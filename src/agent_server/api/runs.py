"""Run endpoints for Agent Protocol"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from langgraph.types import Command, Send
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth_ctx import with_auth_ctx
from ..core.auth_deps import get_current_user
from ..core.orm import Assistant as AssistantORM
from ..core.orm import Run as RunORM
from ..core.orm import Thread as ThreadORM
from ..core.orm import _get_session_maker, get_session
from ..core.serializers import GeneralSerializer
from ..core.sse import create_end_event, get_sse_headers
from ..models import Run, RunCreate, RunStatus, User
from ..services.langgraph_service import create_run_config, get_langgraph_service
from ..services.streaming_service import streaming_service
from ..utils.assistants import resolve_assistant_id

router = APIRouter()

logger = logging.getLogger(__name__)
serializer = GeneralSerializer()
# TODO: Replace all print statements and bare exceptions with structured logging across the codebase


# NOTE: We keep only an in-memory task registry for asyncio.Task handles.
# All run metadata/state is persisted via ORM.
active_runs: dict[str, asyncio.Task] = {}

# Default stream modes for background run execution
DEFAULT_STREAM_MODES = ["values"]


def map_command_to_langgraph(cmd: dict[str, Any]) -> Command:
    """Convert API command to LangGraph Command"""
    goto = cmd.get("goto")
    if goto is not None and not isinstance(goto, list):
        goto = [goto]

    update = cmd.get("update")
    if isinstance(update, (tuple, list)) and all(
        isinstance(t, (tuple, list)) and len(t) == 2 and isinstance(t[0], str)
        for t in update
    ):
        update = [tuple(t) for t in update]

    return Command(
        update=update,
        goto=(
            [
                it if isinstance(it, str) else Send(it["node"], it["input"])
                for it in goto
            ]
            if goto
            else None
        ),
        resume=cmd.get("resume"),
    )


async def set_thread_status(session: AsyncSession, thread_id: str, status: str) -> None:
    """Update the status column of a thread."""
    await session.execute(
        update(ThreadORM)
        .where(ThreadORM.thread_id == thread_id)
        .values(status=status, updated_at=datetime.now(UTC))
    )
    await session.commit()


async def update_thread_metadata(
    session: AsyncSession, thread_id: str, assistant_id: str, graph_id: str
) -> None:
    """Update thread metadata with assistant and graph information (dialect agnostic)."""
    # Read-modify-write to avoid DB-specific JSON concat operators
    thread = await session.scalar(
        select(ThreadORM).where(ThreadORM.thread_id == thread_id)
    )
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found for metadata update")
    md = dict(getattr(thread, "metadata_json", {}) or {})
    md.update(
        {
            "assistant_id": str(assistant_id),
            "graph_id": graph_id,
        }
    )
    await session.execute(
        update(ThreadORM)
        .where(ThreadORM.thread_id == thread_id)
        .values(metadata_json=md, updated_at=datetime.now(UTC))
    )
    await session.commit()


@router.post("/threads/{thread_id}/runs", response_model=Run)
async def create_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Create and execute a new run (persisted)."""

    # Validate resume command requirements early
    if request.command and request.command.get("resume") is not None:
        # Check if thread exists and is in interrupted state
        thread_stmt = select(ThreadORM).where(ThreadORM.thread_id == thread_id)
        thread = await session.scalar(thread_stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")
        if thread.status != "interrupted":
            raise HTTPException(
                400, "Cannot resume: thread is not in interrupted state"
            )

    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    print(
        f"create_run: scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    print(
        f"[create_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}"
    )

    # Validate assistant exists and get its graph_id. If a graph_id was provided
    # instead of an assistant UUID, map it deterministically and fall back to the
    # default assistant created at startup.
    requested_id = str(request.assistant_id)
    available_graphs = langgraph_service.list_graphs()
    resolved_assistant_id = resolve_assistant_id(requested_id, available_graphs)

    config = request.config
    context = request.context

    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == resolved_assistant_id,
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(
            404, f"Graph '{assistant.graph_id}' not found for assistant"
        )

    # Mark thread as busy and update metadata with assistant/graph info
    await set_thread_status(session, thread_id, "busy")
    await update_thread_metadata(
        session, thread_id, assistant.assistant_id, assistant.graph_id
    )

    # Persist run record via ORM model in core.orm (Run table)
    now = datetime.now(UTC)
    run_orm = RunORM(
        run_id=run_id,  # explicitly set (DB can also default-generate if omitted)
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="pending",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response from ORM -> Pydantic
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="pending",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )

    # Start execution asynchronously
    # Don't pass the session to avoid transaction conflicts
    task = asyncio.create_task(
        execute_run_async(
            run_id,
            thread_id,
            assistant.graph_id,
            request.input or {},
            user,
            config,
            context,
            request.stream_mode,
            None,  # Don't pass session to avoid conflicts
            request.checkpoint,
            request.command,
            request.interrupt_before,
            request.interrupt_after,
            request.multitask_strategy,
            request.stream_subgraphs,
        )
    )
    print(
        f"[create_run] background task created task_id={id(task)} for run_id={run_id}"
    )
    active_runs[run_id] = task

    return run


@router.post("/threads/{thread_id}/runs/stream")
async def create_and_stream_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Create a new run and stream its execution - persisted + SSE."""

    # Validate resume command requirements early
    if request.command and request.command.get("resume") is not None:
        # Check if thread exists and is in interrupted state
        thread_stmt = select(ThreadORM).where(ThreadORM.thread_id == thread_id)
        thread = await session.scalar(thread_stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")
        if thread.status != "interrupted":
            raise HTTPException(
                400, "Cannot resume: thread is not in interrupted state"
            )

    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    print(
        f"[create_and_stream_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}"
    )

    # Validate assistant exists and get its graph_id. Allow passing a graph_id
    # by mapping it to a deterministic assistant ID.
    requested_id = str(request.assistant_id)
    available_graphs = langgraph_service.list_graphs()

    resolved_assistant_id = resolve_assistant_id(requested_id, available_graphs)

    config = request.config
    context = request.context

    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == resolved_assistant_id,
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(
            404, f"Graph '{assistant.graph_id}' not found for assistant"
        )

    # Mark thread as busy and update metadata with assistant/graph info
    await set_thread_status(session, thread_id, "busy")
    await update_thread_metadata(
        session, thread_id, assistant.assistant_id, assistant.graph_id
    )

    # Persist run record
    now = datetime.now(UTC)
    run_orm = RunORM(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="streaming",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response model for stream context
    run = Run(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="streaming",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )

    # Start background execution that will populate the broker
    # Don't pass the session to avoid transaction conflicts
    task = asyncio.create_task(
        execute_run_async(
            run_id,
            thread_id,
            assistant.graph_id,
            request.input or {},
            user,
            config,
            context,
            request.stream_mode,
            None,  # Don't pass session to avoid conflicts
            request.checkpoint,
            request.command,
            request.interrupt_before,
            request.interrupt_after,
            request.multitask_strategy,
            request.stream_subgraphs,
        )
    )
    print(
        f"[create_and_stream_run] background task created task_id={id(task)} for run_id={run_id}"
    )
    active_runs[run_id] = task

    # Extract requested stream mode(s)
    stream_mode = request.stream_mode
    if not stream_mode and config and "stream_mode" in config:
        stream_mode = config["stream_mode"]

    # Stream immediately from broker (which will also include replay of any early events)
    cancel_on_disconnect = (request.on_disconnect or "continue").lower() == "cancel"

    return StreamingResponse(
        streaming_service.stream_run_execution(
            run,
            None,
            cancel_on_disconnect=cancel_on_disconnect,
        ),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        },
    )


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=Run)
async def get_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Get run by ID (persisted)."""
    stmt = select(RunORM).where(
        RunORM.run_id == str(run_id),
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
    )
    print(
        f"[get_run] querying DB run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    run_orm = await session.scalar(stmt)
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Refresh to ensure we have the latest data (in case background task updated it)
    await session.refresh(run_orm)

    print(
        f"[get_run] found run status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}"
    )
    # Convert to Pydantic
    return Run.model_validate(
        {c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns}
    )


@router.get("/threads/{thread_id}/runs", response_model=list[Run])
async def list_runs(
    thread_id: str,
    limit: int = Query(10, ge=1, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip for pagination"),
    status: str | None = Query(None, description="Filter by run status"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Run]:
    """List runs for a specific thread (persisted)."""
    stmt = (
        select(RunORM)
        .where(
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
            *([RunORM.status == status] if status else []),
        )
        .limit(limit)
        .offset(offset)
        .order_by(RunORM.created_at.desc())
    )
    print(f"[list_runs] querying DB thread_id={thread_id} user={user.identity}")
    result = await session.scalars(stmt)
    rows = result.all()
    runs = [
        Run.model_validate({c.name: getattr(r, c.name) for c in r.__table__.columns})
        for r in rows
    ]
    print(f"[list_runs] total={len(runs)} user={user.identity} thread_id={thread_id}")
    return runs


@router.patch("/threads/{thread_id}/runs/{run_id}")
async def update_run(
    thread_id: str,
    run_id: str,
    request: RunStatus,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Update run status (for cancellation/interruption, persisted)."""
    print(
        f"[update_run] fetch for update run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Handle interruption/cancellation

    if request.status == "cancelled":
        print(
            f"[update_run] cancelling run_id={run_id} user={user.identity} thread_id={thread_id}"
        )
        await streaming_service.cancel_run(run_id)
        print(f"[update_run] set DB status=cancelled run_id={run_id}")
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="cancelled", updated_at=datetime.now(UTC))
        )
        await session.commit()
        print(f"[update_run] commit done (cancelled) run_id={run_id}")
    elif request.status == "interrupted":
        print(
            f"[update_run] interrupt run_id={run_id} user={user.identity} thread_id={thread_id}"
        )
        await streaming_service.interrupt_run(run_id)
        print(f"[update_run] set DB status=interrupted run_id={run_id}")
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="interrupted", updated_at=datetime.now(UTC))
        )
        await session.commit()
        print(f"[update_run] commit done (interrupted) run_id={run_id}")

    # Return final run state
    run_orm = await session.scalar(select(RunORM).where(RunORM.run_id == run_id))
    if run_orm:
        # Refresh to ensure we have the latest data after our own update
        await session.refresh(run_orm)
    return Run.model_validate(
        {c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns}
    )


@router.get("/threads/{thread_id}/runs/{run_id}/join")
async def join_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Join a run (wait for completion and return final output) - persisted."""
    # Get run and validate it exists
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # If already completed, return output immediately
    if run_orm.status in ["completed", "failed", "cancelled"]:
        # Refresh to ensure we have the latest data
        await session.refresh(run_orm)
        output = getattr(run_orm, "output", None) or {}
        return output

    # Wait for background task to complete
    task = active_runs.get(run_id)
    if task:
        try:
            await asyncio.wait_for(task, timeout=30.0)
        except TimeoutError:
            # Task is taking too long, but that's okay - we'll check DB status
            pass
        except asyncio.CancelledError:
            # Task was cancelled, that's also okay
            pass

    # Return final output from database
    run_orm = await session.scalar(select(RunORM).where(RunORM.run_id == run_id))
    if run_orm:
        await session.refresh(run_orm)  # Refresh to get latest data from DB
    output = getattr(run_orm, "output", None) or {}
    return output


# TODO: check if this method is actually required because the implementation doesn't seem correct.
@router.get("/threads/{thread_id}/runs/{run_id}/stream")
async def stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    _stream_mode: str | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream run execution with SSE and reconnection support - persisted metadata."""
    print(
        f"[stream_run] fetch for stream run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    print(
        f"[stream_run] status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}"
    )
    # If already terminal, emit a final end event
    if run_orm.status in ["completed", "failed", "cancelled"]:

        async def generate_final() -> AsyncIterator[str]:
            yield create_end_event()

        print(
            f"[stream_run] starting terminal stream run_id={run_id} status={run_orm.status}"
        )
        return StreamingResponse(
            generate_final(),
            media_type="text/event-stream",
            headers={
                **get_sse_headers(),
                "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
                "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
            },
        )

    # Stream active or pending runs via broker

    # Build a lightweight Pydantic Run from ORM for streaming context (IDs already strings)
    run_model = Run.model_validate(
        {c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns}
    )

    return StreamingResponse(
        streaming_service.stream_run_execution(
            run_model, last_event_id, cancel_on_disconnect=False
        ),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        },
    )


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    thread_id: str,
    run_id: str,
    wait: int = Query(
        0, ge=0, le=1, description="Whether to wait for the run task to settle"
    ),
    action: str = Query(
        "cancel", pattern="^(cancel|interrupt)$", description="Cancellation action"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """
    Cancel or interrupt a run (client-compatible endpoint).

    Matches client usage:
      POST /v1/threads/{thread_id}/runs/{run_id}/cancel?wait=0&action=interrupt

    - action=cancel => hard cancel
    - action=interrupt => cooperative interrupt if supported
    - wait=1 => await background task to finish settling
    """
    print(
        f"[cancel_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    if action == "interrupt":
        print(
            f"[cancel_run] interrupt run_id={run_id} user={user.identity} thread_id={thread_id}"
        )
        await streaming_service.interrupt_run(run_id)
        # Persist status as interrupted
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="interrupted", updated_at=datetime.now(UTC))
        )
        await session.commit()
    else:
        print(
            f"[cancel_run] cancel run_id={run_id} user={user.identity} thread_id={thread_id}"
        )
        await streaming_service.cancel_run(run_id)
        # Persist status as cancelled
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="cancelled", updated_at=datetime.now(UTC))
        )
        await session.commit()

    # Optionally wait for background task
    if wait:
        task = active_runs.get(run_id)
        if task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # Reload and return updated Run (do NOT delete here; deletion is a separate endpoint)
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found after cancellation")
    return Run.model_validate(
        {c.name: getattr(run_orm, c.name) for c in run_orm.__table__.columns}
    )


def _should_skip_event(raw_event: Any) -> bool:
    """Check if an event should be skipped based on langsmith:nostream tag"""
    try:
        # Check if the event has metadata with tags containing 'langsmith:nostream'
        if isinstance(raw_event, tuple) and len(raw_event) >= 2:
            # For tuple events, check the third element (metadata tuple)
            metadata_tuple = raw_event[len(raw_event) - 1]
            if isinstance(metadata_tuple, tuple) and len(metadata_tuple) >= 2:
                # Get the second item in the metadata tuple
                metadata = metadata_tuple[1]
                if isinstance(metadata, dict) and "tags" in metadata:
                    tags = metadata["tags"]
                    if isinstance(tags, list) and "langsmith:nostream" in tags:
                        return True
        return False
    except Exception:
        # If we can't parse the event structure, don't skip it
        return False


async def execute_run_async(
    run_id: str,
    thread_id: str,
    graph_id: str,
    input_data: dict,
    user: User,
    config: dict | None = None,
    context: dict | None = None,
    stream_mode: list[str] | None = None,
    session: AsyncSession | None = None,
    checkpoint: dict | None = None,
    command: dict[str, Any] | None = None,
    interrupt_before: str | list[str] | None = None,
    interrupt_after: str | list[str] | None = None,
    _multitask_strategy: str | None = None,
    subgraphs: bool | None = False,
) -> None:
    """Execute run asynchronously in background using streaming to capture all events"""  # Use provided session or get a new one
    if session is None:
        maker = _get_session_maker()
        session = maker()

    # Normalize stream_mode once here for all callers/endpoints.
    # Accept "messages-tuple" as an alias of "messages".
    def _normalize_mode(mode: str | None) -> str | None:
        return (
            "messages" if isinstance(mode, str) and mode == "messages-tuple" else mode
        )

    if isinstance(stream_mode, list):
        stream_mode = [_normalize_mode(m) for m in stream_mode]
    else:
        stream_mode = _normalize_mode(stream_mode)

    try:
        # Update status
        await update_run_status(run_id, "running", session=session)

        # Get graph and execute
        langgraph_service = get_langgraph_service()
        graph = await langgraph_service.get_graph(graph_id)

        run_config = create_run_config(
            run_id, thread_id, user, config or {}, checkpoint
        )

        # Handle human-in-the-loop fields
        if interrupt_before is not None:
            run_config["interrupt_before"] = (
                interrupt_before
                if isinstance(interrupt_before, list)
                else [interrupt_before]
            )
        if interrupt_after is not None:
            run_config["interrupt_after"] = (
                interrupt_after
                if isinstance(interrupt_after, list)
                else [interrupt_after]
            )

        # Note: multitask_strategy is handled at the run creation level, not execution level
        # It controls concurrent run behavior, not graph execution behavior

        # Determine input for execution (either input_data or command)
        if command is not None:
            # When command is provided, it replaces input entirely (LangGraph API behavior)
            if isinstance(command, dict):
                execution_input = map_command_to_langgraph(command)
            else:
                # Direct resume value (backward compatibility)
                execution_input = Command(resume=command)
        else:
            # No command, use regular input
            execution_input = input_data

        # Execute using streaming to capture events for later replay
        event_counter = 0
        final_output = None
        has_interrupt = False

        # Prepare stream modes for execution
        if stream_mode is None:
            final_stream_modes = DEFAULT_STREAM_MODES.copy()
        elif isinstance(stream_mode, str):
            final_stream_modes = [stream_mode]
        else:
            final_stream_modes = stream_mode.copy()

        # Ensure interrupt events are captured by including updates mode
        # Track whether updates was explicitly requested by user
        user_requested_updates = "updates" in final_stream_modes
        if not user_requested_updates:
            final_stream_modes.append("updates")

        only_interrupt_updates = not user_requested_updates

        async with with_auth_ctx(user, []):
            async for raw_event in graph.astream(
                execution_input,
                config=run_config,
                context=context,
                subgraphs=subgraphs,
                stream_mode=final_stream_modes,
            ):
                # Skip events that contain langsmith:nostream tag
                if _should_skip_event(raw_event):
                    continue

                event_counter += 1
                event_id = f"{run_id}_event_{event_counter}"

                # Forward to broker for live consumers
                await streaming_service.put_to_broker(
                    run_id,
                    event_id,
                    raw_event,
                    only_interrupt_updates=only_interrupt_updates,
                )
                # Store for replay
                await streaming_service.store_event_from_raw(
                    run_id,
                    event_id,
                    raw_event,
                    only_interrupt_updates=only_interrupt_updates,
                )

                # Check for interrupt in this event
                event_data = None
                if isinstance(raw_event, tuple) and len(raw_event) >= 2:
                    event_data = raw_event[1]
                elif not isinstance(raw_event, tuple):
                    event_data = raw_event

                if isinstance(event_data, dict) and "__interrupt__" in event_data:
                    has_interrupt = True

                # Track final output
                if isinstance(raw_event, tuple):
                    if len(raw_event) >= 2 and raw_event[0] == "values":
                        final_output = raw_event[1]
                elif not isinstance(raw_event, tuple):
                    # Non-tuple events are values mode
                    final_output = raw_event

        if has_interrupt:
            await update_run_status(
                run_id, "interrupted", output=final_output or {}, session=session
            )
            if not session:
                raise RuntimeError(
                    f"No database session available to update thread {thread_id} status"
                )
            await set_thread_status(session, thread_id, "interrupted")

        else:
            # Update with results
            await update_run_status(
                run_id, "completed", output=final_output or {}, session=session
            )
            # Mark thread back to idle
            if not session:
                raise RuntimeError(
                    f"No database session available to update thread {thread_id} status"
                )
            await set_thread_status(session, thread_id, "idle")

    except asyncio.CancelledError:
        # Store empty output to avoid JSON serialization issues
        await update_run_status(run_id, "cancelled", output={}, session=session)
        if not session:
            raise RuntimeError(
                f"No database session available to update thread {thread_id} status"
            ) from None
        await set_thread_status(session, thread_id, "idle")
        # Signal cancellation to broker
        await streaming_service.signal_run_cancelled(run_id)
        raise
    except Exception as e:
        # Store empty output to avoid JSON serialization issues
        await update_run_status(
            run_id, "failed", output={}, error=str(e), session=session
        )
        if not session:
            raise RuntimeError(
                f"No database session available to update thread {thread_id} status"
            ) from None
        await set_thread_status(session, thread_id, "idle")
        # Signal error to broker
        await streaming_service.signal_run_error(run_id, str(e))
        raise
    finally:
        # Clean up broker
        await streaming_service.cleanup_run(run_id)
        active_runs.pop(run_id, None)


async def update_run_status(
    run_id: str,
    status: str,
    output: Any = None,
    error: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Update run status in database (persisted). If session not provided, opens a short-lived session."""
    owns_session = False
    if session is None:
        maker = _get_session_maker()
        session = maker()  # type: ignore[assignment]
        owns_session = True
    try:
        values = {"status": status, "updated_at": datetime.now(UTC)}
        if output is not None:
            # Serialize output to ensure JSON compatibility
            try:
                serialized_output = serializer.serialize(output)
                values["output"] = serialized_output
            except Exception as e:
                logger.warning(f"Failed to serialize output for run {run_id}: {e}")
                values["output"] = {
                    "error": "Output serialization failed",
                    "original_type": str(type(output)),
                }
        if error is not None:
            values["error_message"] = error
        print(f"[update_run_status] updating DB run_id={run_id} status={status}")
        await session.execute(
            update(RunORM).where(RunORM.run_id == str(run_id)).values(**values)
        )  # type: ignore[arg-type]
        await session.commit()
        print(f"[update_run_status] commit done run_id={run_id}")
    finally:
        # Close only if we created it here
        if owns_session:
            await session.close()  # type: ignore[func-returns-value]


@router.delete("/threads/{thread_id}/runs/{run_id}", status_code=204)
async def delete_run(
    thread_id: str,
    run_id: str,
    force: int = Query(
        0, ge=0, le=1, description="Force cancel active run before delete (1=yes)"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Delete a run record.

    Behavior:
    - If the run is active (pending/running/streaming) and force=0, returns 409 Conflict.
    - If force=1 and the run is active, cancels it first (best-effort) and then deletes.
    - Always returns 204 No Content on successful deletion.
    """
    print(
        f"[delete_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}"
    )
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # If active and not forcing, reject deletion
    if run_orm.status in ["pending", "running", "streaming"] and not force:
        raise HTTPException(
            status_code=409,
            detail="Run is active. Retry with force=1 to cancel and delete.",
        )

    # If forcing and active, cancel first
    if force and run_orm.status in ["pending", "running", "streaming"]:
        print(f"[delete_run] force-cancelling active run run_id={run_id}")
        await streaming_service.cancel_run(run_id)
        # Best-effort: wait for bg task to settle
        task = active_runs.get(run_id)
        if task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # Delete the record
    await session.execute(
        delete(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    await session.commit()

    # Clean up active task if exists
    task = active_runs.pop(run_id, None)
    if task and not task.done():
        task.cancel()

    # 204 No Content
    return
