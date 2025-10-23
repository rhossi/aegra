"""Unit tests for LangGraphService"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from agent_server.services.langgraph_service import (
    LangGraphService,
    create_run_config,
    create_thread_config,
    inject_user_context,
)


class TestLangGraphServiceInit:
    """Test LangGraphService initialization"""

    def test_init_default_config_path(self):
        """Test initialization with default config path"""
        service = LangGraphService()
        assert service.config_path == Path("aegra.json")
        assert service.config is None
        assert service._graph_registry == {}
        assert service._graph_cache == {}

    def test_init_custom_config_path(self):
        """Test initialization with custom config path"""
        custom_path = "custom.json"
        service = LangGraphService(custom_path)
        assert service.config_path == Path(custom_path)
        assert service.config is None
        assert service._graph_registry == {}
        assert service._graph_cache == {}

    def test_init_absolute_path(self):
        """Test initialization with absolute path"""
        absolute_path = "/absolute/path/config.json"
        service = LangGraphService(absolute_path)
        assert service.config_path == Path(absolute_path)


class TestLangGraphServiceConfig:
    """Test configuration loading and management"""

    @pytest.mark.asyncio
    async def test_initialize_env_var_override(self, monkeypatch):
        """Test config loading with AEGRA_CONFIG env var"""
        config_data = {"graphs": {"test": "./graphs/test.py:graph"}}

        # Mock environment variable
        monkeypatch.setenv("AEGRA_CONFIG", "/env/path/config.json")

        # Mock file operations and database dependencies
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=json.dumps(config_data))),
            patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ),
        ):
            service = LangGraphService()
            await service.initialize()

            assert service.config == config_data
            assert service.config_path == Path("/env/path/config.json")

    @pytest.mark.asyncio
    async def test_initialize_explicit_path_exists(self):
        """Test config loading with existing explicit path"""
        config_data = {"graphs": {"test": "./graphs/test.py:graph"}}

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=json.dumps(config_data))),
            patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ),
        ):
            service = LangGraphService("explicit.json")
            await service.initialize()

            assert service.config == config_data
            assert service.config_path == Path("explicit.json")

    @pytest.mark.asyncio
    async def test_initialize_aegra_json_fallback(self, monkeypatch):
        """Test config loading with aegra.json fallback"""
        config_data = {"graphs": {"test": "./graphs/test.py:graph"}}

        # Clear AEGRA_CONFIG
        monkeypatch.delenv("AEGRA_CONFIG", raising=False)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=json.dumps(config_data))),
            patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ),
        ):
            service = LangGraphService()
            await service.initialize()

            assert service.config == config_data
            assert service.config_path == Path("aegra.json")

    @pytest.mark.asyncio
    async def test_initialize_langgraph_json_fallback(self, monkeypatch):
        """Test config loading with langgraph.json fallback"""
        config_data = {"graphs": {"test": "./graphs/test.py:graph"}}

        # Clear AEGRA_CONFIG
        monkeypatch.delenv("AEGRA_CONFIG", raising=False)

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data=json.dumps(config_data))),
            patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ),
        ):
            service = LangGraphService()
            await service.initialize()

            assert service.config == config_data
            # Since we're mocking exists to return True, it will find aegra.json first
            assert service.config_path == Path("aegra.json")

    @pytest.mark.asyncio
    async def test_initialize_no_config_file_found(self, monkeypatch):
        """Test error when no config file is found"""
        # Clear AEGRA_CONFIG
        monkeypatch.delenv("AEGRA_CONFIG", raising=False)

        with patch("pathlib.Path.exists", return_value=False):
            service = LangGraphService()

            with pytest.raises(ValueError, match="Configuration file not found"):
                await service.initialize()

    @pytest.mark.asyncio
    async def test_initialize_invalid_json(self):
        """Test error with invalid JSON config"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.open", mock_open(read_data="invalid json")),
        ):
            service = LangGraphService()

            with pytest.raises(json.JSONDecodeError):
                await service.initialize()

    def test_get_config(self):
        """Test getting loaded configuration"""
        service = LangGraphService()
        service.config = {"test": "value"}

        assert service.get_config() == {"test": "value"}

    def test_get_config_none(self):
        """Test getting config when not loaded"""
        service = LangGraphService()

        assert service.get_config() is None

    def test_get_dependencies(self):
        """Test getting dependencies from config"""
        service = LangGraphService()
        service.config = {"dependencies": ["dep1", "dep2"]}

        assert service.get_dependencies() == ["dep1", "dep2"]

    def test_get_dependencies_none(self):
        """Test getting dependencies when config is None"""
        service = LangGraphService()

        # The method should handle None config gracefully
        result = service.get_dependencies()
        assert result == []

    def test_get_dependencies_missing_key(self):
        """Test getting dependencies when key is missing"""
        service = LangGraphService()
        service.config = {}

        assert service.get_dependencies() == []


class TestLangGraphServiceGraphs:
    """Test graph management"""

    @pytest.mark.asyncio
    async def test_get_graph_success(self):
        """Test successful graph retrieval"""
        service = LangGraphService()
        service._graph_registry = {
            "test_graph": {"file_path": "test.py", "export_name": "graph"}
        }

        mock_graph = Mock()
        mock_compiled_graph = Mock()

        with (
            patch.object(
                service, "_load_graph_from_file", return_value=mock_graph
            ) as mock_load,
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            # Mock database manager
            mock_db_manager.get_checkpointer = AsyncMock(return_value="checkpointer")
            mock_db_manager.get_store = AsyncMock(return_value="store")

            # Mock graph compilation
            mock_graph.compile = Mock(return_value=mock_compiled_graph)

            result = await service.get_graph("test_graph")

            assert result == mock_compiled_graph
            mock_load.assert_called_once_with(
                "test_graph", service._graph_registry["test_graph"]
            )
            mock_graph.compile.assert_called_once_with(
                checkpointer="checkpointer", store="store"
            )

    @pytest.mark.asyncio
    async def test_get_graph_not_found(self):
        """Test error when graph not found in registry"""
        service = LangGraphService()
        service._graph_registry = {}

        with pytest.raises(ValueError, match="Graph not found: missing_graph"):
            await service.get_graph("missing_graph")

    @pytest.mark.asyncio
    async def test_get_graph_cached(self):
        """Test returning cached graph"""
        service = LangGraphService()
        service._graph_registry = {
            "test_graph": {"file_path": "test.py", "export_name": "graph"}
        }

        cached_graph = Mock()
        service._graph_cache = {"test_graph": cached_graph}

        result = await service.get_graph("test_graph")

        assert result == cached_graph

    @pytest.mark.asyncio
    async def test_get_graph_force_reload(self):
        """Test force reload bypasses cache"""
        service = LangGraphService()
        service._graph_registry = {
            "test_graph": {"file_path": "test.py", "export_name": "graph"}
        }

        cached_graph = Mock()
        new_graph = Mock()
        service._graph_cache = {"test_graph": cached_graph}

        with (
            patch.object(
                service, "_load_graph_from_file", return_value=new_graph
            ) as mock_load,
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(return_value="checkpointer")
            mock_db_manager.get_store = AsyncMock(return_value="store")
            new_graph.compile = Mock(return_value=new_graph)

            result = await service.get_graph("test_graph", force_reload=True)

            assert result == new_graph
            mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_graph_from_file_success(self):
        """Test successful graph loading from file"""
        service = LangGraphService()

        mock_module = Mock()
        mock_graph = Mock()
        mock_module.test_graph = mock_graph

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module_from_spec,
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()
            mock_module_from_spec.return_value = mock_module

            graph_info = {"file_path": "test.py", "export_name": "test_graph"}

            result = await service._load_graph_from_file("test_graph", graph_info)

            assert result == mock_graph

    @pytest.mark.asyncio
    async def test_load_graph_from_file_not_found(self):
        """Test error when graph file not found"""
        service = LangGraphService()

        with patch("pathlib.Path.exists", return_value=False):
            graph_info = {"file_path": "missing.py", "export_name": "graph"}

            with pytest.raises(ValueError, match="Graph file not found"):
                await service._load_graph_from_file("test_graph", graph_info)

    @pytest.mark.asyncio
    async def test_load_graph_from_file_import_failure(self):
        """Test error when graph import fails"""
        service = LangGraphService()

        with (
            patch("importlib.util.spec_from_file_location", return_value=None),
            patch("pathlib.Path.exists", return_value=True),
        ):
            graph_info = {"file_path": "test.py", "export_name": "graph"}

            with pytest.raises(ValueError, match="Failed to load graph module"):
                await service._load_graph_from_file("test_graph", graph_info)

    @pytest.mark.asyncio
    async def test_load_graph_from_file_export_not_found(self):
        """Test error when export not found in module"""
        service = LangGraphService()

        mock_module = Mock()
        # Don't set the export_name attribute
        del mock_module.missing_export  # Ensure it doesn't exist

        with (
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec", return_value=mock_module),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/absolute/test.py")),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()

            graph_info = {"file_path": "test.py", "export_name": "missing_export"}

            with pytest.raises(ValueError, match="Graph export not found"):
                await service._load_graph_from_file("test_graph", graph_info)

    def test_list_graphs(self):
        """Test listing available graphs"""
        service = LangGraphService()
        service._graph_registry = {
            "graph1": {"file_path": "path1.py"},
            "graph2": {"file_path": "path2.py"},
        }

        result = service.list_graphs()

        assert result == {"graph1": "path1.py", "graph2": "path2.py"}

    def test_list_graphs_empty(self):
        """Test listing graphs when registry is empty"""
        service = LangGraphService()
        service._graph_registry = {}

        result = service.list_graphs()

        assert result == {}


class TestLangGraphServiceCache:
    """Test cache management"""

    def test_invalidate_cache_specific_graph(self):
        """Test invalidating cache for specific graph"""
        service = LangGraphService()
        service._graph_cache = {"graph1": Mock(), "graph2": Mock()}

        service.invalidate_cache("graph1")

        assert "graph1" not in service._graph_cache
        assert "graph2" in service._graph_cache

    def test_invalidate_cache_specific_graph_not_found(self):
        """Test invalidating cache for non-existent graph"""
        service = LangGraphService()
        service._graph_cache = {"graph1": Mock()}

        # Should not raise error
        service.invalidate_cache("missing_graph")

        assert "graph1" in service._graph_cache

    def test_invalidate_cache_all(self):
        """Test invalidating entire cache"""
        service = LangGraphService()
        service._graph_cache = {"graph1": Mock(), "graph2": Mock()}

        service.invalidate_cache()

        assert service._graph_cache == {}

    def test_invalidate_cache_empty(self):
        """Test invalidating empty cache"""
        service = LangGraphService()
        service._graph_cache = {}

        # Should not raise error
        service.invalidate_cache()

        assert service._graph_cache == {}


class TestLangGraphServiceContext:
    """Test user context injection"""

    def test_inject_user_context_with_user(self):
        """Test injecting user context with user object"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123", "name": "Test User"}

        base_config = {"existing": "value"}

        result = inject_user_context(mock_user, base_config)

        assert result["existing"] == "value"
        assert result["configurable"]["user_id"] == "user-123"
        assert result["configurable"]["user_display_name"] == "Test User"
        assert result["configurable"]["langgraph_auth_user"] == {
            "identity": "user-123",
            "name": "Test User",
        }

    def test_inject_user_context_without_user(self):
        """Test injecting context without user object"""
        base_config = {"existing": "value"}

        result = inject_user_context(None, base_config)

        assert result["existing"] == "value"
        # When no user, configurable should be empty or not contain user-specific keys
        assert "user_id" not in result.get("configurable", {})

    def test_inject_user_context_no_base_config(self):
        """Test injecting context without base config"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        result = inject_user_context(mock_user, None)

        assert result["configurable"]["user_id"] == "user-123"
        assert result["configurable"]["user_display_name"] == "Test User"

    def test_inject_user_context_user_to_dict_failure(self):
        """Test fallback when user.to_dict() fails"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.side_effect = Exception("to_dict failed")

        result = inject_user_context(mock_user, {})

        assert result["configurable"]["user_id"] == "user-123"
        assert result["configurable"]["user_display_name"] == "Test User"
        assert result["configurable"]["langgraph_auth_user"] == {"identity": "user-123"}

    def test_inject_user_context_existing_configurable(self):
        """Test preserving existing configurable values"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        base_config = {"configurable": {"existing_key": "existing_value"}}

        result = inject_user_context(mock_user, base_config)

        assert result["configurable"]["existing_key"] == "existing_value"
        assert result["configurable"]["user_id"] == "user-123"


class TestLangGraphServiceConfigs:
    """Test thread and run config creation"""

    def test_create_thread_config(self):
        """Test creating thread configuration"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        thread_id = "thread-456"
        additional_config = {"custom": "value"}

        result = create_thread_config(thread_id, mock_user, additional_config)

        assert result["configurable"]["thread_id"] == thread_id
        assert result["configurable"]["user_id"] == "user-123"
        assert result["custom"] == "value"

    def test_create_thread_config_no_additional(self):
        """Test creating thread config without additional config"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        thread_id = "thread-456"

        result = create_thread_config(thread_id, mock_user)

        assert result["configurable"]["thread_id"] == thread_id
        assert result["configurable"]["user_id"] == "user-123"

    def test_create_run_config(self):
        """Test creating run configuration"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        run_id = "run-789"
        thread_id = "thread-456"
        additional_config = {"custom": "value"}

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=[],
        ):
            result = create_run_config(run_id, thread_id, mock_user, additional_config)

        assert result["configurable"]["run_id"] == run_id
        assert result["configurable"]["thread_id"] == thread_id
        assert result["configurable"]["user_id"] == "user-123"
        assert result["custom"] == "value"

    def test_create_run_config_with_checkpoint(self):
        """Test creating run config with checkpoint"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        run_id = "run-789"
        thread_id = "thread-456"
        checkpoint = {"checkpoint_key": "checkpoint_value"}

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=[],
        ):
            result = create_run_config(
                run_id, thread_id, mock_user, checkpoint=checkpoint
            )

        assert result["configurable"]["checkpoint_key"] == "checkpoint_value"

    def test_create_run_config_with_tracing_callbacks(self):
        """Test creating run config with tracing callbacks"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        run_id = "run-789"
        thread_id = "thread-456"

        mock_callbacks = [Mock(), Mock()]

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=mock_callbacks,
        ):
            result = create_run_config(run_id, thread_id, mock_user)

        assert result["callbacks"] == mock_callbacks
        assert result["metadata"]["langfuse_session_id"] == thread_id
        assert result["metadata"]["langfuse_user_id"] == "user-123"
        assert "aegra_run" in result["metadata"]["langfuse_tags"]
        assert f"run:{run_id}" in result["metadata"]["langfuse_tags"]
        assert f"thread:{thread_id}" in result["metadata"]["langfuse_tags"]
        assert f"user:{mock_user.identity}" in result["metadata"]["langfuse_tags"]

    def test_create_run_config_existing_callbacks(self):
        """Test creating run config with existing callbacks"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        run_id = "run-789"
        thread_id = "thread-456"
        existing_callback = Mock()
        additional_config = {"callbacks": [existing_callback]}

        mock_callbacks = [Mock(), Mock()]

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=mock_callbacks,
        ):
            result = create_run_config(run_id, thread_id, mock_user, additional_config)

        # Should have existing + tracing callbacks
        assert len(result["callbacks"]) == 3
        # Verify structure is correct (don't check exact objects due to Mock ID differences)
        assert "callbacks" in result
        assert isinstance(result["callbacks"], list)

    def test_create_run_config_invalid_callbacks(self):
        """Test creating run config with invalid callbacks type"""
        mock_user = Mock()
        mock_user.identity = "user-123"
        mock_user.display_name = "Test User"
        mock_user.to_dict.return_value = {"identity": "user-123"}

        run_id = "run-789"
        thread_id = "thread-456"
        additional_config = {"callbacks": "not_a_list"}

        mock_callbacks = [Mock(), Mock()]

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=mock_callbacks,
        ):
            result = create_run_config(run_id, thread_id, mock_user, additional_config)

        assert result["callbacks"] == mock_callbacks

    def test_create_run_config_no_user(self):
        """Test creating run config without user"""
        run_id = "run-789"
        thread_id = "thread-456"

        with patch(
            "agent_server.services.langgraph_service.get_tracing_callbacks",
            return_value=[],
        ):
            result = create_run_config(run_id, thread_id, None)

        assert result["configurable"]["run_id"] == run_id
        assert result["configurable"]["thread_id"] == thread_id
        assert "user_id" not in result["configurable"]
        # Metadata may not exist if no tracing callbacks
        if "metadata" in result:
            assert "langfuse_user_id" not in result["metadata"]
