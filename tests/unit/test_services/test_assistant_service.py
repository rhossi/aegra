"""Unit tests for AssistantService business logic

These tests focus on pure business logic without external dependencies.
All external dependencies (database, LangGraph) are mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from agent_server.models import Assistant, AssistantCreate, AssistantUpdate
from agent_server.services.assistant_service import AssistantService, to_pydantic


@pytest.fixture
def mock_session():
    """Mock AsyncSession for testing"""
    return AsyncMock()


@pytest.fixture
def mock_langgraph_service():
    """Mock LangGraphService for testing"""
    mock_service = Mock()
    mock_service.list_graphs.return_value = {"test-graph": {}}
    mock_service.get_graph = AsyncMock(return_value=Mock())
    return mock_service


@pytest.fixture
def assistant_service(mock_session, mock_langgraph_service):
    """AssistantService instance with mocked dependencies"""
    return AssistantService(mock_session, mock_langgraph_service)


@pytest.fixture
def sample_assistant_create():
    """Sample AssistantCreate request for testing"""
    return AssistantCreate(
        name="Test Assistant",
        description="A test assistant",
        graph_id="test-graph",
        config={"temperature": 0.7},
        context={"user_id": "test-user"},
        metadata={"env": "test"},
    )


@pytest.fixture
def sample_assistant_update():
    """Sample AssistantUpdate request for testing"""
    return AssistantUpdate(
        name="Updated Assistant",
        description="An updated test assistant",
        config={"temperature": 0.8},
        metadata={"env": "updated"},
    )


class TestToPydantic:
    """Test ORM to Pydantic conversion logic"""

    def test_to_pydantic_basic_conversion(self):
        """Test basic ORM to Pydantic conversion"""
        # Create mock ORM object
        mock_orm = Mock()
        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "description"
        mock_column4 = Mock()
        mock_column4.name = "user_id"
        mock_column5 = Mock()
        mock_column5.name = "graph_id"
        mock_column6 = Mock()
        mock_column6.name = "version"
        mock_column7 = Mock()
        mock_column7.name = "created_at"
        mock_column8 = Mock()
        mock_column8.name = "updated_at"
        mock_column9 = Mock()
        mock_column9.name = "config"
        mock_column10 = Mock()
        mock_column10.name = "context"
        mock_column11 = Mock()
        mock_column11.name = "metadata_dict"
        mock_table.columns = [
            mock_column1,
            mock_column2,
            mock_column3,
            mock_column4,
            mock_column5,
            mock_column6,
            mock_column7,
            mock_column8,
            mock_column9,
            mock_column10,
            mock_column11,
        ]
        mock_orm.__table__ = mock_table
        mock_orm.assistant_id = uuid.uuid4()
        mock_orm.name = "Test Assistant"
        mock_orm.description = "Test Description"
        mock_orm.user_id = uuid.uuid4()
        mock_orm.graph_id = "test-graph"
        mock_orm.version = 1
        mock_orm.created_at = datetime.now(UTC)
        mock_orm.updated_at = datetime.now(UTC)
        mock_orm.config = {}
        mock_orm.context = {}
        mock_orm.metadata_dict = {}

        result = to_pydantic(mock_orm)

        assert isinstance(result, Assistant)
        assert result.name == "Test Assistant"
        assert result.description == "Test Description"
        assert isinstance(result.assistant_id, str)
        assert isinstance(result.user_id, str)

    def test_to_pydantic_uuid_conversion(self):
        """Test UUID to string conversion"""
        mock_orm = Mock()
        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "user_id"
        mock_column4 = Mock()
        mock_column4.name = "graph_id"
        mock_column5 = Mock()
        mock_column5.name = "version"
        mock_column6 = Mock()
        mock_column6.name = "created_at"
        mock_column7 = Mock()
        mock_column7.name = "updated_at"
        mock_column8 = Mock()
        mock_column8.name = "config"
        mock_column9 = Mock()
        mock_column9.name = "context"
        mock_column10 = Mock()
        mock_column10.name = "metadata_dict"
        mock_table.columns = [
            mock_column1,
            mock_column2,
            mock_column3,
            mock_column4,
            mock_column5,
            mock_column6,
            mock_column7,
            mock_column8,
            mock_column9,
            mock_column10,
        ]
        mock_orm.__table__ = mock_table
        test_uuid = uuid.uuid4()
        mock_orm.assistant_id = test_uuid
        mock_orm.name = "Test Assistant"
        mock_orm.description = "Test description"
        mock_orm.user_id = test_uuid
        mock_orm.graph_id = "test-graph"
        mock_orm.version = 1
        mock_orm.created_at = datetime.now(UTC)
        mock_orm.updated_at = datetime.now(UTC)
        mock_orm.config = {}
        mock_orm.context = {}
        mock_orm.metadata_dict = {}

        result = to_pydantic(mock_orm)

        assert result.assistant_id == str(test_uuid)
        assert result.user_id == str(test_uuid)

    def test_to_pydantic_none_values(self):
        """Test handling of None values"""
        mock_orm = Mock()
        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "user_id"
        mock_column4 = Mock()
        mock_column4.name = "graph_id"
        mock_column5 = Mock()
        mock_column5.name = "version"
        mock_column6 = Mock()
        mock_column6.name = "created_at"
        mock_column7 = Mock()
        mock_column7.name = "updated_at"
        mock_column8 = Mock()
        mock_column8.name = "config"
        mock_column9 = Mock()
        mock_column9.name = "context"
        mock_column10 = Mock()
        mock_column10.name = "metadata_dict"
        mock_table.columns = [
            mock_column1,
            mock_column2,
            mock_column3,
            mock_column4,
            mock_column5,
            mock_column6,
            mock_column7,
            mock_column8,
            mock_column9,
            mock_column10,
        ]
        mock_orm.__table__ = mock_table
        mock_orm.assistant_id = "test-id"
        mock_orm.name = "Test"
        mock_orm.description = None
        mock_orm.user_id = "user-123"
        mock_orm.graph_id = "test-graph"
        mock_orm.version = 1
        mock_orm.created_at = datetime.now(UTC)
        mock_orm.updated_at = datetime.now(UTC)
        mock_orm.config = {}
        mock_orm.context = {}
        mock_orm.metadata_dict = {}

        result = to_pydantic(mock_orm)

        assert result.assistant_id == "test-id"
        assert result.name == "Test"


class TestAssistantServiceCreate:
    """Test assistant creation business logic"""

    @pytest.mark.asyncio
    async def test_create_assistant_graph_validation_success(
        self, assistant_service, sample_assistant_create
    ):
        """Test successful graph validation"""
        # Setup mocks
        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()

        # Mock database operations
        assistant_service.session.scalar.return_value = None  # No existing assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.name = "Test Assistant"
        mock_assistant.description = "Test description"
        mock_assistant.user_id = "user-123"
        mock_assistant.graph_id = "test-graph"
        mock_assistant.version = 1
        mock_assistant.created_at = datetime.now(UTC)
        mock_assistant.updated_at = datetime.now(UTC)
        mock_assistant.config = {}
        mock_assistant.context = {}
        mock_assistant.metadata_dict = {}

        assistant_service.session.add = Mock()
        assistant_service.session.commit = AsyncMock()

        # Mock refresh to populate the mock object with attributes
        def mock_refresh(obj):
            obj.assistant_id = "test-id"
            obj.name = "Test Assistant"
            obj.description = "Test description"
            obj.user_id = "user-123"
            obj.graph_id = "test-graph"
            obj.version = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)
            obj.config = {}
            obj.context = {}
            obj.metadata_dict = {}

        assistant_service.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await assistant_service.create_assistant(
            sample_assistant_create, "user-123"
        )

        assert isinstance(result, Assistant)
        assistant_service.langgraph_service.list_graphs.assert_called_once()
        assistant_service.langgraph_service.get_graph.assert_called_once_with(
            "test-graph"
        )

    @pytest.mark.asyncio
    async def test_create_assistant_graph_not_found(
        self, assistant_service, sample_assistant_create
    ):
        """Test graph not found error"""
        assistant_service.langgraph_service.list_graphs.return_value = {
            "other-graph": {}
        }

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.create_assistant(
                sample_assistant_create, "user-123"
            )

        assert exc_info.value.status_code == 400
        assert "Graph 'test-graph' not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_assistant_graph_load_failure(
        self, assistant_service, sample_assistant_create
    ):
        """Test graph loading failure"""
        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.side_effect = Exception(
            "Graph load failed"
        )

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.create_assistant(
                sample_assistant_create, "user-123"
            )

        assert exc_info.value.status_code == 400
        assert "Failed to load graph" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_assistant_config_context_conflict(self, assistant_service):
        """Test config and context conflict validation"""
        request = AssistantCreate(
            graph_id="test-graph",
            config={"configurable": {"key": "value"}},
            context={"other_key": "other_value"},
        )

        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.create_assistant(request, "user-123")

        assert exc_info.value.status_code == 400
        assert "Cannot specify both configurable and context" in str(
            exc_info.value.detail
        )

    @pytest.mark.asyncio
    async def test_create_assistant_config_context_sync_from_config(
        self, assistant_service
    ):
        """Test config to context synchronization"""
        request = AssistantCreate(
            graph_id="test-graph",
            config={"configurable": {"key": "value"}},
            context=None,
        )

        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()
        assistant_service.session.scalar.return_value = None
        assistant_service.session.add = Mock()
        assistant_service.session.commit = AsyncMock()

        # Mock refresh to populate the mock object with attributes
        def mock_refresh(obj):
            obj.assistant_id = "test-id"
            obj.name = "Test Assistant"
            obj.description = "Test description"
            obj.user_id = "user-123"
            obj.graph_id = "test-graph"
            obj.version = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)
            obj.config = {"configurable": {"key": "value"}}
            obj.context = {"key": "value"}
            obj.metadata_dict = {}

        assistant_service.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await assistant_service.create_assistant(request, "user-123")

        # Verify context was set from config
        assert result.context == {"key": "value"}

    @pytest.mark.asyncio
    async def test_create_assistant_config_context_sync_from_context(
        self, assistant_service
    ):
        """Test context to config synchronization"""
        request = AssistantCreate(
            graph_id="test-graph",
            config={},
            context={"key": "value"},
        )

        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()
        assistant_service.session.scalar.return_value = None
        assistant_service.session.add = Mock()
        assistant_service.session.commit = AsyncMock()

        # Mock refresh to populate the mock object with attributes
        def mock_refresh(obj):
            obj.assistant_id = "test-id"
            obj.name = "Test Assistant"
            obj.description = "Test description"
            obj.user_id = "user-123"
            obj.graph_id = "test-graph"
            obj.version = 1
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)
            obj.config = {"configurable": {"key": "value"}}
            obj.context = {"key": "value"}
            obj.metadata_dict = {}

        assistant_service.session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await assistant_service.create_assistant(request, "user-123")

        # Verify config was set from context
        assert result.config == {"configurable": {"key": "value"}}

    @pytest.mark.asyncio
    async def test_create_assistant_duplicate_handling_do_nothing(
        self, assistant_service, sample_assistant_create
    ):
        """Test duplicate assistant handling with do_nothing policy"""
        request = AssistantCreate(
            graph_id="test-graph",
            if_exists="do_nothing",
        )

        # Mock existing assistant
        existing_assistant = Mock()
        existing_assistant.assistant_id = "existing-id"
        existing_assistant.name = "Existing Assistant"
        existing_assistant.description = "Existing description"
        existing_assistant.user_id = "user-123"
        existing_assistant.graph_id = "test-graph"
        existing_assistant.version = 1
        existing_assistant.created_at = datetime.now(UTC)
        existing_assistant.updated_at = datetime.now(UTC)
        existing_assistant.config = {}
        existing_assistant.context = {}
        existing_assistant.metadata_dict = {}

        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        existing_assistant.__table__ = mock_table

        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()
        assistant_service.session.scalar.return_value = existing_assistant

        result = await assistant_service.create_assistant(request, "user-123")

        assert result.assistant_id == "existing-id"
        assert result.name == "Existing Assistant"

    @pytest.mark.asyncio
    async def test_create_assistant_duplicate_handling_error(
        self, assistant_service, sample_assistant_create
    ):
        """Test duplicate assistant handling with error policy"""
        request = AssistantCreate(
            graph_id="test-graph",
            if_exists="error",
        )

        # Mock existing assistant
        existing_assistant = Mock()
        existing_assistant.assistant_id = "existing-id"

        assistant_service.langgraph_service.list_graphs.return_value = {
            "test-graph": {}
        }
        assistant_service.langgraph_service.get_graph.return_value = Mock()
        assistant_service.session.scalar.return_value = existing_assistant

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.create_assistant(request, "user-123")

        assert exc_info.value.status_code == 409
        assert "already exists" in str(exc_info.value.detail)


class TestAssistantServiceGet:
    """Test assistant retrieval business logic"""

    @pytest.mark.asyncio
    async def test_get_assistant_success(self, assistant_service):
        """Test successful assistant retrieval"""
        # Mock assistant from database
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.name = "Test Assistant"
        mock_assistant.description = "Test description"
        mock_assistant.user_id = "user-123"
        mock_assistant.graph_id = "test-graph"
        mock_assistant.version = 1
        mock_assistant.created_at = datetime.now(UTC)
        mock_assistant.updated_at = datetime.now(UTC)
        mock_assistant.config = {}
        mock_assistant.context = {}
        mock_assistant.metadata_dict = {}

        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "user_id"
        mock_table.columns = [mock_column1, mock_column2, mock_column3]
        mock_assistant.__table__ = mock_table

        assistant_service.session.scalar.return_value = mock_assistant

        result = await assistant_service.get_assistant("test-id", "user-123")

        assert isinstance(result, Assistant)
        assert result.assistant_id == "test-id"
        assert result.name == "Test Assistant"

    @pytest.mark.asyncio
    async def test_get_assistant_not_found(self, assistant_service):
        """Test assistant not found error"""
        assistant_service.session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant("nonexistent", "user-123")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_assistant_system_access(self, assistant_service):
        """Test system assistant access"""
        # Mock system assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "system-assistant"
        mock_assistant.name = "System Assistant"
        mock_assistant.description = "System description"
        mock_assistant.user_id = "system"
        mock_assistant.graph_id = "system-graph"
        mock_assistant.version = 1
        mock_assistant.created_at = datetime.now(UTC)
        mock_assistant.updated_at = datetime.now(UTC)
        mock_assistant.config = {}
        mock_assistant.context = {}
        mock_assistant.metadata_dict = {}

        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "user_id"
        mock_table.columns = [mock_column1, mock_column2, mock_column3]
        mock_assistant.__table__ = mock_table

        assistant_service.session.scalar.return_value = mock_assistant

        result = await assistant_service.get_assistant("system-assistant", "user-123")

        assert result.assistant_id == "system-assistant"
        assert result.name == "System Assistant"


class TestAssistantServiceUpdate:
    """Test assistant update business logic"""

    @pytest.mark.asyncio
    async def test_update_assistant_success(
        self, assistant_service, sample_assistant_update
    ):
        """Test successful assistant update"""
        # Mock existing assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.name = "Old Name"
        mock_assistant.description = "Old Description"
        mock_assistant.user_id = "user-123"
        mock_assistant.graph_id = "old-graph"
        mock_assistant.version = 1
        mock_assistant.created_at = datetime.now(UTC)
        mock_assistant.updated_at = datetime.now(UTC)
        mock_assistant.config = {}
        mock_assistant.context = {}
        mock_assistant.metadata_dict = {}

        mock_table = Mock()
        mock_column1 = Mock()
        mock_column1.name = "assistant_id"
        mock_column2 = Mock()
        mock_column2.name = "name"
        mock_column3 = Mock()
        mock_column3.name = "description"
        mock_column4 = Mock()
        mock_column4.name = "graph_id"
        mock_table.columns = [mock_column1, mock_column2, mock_column3, mock_column4]
        mock_assistant.__table__ = mock_table

        # Mock scalar calls: first returns assistant, second returns max version, third returns updated assistant
        assistant_service.session.scalar.side_effect = [
            mock_assistant,
            1,
            mock_assistant,
        ]
        assistant_service.session.execute = AsyncMock()
        assistant_service.session.commit = AsyncMock()

        result = await assistant_service.update_assistant(
            "test-id", sample_assistant_update, "user-123"
        )

        assert isinstance(result, Assistant)
        assistant_service.session.execute.assert_called_once()
        assistant_service.session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_assistant_not_found(
        self, assistant_service, sample_assistant_update
    ):
        """Test update of non-existent assistant"""
        assistant_service.session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.update_assistant(
                "nonexistent", sample_assistant_update, "user-123"
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_assistant_config_context_conflict(self, assistant_service):
        """Test update with config and context conflict"""
        request = AssistantUpdate(
            config={"configurable": {"key": "value"}},
            context={"other_key": "other_value"},
        )

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.update_assistant("test-id", request, "user-123")

        assert exc_info.value.status_code == 400
        assert "Cannot specify both configurable and context" in str(
            exc_info.value.detail
        )


class TestAssistantServiceDelete:
    """Test assistant deletion business logic"""

    @pytest.mark.asyncio
    async def test_delete_assistant_success(self, assistant_service):
        """Test successful assistant deletion"""
        # Mock existing assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.session.delete = AsyncMock()
        assistant_service.session.commit = AsyncMock()

        result = await assistant_service.delete_assistant("test-id", "user-123")

        assert result == {"status": "deleted"}
        assistant_service.session.delete.assert_called_once_with(mock_assistant)
        assistant_service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_assistant_not_found(self, assistant_service):
        """Test deletion of non-existent assistant"""
        assistant_service.session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.delete_assistant("nonexistent", "user-123")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)


class TestAssistantServiceVersionManagement:
    """Test assistant version management logic"""

    @pytest.mark.asyncio
    async def test_set_assistant_latest_success(self, assistant_service):
        """Test setting assistant latest version"""
        # Mock existing assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.name = "Test Assistant"
        mock_assistant.description = "Test description"
        mock_assistant.user_id = "user-123"
        mock_assistant.graph_id = "test-graph"
        mock_assistant.version = 1
        mock_assistant.created_at = datetime.now(UTC)
        mock_assistant.updated_at = datetime.now(UTC)
        mock_assistant.config = {}
        mock_assistant.context = {}
        mock_assistant.metadata_dict = {}

        # Mock existing version
        mock_version = Mock()
        mock_version.name = "Version Name"
        mock_version.description = "Version Description"
        mock_version.config = {"key": "value"}
        mock_version.context = {"ctx": "val"}
        mock_version.graph_id = "test-graph"

        assistant_service.session.scalar.side_effect = [
            mock_assistant,
            mock_version,
            mock_assistant,
        ]
        assistant_service.session.execute = AsyncMock()
        assistant_service.session.commit = AsyncMock()

        result = await assistant_service.set_assistant_latest("test-id", 2, "user-123")

        assert isinstance(result, Assistant)
        assistant_service.session.execute.assert_called_once()
        assistant_service.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_assistant_latest_assistant_not_found(self, assistant_service):
        """Test setting latest version for non-existent assistant"""
        assistant_service.session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.set_assistant_latest("nonexistent", 2, "user-123")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_set_assistant_latest_version_not_found(self, assistant_service):
        """Test setting non-existent version as latest"""
        # Mock existing assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"

        assistant_service.session.scalar.side_effect = [mock_assistant, None]

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.set_assistant_latest("test-id", 999, "user-123")

        assert exc_info.value.status_code == 404
        assert "Version '999' for Assistant 'test-id' not found" in str(
            exc_info.value.detail
        )


class TestAssistantServiceSearch:
    """Test assistant search business logic"""

    @pytest.mark.asyncio
    async def test_search_assistants_with_filters(self, assistant_service):
        """Test assistant search with various filters"""
        # Mock search request
        mock_request = Mock()
        mock_request.name = "test"
        mock_request.description = "description"
        mock_request.graph_id = "graph-1"
        mock_request.metadata = {"env": "test"}
        mock_request.offset = 0
        mock_request.limit = 10

        # Mock search results
        mock_result = Mock()
        mock_result.all.return_value = []

        assistant_service.session.scalars.return_value = mock_result

        result = await assistant_service.search_assistants(mock_request, "user-123")

        assert isinstance(result, list)
        assistant_service.session.scalars.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_assistants_with_filters(self, assistant_service):
        """Test assistant counting with filters"""
        # Mock search request
        mock_request = Mock()
        mock_request.name = "test"
        mock_request.graph_id = "graph-1"

        assistant_service.session.scalar.return_value = 5

        result = await assistant_service.count_assistants(mock_request, "user-123")

        assert result == 5
        assistant_service.session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_assistants_none_result(self, assistant_service):
        """Test assistant counting with None result"""
        mock_request = Mock()
        assistant_service.session.scalar.return_value = None

        result = await assistant_service.count_assistants(mock_request, "user-123")

        assert result == 0


class TestAssistantServiceSchemas:
    """Test assistant schema extraction logic"""

    @pytest.mark.asyncio
    async def test_get_assistant_schemas_success(self, assistant_service):
        """Test successful schema extraction"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph with schemas
        mock_graph = Mock()
        mock_graph.get_input_jsonschema.return_value = {"type": "object"}
        mock_graph.get_output_jsonschema.return_value = {"type": "object"}
        mock_graph.stream_channels_list = []
        mock_graph.channels = {}
        mock_graph.get_name.return_value = "State"
        mock_graph.config_schema.return_value = Mock()
        mock_graph.get_context_jsonschema.return_value = {"type": "object"}

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        result = await assistant_service.get_assistant_schemas("test-id", "user-123")

        assert "graph_id" in result
        assert "input_schema" in result
        assert "output_schema" in result
        assert result["graph_id"] == "test-graph"

    @pytest.mark.asyncio
    async def test_get_assistant_schemas_assistant_not_found(self, assistant_service):
        """Test schema extraction for non-existent assistant"""
        assistant_service.session.scalar.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant_schemas("nonexistent", "user-123")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_assistant_schemas_graph_failure(self, assistant_service):
        """Test schema extraction with graph loading failure"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.side_effect = Exception(
            "Graph load failed"
        )

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant_schemas("test-id", "user-123")

        assert exc_info.value.status_code == 400
        assert "Failed to extract schemas" in str(exc_info.value.detail)


class TestAssistantServiceGraph:
    """Test assistant graph operations"""

    @pytest.mark.asyncio
    async def test_get_assistant_graph_success(self, assistant_service):
        """Test successful graph retrieval"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph
        mock_graph = Mock()
        mock_drawable_graph = Mock()
        mock_drawable_graph.to_json.return_value = {
            "nodes": [{"data": {"id": "node1"}}]
        }

        mock_graph.aget_graph = AsyncMock(return_value=mock_drawable_graph)

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        result = await assistant_service.get_assistant_graph(
            "test-id", False, "user-123"
        )

        assert "nodes" in result
        # Verify id was removed from node data
        assert "id" not in result["nodes"][0]["data"]

    @pytest.mark.asyncio
    async def test_get_assistant_graph_invalid_xray(self, assistant_service):
        """Test graph retrieval with invalid xray parameter"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph
        mock_graph = Mock()
        mock_graph.aget_graph.return_value = Mock()

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant_graph("test-id", -1, "user-123")

        assert exc_info.value.status_code == 422
        assert "Invalid xray value" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_assistant_graph_not_implemented(self, assistant_service):
        """Test graph retrieval with unsupported visualization"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph
        mock_graph = Mock()
        mock_graph.aget_graph.side_effect = NotImplementedError("Not supported")

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant_graph("test-id", False, "user-123")

        assert exc_info.value.status_code == 422
        assert "does not support visualization" in str(exc_info.value.detail)


class TestAssistantServiceSubgraphs:
    """Test assistant subgraph operations"""

    @pytest.mark.asyncio
    async def test_get_assistant_subgraphs_success(self, assistant_service):
        """Test successful subgraph retrieval"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph
        mock_graph = Mock()
        mock_subgraph = Mock()
        mock_subgraph.get_input_jsonschema.return_value = {"type": "object"}
        mock_subgraph.get_output_jsonschema.return_value = {"type": "object"}
        mock_subgraph.stream_channels_list = []
        mock_subgraph.channels = {}
        mock_subgraph.get_name.return_value = "State"
        mock_subgraph.config_schema.return_value = Mock()
        mock_subgraph.get_context_jsonschema.return_value = {"type": "object"}

        async def mock_aget_subgraphs(namespace=None, recurse=False):
            yield "subgraph1", mock_subgraph

        mock_graph.aget_subgraphs = mock_aget_subgraphs

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        result = await assistant_service.get_assistant_subgraphs(
            "test-id", "namespace1", True, "user-123"
        )

        assert "subgraph1" in result
        assert "input_schema" in result["subgraph1"]

    @pytest.mark.asyncio
    async def test_get_assistant_subgraphs_not_implemented(self, assistant_service):
        """Test subgraph retrieval with unsupported feature"""
        # Mock assistant
        mock_assistant = Mock()
        mock_assistant.assistant_id = "test-id"
        mock_assistant.graph_id = "test-graph"
        mock_table = Mock()
        mock_column = Mock()
        mock_column.name = "assistant_id"
        mock_table.columns = [mock_column]
        mock_assistant.__table__ = mock_table

        # Mock graph
        mock_graph = Mock()
        mock_graph.aget_subgraphs.side_effect = NotImplementedError("Not supported")

        assistant_service.session.scalar.return_value = mock_assistant
        assistant_service.langgraph_service.get_graph.return_value = mock_graph

        with pytest.raises(HTTPException) as exc_info:
            await assistant_service.get_assistant_subgraphs(
                "test-id", "namespace1", True, "user-123"
            )

        assert exc_info.value.status_code == 422
        assert "does not support subgraphs" in str(exc_info.value.detail)
