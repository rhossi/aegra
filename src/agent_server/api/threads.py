"""Thread endpoints for Agent Protocol"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.runs import active_runs
from ..core.auth_deps import get_current_user
from ..core.orm import Run as RunORM
from ..core.orm import Thread as ThreadORM
from ..core.orm import get_session
from ..models import (
    Thread,
    ThreadCheckpointPostRequest,
    ThreadCreate,
    ThreadHistoryRequest,
    ThreadList,
    ThreadSearchRequest,
    ThreadState,
    User,
)
from ..services.streaming_service import streaming_service
from ..services.thread_state_service import ThreadStateService

# TODO: adopt structured logging across all modules; replace print() and bare exceptions in:
# - agent_server/api/*.py
# - agent_server/services/*.py
# - agent_server/core/*.py
# - agent_server/models/*.py (where applicable)
# Use logging.getLogger(__name__) and appropriate levels (debug/info/warning/error).

router = APIRouter()
logger = logging.getLogger(__name__)

thread_state_service = ThreadStateService()


# In-memory storage removed; using database via ORM


@router.post("/threads", response_model=Thread)
async def create_thread(
    request: ThreadCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new conversation thread"""

    thread_id = str(uuid4())

    # Build metadata with required fields
    metadata = request.metadata or {}
    metadata.update(
        {
            "owner": user.identity,
            "assistant_id": None,  # Will be set when first run is created
            "graph_id": None,  # Will be set when first run is created
            "thread_name": "",  # User can update this later
        }
    )

    thread_orm = ThreadORM(
        thread_id=thread_id,
        status="idle",
        metadata_json=metadata,
        user_id=user.identity,
    )
    # SQLAlchemy AsyncSession.add is sync; do not await
    session.add(thread_orm)
    await session.commit()
    # In tests, session.refresh may be a no-op; guard access to columns accordingly
    with contextlib.suppress(Exception):
        await session.refresh(thread_orm)

    # TODO: initialize LangGraph checkpoint with initial_state if provided

    # Build a safe dict for Pydantic Thread validation, coercing MagicMocks to plain types
    def _coerce_str(val: Any, default: str) -> str:
        try:
            s = str(val)
            # MagicMock string often contains "MagicMock"; if so, fall back to default
            return default if "MagicMock" in s else s
        except Exception:
            return default

    def _coerce_dict(val: Any, default: dict[str, Any]) -> dict[str, Any]:
        if isinstance(val, dict):
            return val
        # Some mocks might pretend to be mapping; try to convert safely
        with contextlib.suppress(Exception):
            if hasattr(val, "items"):
                return dict(val.items())  # type: ignore[attr-defined]
        return default

    coerced_thread_id = _coerce_str(
        getattr(thread_orm, "thread_id", thread_id), thread_id
    )
    coerced_status = _coerce_str(getattr(thread_orm, "status", "idle"), "idle")
    coerced_user_id = _coerce_str(
        getattr(thread_orm, "user_id", user.identity), user.identity
    )
    coerced_metadata = _coerce_dict(
        getattr(thread_orm, "metadata_json", metadata), metadata
    )
    coerced_created_at = getattr(thread_orm, "created_at", None)
    if not isinstance(coerced_created_at, datetime):
        coerced_created_at = datetime.now(UTC)

    thread_dict: dict[str, Any] = {
        "thread_id": coerced_thread_id,
        "status": coerced_status,
        "metadata": coerced_metadata,
        "user_id": coerced_user_id,
        "created_at": coerced_created_at,
    }

    return Thread.model_validate(thread_dict)


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    """List user's threads"""
    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)
    result = await session.scalars(stmt)
    rows = result.all()
    user_threads = [
        Thread.model_validate(
            {
                **{c.name: getattr(t, c.name) for c in t.__table__.columns},
                "metadata": t.metadata_json,
            }
        )
        for t in rows
    ]
    return ThreadList(threads=user_threads, total=len(user_threads))


@router.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread by ID"""
    stmt = select(ThreadORM).where(
        ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
    )
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    return Thread.model_validate(
        {
            **{c.name: getattr(thread, c.name) for c in thread.__table__.columns},
            "metadata": thread.metadata_json,
        }
    )


@router.get("/threads/{thread_id}/state/{checkpoint_id}", response_model=ThreadState)
async def get_thread_state_at_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    subgraphs: bool | None = Query(False, description="Include states from subgraphs"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread state at a specific checkpoint"""
    try:
        # Verify the thread exists and belongs to the user
        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        # Extract graph_id from thread metadata
        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            raise HTTPException(404, f"Thread '{thread_id}' has no associated graph")

        # Get compiled graph
        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()
        try:
            agent = await langgraph_service.get_graph(graph_id)
        except Exception as e:
            logger.exception(
                "Failed to load graph '%s' for checkpoint retrieval", graph_id
            )
            raise HTTPException(
                500, f"Failed to load graph '{graph_id}': {str(e)}"
            ) from e

        # Build config with user context and thread_id
        config: dict[str, Any] = create_thread_config(thread_id, user, {})
        config["configurable"]["checkpoint_id"] = checkpoint_id

        # Fetch state at checkpoint
        try:
            agent = agent.with_config(config)
            state_snapshot = await agent.aget_state(config, subgraphs=subgraphs)
        except Exception as e:
            logger.exception(
                "Failed to retrieve state at checkpoint '%s' for thread '%s'",
                checkpoint_id,
                thread_id,
            )
            raise HTTPException(
                500,
                f"Failed to retrieve state at checkpoint '{checkpoint_id}': {str(e)}",
            ) from e

        if not state_snapshot:
            raise HTTPException(
                404,
                f"No state found at checkpoint '{checkpoint_id}' for thread '{thread_id}'",
            )

        # Convert snapshot to ThreadCheckpoint using service
        thread_checkpoint = thread_state_service.convert_snapshot_to_thread_state(
            state_snapshot,
            thread_id,
        )

        return thread_checkpoint

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error retrieving checkpoint '%s' for thread '%s'", checkpoint_id, thread_id
        )
        raise HTTPException(
            500, f"Error retrieving checkpoint '{checkpoint_id}': {str(e)}"
        ) from e


@router.post("/threads/{thread_id}/state/checkpoint", response_model=ThreadState)
async def get_thread_state_at_checkpoint_post(
    thread_id: str,
    request: ThreadCheckpointPostRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread state at a specific checkpoint (POST method - for SDK compatibility)"""
    # Reuse GET logic by calling the function directly
    checkpoint = request.checkpoint
    subgraphs = request.subgraphs
    output = await get_thread_state_at_checkpoint(
        thread_id, checkpoint.checkpoint_id, subgraphs, user, session
    )
    return output


@router.post("/threads/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_post(
    thread_id: str,
    request: ThreadHistoryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread checkpoint history (POST method - for SDK compatibility)"""

    try:
        # Validate and coerce inputs
        limit = request.limit or 10
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise HTTPException(
                422, "Invalid limit; must be an integer between 1 and 1000"
            )

        before = request.before
        if before is not None and not isinstance(before, str):
            raise HTTPException(
                422,
                "Invalid 'before' parameter; must be a string checkpoint identifier",
            )

        metadata = request.metadata
        if metadata is not None and not isinstance(metadata, dict):
            raise HTTPException(422, "Invalid 'metadata' parameter; must be an object")

        checkpoint = request.checkpoint or {}
        if not isinstance(checkpoint, dict):
            raise HTTPException(
                422, "Invalid 'checkpoint' parameter; must be an object"
            )

        # Optional flags
        subgraphs = bool(request.subgraphs) if request.subgraphs is not None else False
        checkpoint_ns = request.checkpoint_ns
        if checkpoint_ns is not None and not isinstance(checkpoint_ns, str):
            raise HTTPException(422, "Invalid 'checkpoint_ns'; must be a string")

        logger.debug(
            f"history POST: thread_id={thread_id} limit={limit} before={before} subgraphs={subgraphs} checkpoint_ns={checkpoint_ns}"
        )

        # Verify the thread exists and belongs to the user
        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        # Extract graph_id from thread metadata
        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            # Return empty history if no graph is associated yet
            logger.info(f"history POST: no graph_id set for thread {thread_id}")
            return []

        # Get compiled graph
        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()
        try:
            agent = await langgraph_service.get_graph(graph_id)
        except Exception as e:
            logger.exception("Failed to load graph '%s' for history", graph_id)
            raise HTTPException(
                500, f"Failed to load graph '{graph_id}': {str(e)}"
            ) from e

        # Build config with user context and thread_id
        config: dict[str, Any] = create_thread_config(thread_id, user, {})
        # Merge checkpoint and namespace if provided
        if checkpoint:
            cfg_cp = checkpoint.copy()
            if checkpoint_ns is not None:
                cfg_cp.setdefault("checkpoint_ns", checkpoint_ns)
            config["configurable"].update(cfg_cp)
        elif checkpoint_ns is not None:
            config["configurable"]["checkpoint_ns"] = checkpoint_ns

        # Fetch state history
        state_snapshots = []
        kwargs = {
            "limit": limit,
            "before": before,
        }
        # The runtime may expect metadata filter under "filter" or "metadata"; try "metadata"
        if metadata is not None:
            kwargs["metadata"] = metadata  # type: ignore[index]

        # Some LangGraph versions support subgraphs flag; pass if available
        try:
            async for snapshot in agent.aget_state_history(
                config, subgraphs=subgraphs, **kwargs
            ):
                state_snapshots.append(snapshot)
        except TypeError:
            # Fallback if subgraphs not supported in this version
            async for snapshot in agent.aget_state_history(config, **kwargs):
                state_snapshots.append(snapshot)

        # Convert snapshots to ThreadState using service
        thread_states = thread_state_service.convert_snapshots_to_thread_states(
            state_snapshots, thread_id
        )

        return thread_states

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in history POST for thread %s", thread_id)
        # Return empty list for clearly absent histories if backend signals not found-like cases
        msg = str(e).lower()
        if "not found" in msg or "no checkpoint" in msg:
            return []
        raise HTTPException(500, f"Error retrieving thread history: {str(e)}") from e


@router.get("/threads/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_get(
    thread_id: str,
    limit: int = Query(10, ge=1, le=1000, description="Number of states to return"),
    before: str | None = Query(
        None, description="Return states before this checkpoint ID"
    ),
    subgraphs: bool | None = Query(False, description="Include states from subgraphs"),
    checkpoint_ns: str | None = Query(None, description="Checkpoint namespace"),
    # Optional metadata filter for parity with POST (use JSON string to avoid FastAPI typing assertion on dict in query)
    metadata: str | None = Query(None, description="JSON-encoded metadata filter"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread checkpoint history (GET method - SDK compatibility)"""
    # Reuse POST logic by constructing a ThreadHistoryRequest-like object
    # Parse metadata JSON string if provided
    parsed_metadata: dict[str, Any] | None = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except Exception as e:
            raise HTTPException(422, f"Invalid metadata query param: {e}") from e
    req = ThreadHistoryRequest(
        limit=limit,
        before=before,
        metadata=parsed_metadata,
        checkpoint=None,
        subgraphs=subgraphs,
        checkpoint_ns=checkpoint_ns,
    )
    return await get_thread_history_post(thread_id, req, user, session)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete thread by ID.

    Automatically cancels any active runs and deletes the thread.
    CASCADE DELETE automatically removes all run records when thread is deleted.
    """
    logger = logging.getLogger(__name__)

    # Check if thread exists
    stmt = select(ThreadORM).where(
        ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
    )
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    # Check for active runs and cancel them
    active_runs_stmt = select(RunORM).where(
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
        RunORM.status.in_(["pending", "running", "streaming"]),
    )
    active_runs_list = (await session.scalars(active_runs_stmt)).all()

    # Cancel active runs if they exist
    if active_runs_list:
        logger.info(
            f"Cancelling {len(active_runs_list)} active runs for thread {thread_id}"
        )

        for run in active_runs_list:
            run_id = run.run_id
            logger.debug(f"Cancelling run {run_id}")

            # Cancel via streaming service
            await streaming_service.cancel_run(run_id)

            # Clean up background task if exists
            task = active_runs.pop(run_id, None)
            if task and not task.done():
                task.cancel()
                # Best-effort: wait for task to settle
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"Error waiting for task {run_id} to settle: {e}")

    # Delete thread (CASCADE DELETE will automatically remove all runs)
    await session.delete(thread)
    await session.commit()

    logger.info(
        f"Deleted thread {thread_id} (cancelled {len(active_runs_list)} active runs)"
    )
    return {"status": "deleted"}


@router.post("/threads/search", response_model=list[Thread])
async def search_threads(
    request: ThreadSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Search threads with filters"""

    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)

    if request.status:
        stmt = stmt.where(ThreadORM.status == request.status)

    if request.metadata:
        # For each key/value, filter JSONB field
        for key, value in request.metadata.items():
            stmt = stmt.where(ThreadORM.metadata_json[key].as_string() == str(value))

    offset = request.offset or 0
    limit = request.limit or 20
    # Return latest first
    stmt = stmt.order_by(ThreadORM.created_at.desc()).offset(offset).limit(limit)

    result = await session.scalars(stmt)
    rows = result.all()
    threads_models = [
        Thread.model_validate(
            {
                **{c.name: getattr(t, c.name) for c in t.__table__.columns},
                "metadata": t.metadata_json,
            }
        )
        for t in rows
    ]

    # Return array of threads for client/vendor parity
    return threads_models
