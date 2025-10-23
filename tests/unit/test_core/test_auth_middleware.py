"""Unit tests for auth middleware"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from starlette.authentication import AuthCredentials, AuthenticationError
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from agent_server.core.auth_middleware import (
    LangGraphAuthBackend,
    LangGraphUser,
    get_auth_backend,
    on_auth_error,
)


class TestLangGraphUser:
    """Test LangGraphUser class"""

    def test_user_initialization(self):
        """Test user initialization with user data"""
        user_data = {
            "identity": "user-123",
            "display_name": "Test User",
            "is_authenticated": True,
            "email": "test@example.com",
        }

        user = LangGraphUser(user_data)

        assert user.identity == "user-123"
        assert user.display_name == "Test User"
        assert user.is_authenticated is True

    def test_user_identity_property(self):
        """Test identity property"""
        user_data = {"identity": "test-identity"}
        user = LangGraphUser(user_data)

        assert user.identity == "test-identity"

    def test_user_display_name_default(self):
        """Test display_name defaults to identity"""
        user_data = {"identity": "test-identity"}
        user = LangGraphUser(user_data)

        assert user.display_name == "test-identity"

    def test_user_display_name_custom(self):
        """Test custom display_name"""
        user_data = {"identity": "test-identity", "display_name": "Custom Name"}
        user = LangGraphUser(user_data)

        assert user.display_name == "Custom Name"

    def test_user_is_authenticated_default(self):
        """Test is_authenticated defaults to True"""
        user_data = {"identity": "test-identity"}
        user = LangGraphUser(user_data)

        assert user.is_authenticated is True

    def test_user_is_authenticated_custom(self):
        """Test custom is_authenticated value"""
        user_data = {"identity": "test-identity", "is_authenticated": False}
        user = LangGraphUser(user_data)

        assert user.is_authenticated is False

    def test_user_getattr_existing_field(self):
        """Test __getattr__ with existing field"""
        user_data = {"identity": "test-identity", "email": "test@example.com"}
        user = LangGraphUser(user_data)

        assert user.email == "test@example.com"

    def test_user_getattr_nonexistent_field(self):
        """Test __getattr__ with non-existent field"""
        user_data = {"identity": "test-identity"}
        user = LangGraphUser(user_data)

        with pytest.raises(AttributeError, match="no attribute 'nonexistent'"):
            _ = user.nonexistent

    def test_user_to_dict(self):
        """Test to_dict method"""
        user_data = {
            "identity": "test-identity",
            "display_name": "Test User",
            "email": "test@example.com",
        }
        user = LangGraphUser(user_data)

        result = user.to_dict()

        assert result == user_data
        assert result is not user_data  # Should be a copy


class TestLangGraphAuthBackend:
    """Test LangGraphAuthBackend class"""

    def test_backend_initialization(self):
        """Test backend initialization"""
        with patch.object(
            LangGraphAuthBackend, "_load_auth_instance", return_value=None
        ):
            backend = LangGraphAuthBackend()
            assert backend.auth_instance is None

    def test_load_auth_instance_success(self):
        """Test successful auth instance loading"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock()

        with patch.object(
            LangGraphAuthBackend, "_load_auth_instance", return_value=mock_auth_instance
        ):
            backend = LangGraphAuthBackend()

            assert backend.auth_instance == mock_auth_instance

    def test_load_auth_instance_file_not_found(self):
        """Test auth instance loading when file doesn't exist"""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.cwd", return_value=Path("/test")),
        ):
            backend = LangGraphAuthBackend()

            assert backend.auth_instance is None

    def test_load_auth_instance_spec_failure(self):
        """Test auth instance loading when spec creation fails"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.cwd", return_value=Path("/test")),
            patch("importlib.util.spec_from_file_location", return_value=None),
        ):
            backend = LangGraphAuthBackend()

            assert backend.auth_instance is None

    def test_load_auth_instance_no_auth_attribute(self):
        """Test auth instance loading when module has no auth attribute"""
        mock_module = Mock()
        mock_module.auth = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.cwd", return_value=Path("/test")),
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec", return_value=mock_module),
            patch("sys.modules", {}),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()

            backend = LangGraphAuthBackend()

            assert backend.auth_instance is None

    def test_load_auth_instance_invalid_auth_type(self):
        """Test auth instance loading when auth is not Auth instance"""
        mock_module = Mock()
        mock_module.auth = "not_an_auth_instance"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.cwd", return_value=Path("/test")),
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec", return_value=mock_module),
            patch("sys.modules", {}),
        ):
            mock_spec.return_value = Mock()
            mock_spec.return_value.loader = Mock()

            backend = LangGraphAuthBackend()

            assert backend.auth_instance is None

    def test_load_auth_instance_exception(self):
        """Test auth instance loading when exception occurs"""
        with patch("pathlib.Path.exists", side_effect=Exception("Test error")):
            backend = LangGraphAuthBackend()

            assert backend.auth_instance is None

    @pytest.mark.asyncio
    async def test_authenticate_no_auth_instance(self):
        """Test authentication when no auth instance is available"""
        backend = LangGraphAuthBackend()
        backend.auth_instance = None

        mock_conn = Mock(spec=HTTPConnection)

        result = await backend.authenticate(mock_conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_no_handler(self):
        """Test authentication when no handler is configured"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = None

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)

        result = await backend.authenticate(mock_conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Test successful authentication"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            return_value={
                "identity": "user-123",
                "display_name": "Test User",
                "permissions": ["read", "write"],
            }
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {
            "authorization": b"Bearer token123",
            "content-type": b"application/json",
        }

        credentials, user = await backend.authenticate(mock_conn)

        assert isinstance(credentials, AuthCredentials)
        assert credentials.scopes == ["read", "write"]
        assert isinstance(user, LangGraphUser)
        assert user.identity == "user-123"
        assert user.display_name == "Test User"

    @pytest.mark.asyncio
    async def test_authenticate_success_string_permissions(self):
        """Test authentication with string permissions"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            return_value={"identity": "user-123", "permissions": "admin"}
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {"authorization": b"Bearer token123"}

        credentials, user = await backend.authenticate(mock_conn)

        assert credentials.scopes == ["admin"]

    @pytest.mark.asyncio
    async def test_authenticate_invalid_user_data(self):
        """Test authentication with invalid user data"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(return_value=None)

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {"authorization": b"Bearer token123"}

        with pytest.raises(AuthenticationError, match="Authentication system error"):
            await backend.authenticate(mock_conn)

    @pytest.mark.asyncio
    async def test_authenticate_missing_identity(self):
        """Test authentication with missing identity field"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            return_value={"display_name": "Test User"}
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {"authorization": b"Bearer token123"}

        with pytest.raises(AuthenticationError, match="Authentication system error"):
            await backend.authenticate(mock_conn)

    @pytest.mark.asyncio
    async def test_authenticate_http_exception(self):
        """Test authentication with HTTP exception"""
        mock_auth_instance = Mock()

        # Create a mock exception with detail attribute
        mock_http_exception = Exception("Auth failed")
        mock_http_exception.detail = "Invalid token"
        mock_auth_instance._authenticate_handler = AsyncMock(
            side_effect=mock_http_exception
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        # Mock the Auth.exceptions.HTTPException to be the same as our exception
        with patch("agent_server.core.auth_middleware.Auth") as mock_auth:
            mock_auth.exceptions.HTTPException = Exception

            mock_conn = Mock(spec=HTTPConnection)
            mock_conn.headers = {"authorization": b"Bearer token123"}

            with pytest.raises(AuthenticationError, match="Invalid token"):
                await backend.authenticate(mock_conn)

    @pytest.mark.asyncio
    async def test_authenticate_headers_conversion(self):
        """Test header conversion for different types"""
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            return_value={"identity": "user-123"}
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {
            b"authorization": b"Bearer token123",  # bytes key and value
            "content-type": "application/json",  # str key and value
            b"user-agent": "test-agent",  # bytes key, str value
        }

        await backend.authenticate(mock_conn)

        # Verify headers were converted properly
        expected_headers = {
            "authorization": "Bearer token123",
            "content-type": "application/json",
            "user-agent": "test-agent",
        }
        mock_auth_instance._authenticate_handler.assert_called_once_with(
            expected_headers
        )


class TestGetAuthBackend:
    """Test get_auth_backend function"""

    def test_get_auth_backend_noop(self):
        """Test getting auth backend with noop type"""
        with patch.dict(os.environ, {"AUTH_TYPE": "noop"}):
            backend = get_auth_backend()
            assert isinstance(backend, LangGraphAuthBackend)

    def test_get_auth_backend_custom(self):
        """Test getting auth backend with custom type"""
        with patch.dict(os.environ, {"AUTH_TYPE": "custom"}):
            backend = get_auth_backend()
            assert isinstance(backend, LangGraphAuthBackend)

    def test_get_auth_backend_unknown(self):
        """Test getting auth backend with unknown type"""
        with patch.dict(os.environ, {"AUTH_TYPE": "unknown"}):
            backend = get_auth_backend()
            assert isinstance(backend, LangGraphAuthBackend)

    def test_get_auth_backend_default(self):
        """Test getting auth backend with no AUTH_TYPE set"""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_auth_backend()
            assert isinstance(backend, LangGraphAuthBackend)


class TestOnAuthError:
    """Test on_auth_error function"""

    def test_on_auth_error_response(self):
        """Test auth error response format"""
        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.url = "http://example.com/api/test"

        exc = AuthenticationError("Invalid credentials")

        response = on_auth_error(mock_conn, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 401

        # Check response content structure
        content = response.body.decode()
        assert '"error":"unauthorized"' in content
        assert '"message":"Invalid credentials"' in content
        assert '"authentication_required":true' in content

    def test_on_auth_error_different_message(self):
        """Test auth error with different message"""
        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.url = "http://example.com/api/test"

        exc = AuthenticationError("Token expired")

        response = on_auth_error(mock_conn, exc)

        content = response.body.decode()
        assert '"message":"Token expired"' in content

    def test_on_auth_error_empty_message(self):
        """Test auth error with empty message"""
        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.url = "http://example.com/api/test"

        exc = AuthenticationError("")

        response = on_auth_error(mock_conn, exc)

        content = response.body.decode()
        assert '"message":""' in content


class TestAuthMiddlewareIntegration:
    """Test auth middleware integration scenarios"""

    @pytest.mark.asyncio
    async def test_full_authentication_flow(self):
        """Test complete authentication flow"""
        # Mock auth instance
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            return_value={
                "identity": "user-123",
                "display_name": "Test User",
                "email": "test@example.com",
                "permissions": ["read", "write", "admin"],
            }
        )

        # Create backend
        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        # Mock connection
        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {
            "authorization": "Bearer valid-token",
            "content-type": "application/json",
        }

        # Authenticate
        credentials, user = await backend.authenticate(mock_conn)

        # Verify results
        assert isinstance(credentials, AuthCredentials)
        assert credentials.scopes == ["read", "write", "admin"]

        assert isinstance(user, LangGraphUser)
        assert user.identity == "user-123"
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"
        assert user.is_authenticated is True

        # Test user dict conversion
        user_dict = user.to_dict()
        assert user_dict["identity"] == "user-123"
        assert user_dict["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_authentication_error_flow(self):
        """Test authentication error handling flow"""
        # Mock auth instance that raises exception
        mock_auth_instance = Mock()
        mock_auth_instance._authenticate_handler = AsyncMock(
            side_effect=Exception("Invalid token")
        )

        backend = LangGraphAuthBackend()
        backend.auth_instance = mock_auth_instance

        mock_conn = Mock(spec=HTTPConnection)
        mock_conn.headers = {"authorization": "Bearer invalid-token"}

        # Should raise AuthenticationError
        with pytest.raises(AuthenticationError):
            await backend.authenticate(mock_conn)

        # Test error response
        exc = AuthenticationError("Invalid token")
        response = on_auth_error(mock_conn, exc)

        assert response.status_code == 401
        content = response.body.decode()
        assert '"error":"unauthorized"' in content
        assert '"message":"Invalid token"' in content
