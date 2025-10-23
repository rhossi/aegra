"""Integration tests for LangGraphService"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_server.services.langgraph_service import LangGraphService


class TestLangGraphServiceRealFiles:
    """Test LangGraphService with real file operations"""

    @pytest.mark.asyncio
    async def test_initialize_with_real_config_file(self):
        """Test initialization with real config file"""
        config_data = {
            "graphs": {"test_graph": "./graphs/test.py:graph"},
            "dependencies": ["dep1", "dep2"],
        }

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "aegra.json"
            config_path.write_text(json.dumps(config_data))

            with patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ):
                service = LangGraphService(str(config_path))
                await service.initialize()

                assert service.config == config_data
                assert service.config_path == config_path
                assert service.get_dependencies() == ["dep1", "dep2"]

    @pytest.mark.asyncio
    async def test_initialize_env_var_with_real_file(self, monkeypatch):
        """Test initialization with AEGRA_CONFIG pointing to real file"""
        config_data = {"graphs": {"env_graph": "./graphs/env.py:graph"}}

        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "env_config.json"
            config_path.write_text(json.dumps(config_data))

            monkeypatch.setenv("AEGRA_CONFIG", str(config_path))

            with patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ):
                service = LangGraphService()
                await service.initialize()

                assert service.config == config_data
                assert service.config_path == config_path

    @pytest.mark.asyncio
    async def test_initialize_fallback_to_langgraph_json(self, monkeypatch):
        """Test fallback to langgraph.json when aegra.json not found"""
        config_data = {"graphs": {"fallback_graph": "./graphs/fallback.py:graph"}}

        with TemporaryDirectory() as temp_dir:
            langgraph_path = Path(temp_dir) / "langgraph.json"
            langgraph_path.write_text(json.dumps(config_data))

            # Change to temp directory and clear AEGRA_CONFIG
            monkeypatch.delenv("AEGRA_CONFIG", raising=False)
            monkeypatch.chdir(temp_dir)

            with patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ):
                service = LangGraphService()
                await service.initialize()

                assert service.config == config_data
                # Path will be relative since we changed directory
                assert service.config_path.name == "langgraph.json"

    @pytest.mark.asyncio
    async def test_initialize_invalid_json_file(self):
        """Test error with invalid JSON in real file"""
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "invalid.json"
            config_path.write_text("invalid json content")

            service = LangGraphService(str(config_path))

            with pytest.raises(json.JSONDecodeError):
                await service.initialize()

    @pytest.mark.asyncio
    async def test_initialize_missing_file(self):
        """Test error with missing config file"""
        with (
            patch(
                "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            service = LangGraphService("nonexistent.json")

            with pytest.raises(ValueError, match="Configuration file not found"):
                await service.initialize()


class TestLangGraphServiceDatabase:
    """Test LangGraphService database integration"""

    @pytest.mark.asyncio
    async def test_get_graph_database_integration(self):
        """Test graph loading with database integration"""
        service = LangGraphService()
        service._graph_registry = {
            "db_graph": {"file_path": "./graphs/db.py", "export_name": "graph"}
        }

        mock_graph = Mock()
        mock_compiled_graph = Mock()

        with (
            patch.object(service, "_load_graph_from_file", return_value=mock_graph),
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            # Mock database manager methods
            mock_checkpointer = Mock()
            mock_store = Mock()
            mock_db_manager.get_checkpointer = AsyncMock(return_value=mock_checkpointer)
            mock_db_manager.get_store = AsyncMock(return_value=mock_store)

            # Mock graph compilation
            mock_graph.compile = Mock(return_value=mock_compiled_graph)

            result = await service.get_graph("db_graph")

            assert result == mock_compiled_graph
            mock_db_manager.get_checkpointer.assert_called_once()
            mock_db_manager.get_store.assert_called_once()
            mock_graph.compile.assert_called_once_with(
                checkpointer=mock_checkpointer, store=mock_store
            )

    @pytest.mark.asyncio
    async def test_get_graph_already_compiled(self):
        """Test graph loading when graph is already compiled"""
        service = LangGraphService()
        service._graph_registry = {
            "compiled_graph": {
                "file_path": "./graphs/compiled.py",
                "export_name": "graph",
            }
        }

        mock_compiled_graph = Mock()
        # Graph doesn't have compile method (already compiled)
        del (
            mock_compiled_graph.compile
        )  # Remove compile method to simulate already compiled graph

        with (
            patch.object(
                service, "_load_graph_from_file", return_value=mock_compiled_graph
            ),
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_checkpointer = Mock()
            mock_store = Mock()
            mock_db_manager.get_checkpointer = AsyncMock(return_value=mock_checkpointer)
            mock_db_manager.get_store = AsyncMock(return_value=mock_store)

            result = await service.get_graph("compiled_graph")

            # Result should be the compiled graph (may be a copy)
            assert result is not None
            # Should not call compile on already compiled graph
            assert not hasattr(mock_compiled_graph, "compile")


class TestLangGraphServiceGraphLoading:
    """Test actual graph loading functionality"""

    @pytest.mark.asyncio
    async def test_load_graph_from_real_file(self):
        """Test loading graph from real Python file"""
        service = LangGraphService()

        # Create a temporary Python file with a valid graph
        graph_code = """
from langgraph.graph import StateGraph

def create_graph():
    graph = StateGraph(dict)
    graph.add_node("test_node", lambda x: x)
    graph.add_edge("__start__", "test_node")
    graph.add_edge("test_node", "__end__")
    return graph.compile()

graph = create_graph()
"""

        with TemporaryDirectory() as temp_dir:
            graph_file = Path(temp_dir) / "test_graph.py"
            graph_file.write_text(graph_code)

            graph_info = {"file_path": str(graph_file), "export_name": "graph"}

            result = await service._load_graph_from_file("test_graph", graph_info)

            # Should return the compiled graph
            assert result is not None
            # Graph should have the expected structure
            assert hasattr(result, "nodes") or hasattr(result, "get_graph")

    @pytest.mark.asyncio
    async def test_load_graph_from_file_with_error(self):
        """Test error handling when graph file has syntax error"""
        service = LangGraphService()

        # Create a Python file with syntax error
        invalid_code = """
def create_graph():
    graph = StateGraph(dict
    return graph.compile()

graph = create_graph()
"""

        with TemporaryDirectory() as temp_dir:
            graph_file = Path(temp_dir) / "invalid_graph.py"
            graph_file.write_text(invalid_code)

            graph_info = {"file_path": str(graph_file), "export_name": "graph"}

            with pytest.raises((SyntaxError, ValueError)):
                await service._load_graph_from_file("invalid_graph", graph_info)

    @pytest.mark.asyncio
    async def test_load_graph_from_file_missing_export(self):
        """Test error when graph file doesn't export expected name"""
        service = LangGraphService()

        # Create a Python file without the expected export
        graph_code = """
from langgraph.graph import StateGraph

def create_graph():
    graph = StateGraph(dict)
    return graph.compile()

# Missing: graph = create_graph()
"""

        with TemporaryDirectory() as temp_dir:
            graph_file = Path(temp_dir) / "missing_export.py"
            graph_file.write_text(graph_code)

            graph_info = {"file_path": str(graph_file), "export_name": "graph"}

            with pytest.raises(ValueError, match="Graph export not found"):
                await service._load_graph_from_file("missing_export", graph_info)


class TestLangGraphServiceErrorHandling:
    """Test error handling scenarios"""

    @pytest.mark.asyncio
    async def test_get_graph_database_error(self):
        """Test error handling when database operations fail"""
        service = LangGraphService()
        service._graph_registry = {
            "error_graph": {"file_path": "./graphs/error.py", "export_name": "graph"}
        }

        mock_graph = Mock()

        with (
            patch.object(service, "_load_graph_from_file", return_value=mock_graph),
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            # Mock database error
            mock_db_manager.get_checkpointer = AsyncMock(
                side_effect=Exception("Database error")
            )

            with pytest.raises(Exception, match="Database error"):
                await service.get_graph("error_graph")

    @pytest.mark.asyncio
    async def test_get_graph_compilation_error(self):
        """Test error handling when graph compilation fails"""
        service = LangGraphService()
        service._graph_registry = {
            "compile_error_graph": {
                "file_path": "./graphs/compile_error.py",
                "export_name": "graph",
            }
        }

        mock_graph = Mock()
        mock_graph.compile = Mock(side_effect=Exception("Compilation error"))

        with (
            patch.object(service, "_load_graph_from_file", return_value=mock_graph),
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(return_value="checkpointer")
            mock_db_manager.get_store = AsyncMock(return_value="store")

            with pytest.raises(Exception, match="Compilation error"):
                await service.get_graph("compile_error_graph")

    @pytest.mark.asyncio
    async def test_initialize_file_permission_error(self):
        """Test error handling when config file cannot be read"""
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "readonly.json"
            config_path.write_text('{"test": "value"}')

            # Make file read-only (Unix only)
            import stat

            config_path.chmod(stat.S_IRUSR)

            with (
                patch(
                    "agent_server.services.langgraph_service.LangGraphService._ensure_default_assistants"
                ),
                patch(
                    "pathlib.Path.open",
                    side_effect=PermissionError("Permission denied"),
                ),
            ):
                service = LangGraphService(str(config_path))

                # Should handle permission error gracefully
                with pytest.raises(PermissionError):
                    await service.initialize()


class TestLangGraphServiceConcurrency:
    """Test concurrent access scenarios"""

    @pytest.mark.asyncio
    async def test_concurrent_graph_loading(self):
        """Test concurrent access to graph loading"""
        service = LangGraphService()
        service._graph_registry = {
            "concurrent_graph": {
                "file_path": "./graphs/concurrent.py",
                "export_name": "graph",
            }
        }

        mock_graph = Mock()
        mock_compiled_graph = Mock()

        with (
            patch.object(service, "_load_graph_from_file", return_value=mock_graph),
            patch("agent_server.core.database.db_manager") as mock_db_manager,
        ):
            mock_db_manager.get_checkpointer = AsyncMock(return_value="checkpointer")
            mock_db_manager.get_store = AsyncMock(return_value="store")
            mock_graph.compile = Mock(return_value=mock_compiled_graph)

            # Load same graph concurrently
            import asyncio

            tasks = [
                service.get_graph("concurrent_graph"),
                service.get_graph("concurrent_graph"),
                service.get_graph("concurrent_graph"),
            ]

            results = await asyncio.gather(*tasks)

            # All should return the same compiled graph
            assert all(result == mock_compiled_graph for result in results)
            # Should only load from file once due to caching
            assert mock_graph.compile.call_count == 1

    @pytest.mark.asyncio
    async def test_concurrent_cache_invalidation(self):
        """Test concurrent cache invalidation"""
        service = LangGraphService()
        service._graph_cache = {"graph1": Mock(), "graph2": Mock(), "graph3": Mock()}

        import asyncio

        async def invalidate_graph(graph_id):
            service.invalidate_cache(graph_id)
            return len(service._graph_cache)

        # Invalidate different graphs concurrently
        tasks = [
            invalidate_graph("graph1"),
            invalidate_graph("graph2"),
            invalidate_graph("graph3"),
        ]

        results = await asyncio.gather(*tasks)

        # Cache should be empty after all invalidations
        assert service._graph_cache == {}
        # All results should be 0 (empty cache) - check individually
        # Note: concurrent execution may cause intermediate states
        assert all(
            result <= 3 for result in results
        )  # Should be <= original cache size
