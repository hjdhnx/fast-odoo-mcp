"""Tests for FastMCP server foundation and lifecycle.

This module tests the basic server structure, initialization,
lifecycle management, and connection to Odoo.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from fast_odoo_mcp.config import OdooConfig
from fast_odoo_mcp.odoo_connection import OdooConnectionError
from fast_odoo_mcp.server import SERVER_VERSION, OdooMCPServer


class TestServerFoundation:
    """Test the basic FastMCP server foundation."""

    @pytest.fixture
    def valid_config(self):
        """Create a valid test configuration."""
        return OdooConfig(
            url=os.getenv("ODOO_URL", "http://localhost:8069"),
            api_key="test_api_key_12345",
            database="test_db",
            log_level="INFO",
            default_limit=10,
            max_limit=100,
        )

    @pytest.fixture
    def server_with_mock_connection(self, valid_config):
        """Create server with mocked managed connection."""
        server = OdooMCPServer(valid_config)
        mock_connection = Mock()
        mock_connection.is_connected = True
        mock_connection.is_authenticated = True
        mock_connection.database = "test_db"
        mock_connection.connect = Mock()
        mock_connection.authenticate = Mock()
        mock_connection.disconnect = Mock()
        mock_access_controller = Mock()

        def ensure_connected():
            mock_connection.connect()
            mock_connection.authenticate()
            return mock_connection, mock_access_controller

        def close():
            if server.connection is not None:
                mock_connection.disconnect()

        manager = Mock()
        manager.ensure_connected.side_effect = ensure_connected
        manager.close.side_effect = close
        manager.performance_manager = None
        manager.get_health_status.return_value = {
            "connected": False,
            "authenticated": False,
            "api_version": valid_config.api_version,
            "database": None,
            "reconnect_count": 0,
            "operation_count": 0,
            "retry_count": 0,
            "last_connect_at": None,
            "last_error_at": None,
            "last_error": None,
            "uptime_seconds": 0,
            "performance": None,
        }
        server.connection_manager = manager
        server._mock_connection = mock_connection
        server._mock_access_controller = mock_access_controller
        yield server

    def test_server_initialization(self, valid_config):
        """Test basic server initialization."""
        server = OdooMCPServer(valid_config)

        assert server.config == valid_config
        assert server.connection is None  # Not connected until run
        assert server.app is not None
        assert server.app.name == "odoo-mcp-server"

    def test_server_initialization_with_env_config(self, monkeypatch, tmp_path):
        """Test server initialization loading config from environment."""
        # Reset config singleton first
        from fast_odoo_mcp.config import reset_config

        reset_config()

        # Set up environment variables
        monkeypatch.setenv("ODOO_URL", "http://test.odoo.com")
        monkeypatch.setenv("ODOO_API_KEY", "env_test_key")
        monkeypatch.setenv("ODOO_DB", "env_test_db")

        try:
            # Create server without explicit config
            server = OdooMCPServer()

            assert server.config.url == "http://test.odoo.com"
            assert server.config.api_key == "env_test_key"
            assert server.config.database == "env_test_db"
        finally:
            # Reset config for other tests
            reset_config()

    def test_server_version(self):
        """Test server version is a valid semver string."""
        parts = SERVER_VERSION.split(".")
        assert len(parts) == 3, f"Expected semver format x.y.z, got {SERVER_VERSION}"
        assert all(p.isdigit() for p in parts), (
            f"Expected numeric semver parts, got {SERVER_VERSION}"
        )

    def test_ensure_connection_success(self, server_with_mock_connection):
        """Test successful connection establishment."""
        server = server_with_mock_connection

        # Ensure connection
        server._ensure_connection()

        # Verify connection was requested through the manager
        assert server.connection_manager.ensure_connected.call_count == 1
        server._mock_connection.connect.assert_called_once()
        server._mock_connection.authenticate.assert_called_once()

        # Verify connection is stored
        assert server.connection == server._mock_connection
        assert server.access_controller is not None

    def test_ensure_connection_failure(self, server_with_mock_connection):
        """Test connection establishment failure."""
        server = server_with_mock_connection

        # Make connection fail
        server.connection_manager.ensure_connected.side_effect = OdooConnectionError(
            "Connection failed"
        )

        # Ensure connection should raise an error
        with pytest.raises(OdooConnectionError, match="Connection failed"):
            server._ensure_connection()

    def test_cleanup_connection(self, server_with_mock_connection):
        """Test connection cleanup."""
        server = server_with_mock_connection

        # First establish connection
        server._ensure_connection()
        assert server.connection is not None

        # Clean up
        server._cleanup_connection()

        # Verify connection was closed
        server._mock_connection.disconnect.assert_called_once()
        assert server.connection is None
        assert server.access_controller is None
        assert server.resource_handler is None

    def test_cleanup_connection_without_connection(self, server_with_mock_connection):
        """Test cleanup when no connection exists."""
        server = server_with_mock_connection

        # Should not raise an error
        server._cleanup_connection()

        # Connection disconnect should not be called
        server._mock_connection.disconnect.assert_not_called()

    def test_cleanup_connection_with_error(self, server_with_mock_connection):
        """Test cleanup when disconnect raises an error."""
        server = server_with_mock_connection

        # Establish connection first
        server._ensure_connection()

        # Make disconnect raise an error
        server._mock_connection.disconnect.side_effect = Exception("Disconnect failed")

        # Should not raise an error (error is logged)
        server._cleanup_connection()

        # Verify disconnect was attempted
        server._mock_connection.disconnect.assert_called_once()
        # Connection should still be cleared
        assert server.connection is None
        assert server.access_controller is None
        assert server.resource_handler is None

    @pytest.mark.asyncio
    async def test_run_stdio_success(self, server_with_mock_connection):
        """Test successful run_stdio execution via lifespan."""
        server = server_with_mock_connection

        # Make run_stdio_async invoke the lifespan like real FastMCP does
        async def mock_run_with_lifespan():
            async with server._odoo_lifespan(server.app):
                pass

        with patch("fast_odoo_mcp.server.register_resources", return_value=Mock()):
            with patch("fast_odoo_mcp.server.register_tools", return_value=Mock()):
                server.app.run_stdio_async = mock_run_with_lifespan
                await server.run_stdio()

        # Verify connection lifecycle was executed
        server._mock_connection.connect.assert_called_once()
        server._mock_connection.authenticate.assert_called_once()
        server._mock_connection.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_stdio_connection_failure(self, server_with_mock_connection):
        """Test run_stdio with connection failure — cleanup still runs."""
        server = server_with_mock_connection

        # Make connection fail
        server.connection_manager.ensure_connected.side_effect = OdooConnectionError(
            "Failed to connect"
        )

        # Make run_stdio_async invoke the lifespan (which will fail on connect)
        async def mock_run_that_invokes_lifespan():
            async with server._odoo_lifespan(server.app):
                pass

        server.app.run_stdio_async = mock_run_that_invokes_lifespan

        # Should raise since lifespan will fail on _ensure_connection
        with pytest.raises(OdooConnectionError, match="Failed to connect"):
            await server.run_stdio()

        # Cleanup should not disconnect an uninitialized connection
        server._mock_connection.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_stdio_keyboard_interrupt(self, server_with_mock_connection):
        """Test run_stdio with keyboard interrupt."""
        server = server_with_mock_connection

        # Mock the FastMCP run_stdio_async to raise KeyboardInterrupt
        server.app.run_stdio_async = AsyncMock(side_effect=KeyboardInterrupt)

        # Should not raise (handled gracefully)
        await server.run_stdio()

        # Verify cleanup ran despite interrupt
        assert server.connection is None

    @pytest.mark.asyncio
    async def test_lifespan_setup_and_teardown(self, server_with_mock_connection):
        """Test that lifespan context manager handles setup and teardown."""
        server = server_with_mock_connection

        with patch("fast_odoo_mcp.server.register_resources") as mock_register_res:
            with patch("fast_odoo_mcp.server.register_tools") as mock_register_tools:
                mock_register_res.return_value = Mock()
                mock_register_tools.return_value = Mock()

                # Use the lifespan context manager
                async with server._odoo_lifespan(server.app) as state:
                    # Verify setup was called
                    server._mock_connection.connect.assert_called_once()
                    server._mock_connection.authenticate.assert_called_once()
                    mock_register_res.assert_called_once()
                    mock_register_tools.assert_called_once()

                    # State should be an empty dict
                    assert state == {}

                # Lifespan no longer closes the managed connection on normal exit.
                server._mock_connection.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_cleanup_on_setup_failure(self, server_with_mock_connection):
        """Test that lifespan cleans up if setup fails after connection is created."""
        server = server_with_mock_connection

        # Connection succeeds but authenticate fails
        server._mock_connection.authenticate.side_effect = OdooConnectionError("Auth failed")

        with pytest.raises(OdooConnectionError, match="Auth failed"):
            async with server._odoo_lifespan(server.app):
                pass

        # Cleanup should not disconnect an uninitialized connection
        server._mock_connection.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_teardown_exception_swallowed(self, server_with_mock_connection):
        """Test that lifespan teardown exceptions are swallowed gracefully."""
        server = server_with_mock_connection

        with patch("fast_odoo_mcp.server.register_resources", return_value=Mock()):
            with patch("fast_odoo_mcp.server.register_tools", return_value=Mock()):
                async with server._odoo_lifespan(server.app):
                    pass
                assert server.connection is server._mock_connection

    def test_get_model_names_returns_list(self, server_with_mock_connection):
        """Test _get_model_names returns model name strings."""
        server = server_with_mock_connection

        # Set up connection and access controller
        mock_ac = server._mock_access_controller
        mock_ac.get_enabled_models.return_value = [
            {"model": "res.partner", "name": "Contact"},
            {"model": "sale.order", "name": "Sales Order"},
        ]

        server._ensure_connection()

        # Get model names
        names = server._get_model_names()
        assert names == ["res.partner", "sale.order"]

    def test_get_model_names_no_access_controller(self, valid_config):
        """Test _get_model_names returns empty list when no access controller."""
        server = OdooMCPServer(valid_config)

        # No connection/access controller set up
        names = server._get_model_names()
        assert names == []

    def test_get_model_names_exception_returns_empty(self, server_with_mock_connection):
        """Test _get_model_names returns empty list on exception."""
        server = server_with_mock_connection

        mock_ac = server._mock_access_controller
        mock_ac.get_enabled_models.side_effect = RuntimeError("boom")
        server._ensure_connection()

        names = server._get_model_names()
        assert names == []

    def test_get_model_names_yolo_mode_fallback(self, server_with_mock_connection):
        """Test _get_model_names queries ir.model when get_enabled_models returns []."""
        server = server_with_mock_connection

        mock_ac = server._mock_access_controller
        mock_ac.get_enabled_models.return_value = []  # YOLO mode returns []
        server._ensure_connection()

        # Mock the connection's search_read for ir.model fallback
        server._mock_connection.is_authenticated = True
        server._mock_connection.search_read.return_value = [
            {"model": "res.partner"},
            {"model": "sale.order"},
        ]

        names = server._get_model_names()
        assert names == ["res.partner", "sale.order"]
        server._mock_connection.search_read.assert_called_once_with(
            "ir.model", [], ["model"], limit=200
        )

    @pytest.mark.asyncio
    async def test_completion_handler_partial_match(self, valid_config):
        """Test that the registered completion handler filters by partial match."""
        import mcp.types as types

        server = OdooMCPServer(valid_config)
        server.access_controller = Mock()
        server.access_controller.get_enabled_models.return_value = [
            {"model": "res.partner"},
            {"model": "res.users"},
            {"model": "sale.order"},
        ]

        # Build a real CompleteRequest and invoke the registered handler
        handler = server.app._mcp_server.request_handlers[types.CompleteRequest]
        req = types.CompleteRequest(
            method="completion/complete",
            params=types.CompleteRequestParams(
                ref=types.PromptReference(type="ref/prompt", name="test"),
                argument=types.CompletionArgument(name="model", value="res."),
            ),
        )

        result = await handler(req)
        values = result.root.completion.values
        assert set(values) == {"res.partner", "res.users"}
        assert "sale.order" not in values

    @pytest.mark.asyncio
    async def test_completion_handler_cap_at_20(self, valid_config):
        """Test that the registered completion handler caps results at 20."""
        import mcp.types as types

        server = OdooMCPServer(valid_config)
        server.access_controller = Mock()
        server.access_controller.get_enabled_models.return_value = [
            {"model": f"model.{i}"} for i in range(25)
        ]

        handler = server.app._mcp_server.request_handlers[types.CompleteRequest]
        req = types.CompleteRequest(
            method="completion/complete",
            params=types.CompleteRequestParams(
                ref=types.PromptReference(type="ref/prompt", name="test"),
                argument=types.CompletionArgument(name="model", value=""),
            ),
        )

        result = await handler(req)
        values = result.root.completion.values
        assert len(values) == 20


class TestServerIntegration:
    """Integration tests with real .env configuration."""

    @pytest.mark.mcp
    def test_server_with_env_file(self, tmp_path, monkeypatch):
        """Test server initialization with .env file in isolated environment."""
        # Import modules we need
        from fast_odoo_mcp.config import load_config, reset_config

        # Store original working directory
        original_cwd = os.getcwd()

        # Create a test .env file in tmp directory
        env_file = tmp_path / ".env"
        env_file.write_text("""
ODOO_URL=http://localhost:8069
ODOO_API_KEY=test_integration_key
ODOO_DB=test_integration_db
ODOO_MCP_LOG_LEVEL=DEBUG
""")

        try:
            # Change to temp directory to isolate from project .env
            os.chdir(tmp_path)

            # Clear all environment variables that might interfere
            for key in [
                "ODOO_URL",
                "ODOO_API_KEY",
                "ODOO_DB",
                "ODOO_MCP_LOG_LEVEL",
                "ODOO_USER",
                "ODOO_PASSWORD",
                "ODOO_YOLO",
            ]:
                monkeypatch.delenv(key, raising=False)

            # Reset config singleton
            reset_config()

            # Load config explicitly from our test .env file
            # This ensures we're loading from the tmp directory's .env
            config = load_config(env_file)

            # Create server with the loaded config
            server = OdooMCPServer(config)

            assert server.config.url == "http://localhost:8069"
            assert server.config.api_key == "test_integration_key"
            assert server.config.database == "test_integration_db"
            assert server.config.log_level == "DEBUG"

        finally:
            os.chdir(original_cwd)
            reset_config()  # Reset again for other tests

    @pytest.mark.mcp
    @pytest.mark.asyncio
    async def test_real_odoo_connection(self):
        """Test with real Odoo connection using .env credentials.

        This test requires a running Odoo server with valid credentials
        in the .env file.
        """
        # Skip if no .env file exists
        if not Path(".env").exists():
            pytest.skip("No .env file found for integration test")

        # Import and reset config to ensure clean state
        from fast_odoo_mcp.config import reset_config

        reset_config()

        # Load environment
        from dotenv import load_dotenv

        load_dotenv()

        # Check if required env vars are set
        if not os.getenv("ODOO_URL"):
            pytest.skip("ODOO_URL not set in environment")

        server = None
        try:
            # Create server with real config
            server = OdooMCPServer()

            # Test connection
            server._ensure_connection()

            # If we get here, connection was successful
            assert server.connection is not None

            # Clean up
            server._cleanup_connection()

        except OdooConnectionError as e:
            # Connection errors are expected if Odoo is not running
            pytest.skip(f"Integration test skipped (Odoo not available): {e}")
        finally:
            # Always reset config for other tests
            reset_config()


class TestMainEntry:
    """Test the __main__ entry point."""

    def test_help_flag(self, capsys):
        """Test --help flag."""
        from fast_odoo_mcp.__main__ import main

        # argparse raises SystemExit for --help
        try:
            exit_code = main(["--help"])
            assert exit_code == 0
        except SystemExit as e:
            assert e.code == 0

        captured = capsys.readouterr()
        # Help output goes to stdout by default from argparse
        help_output = captured.out or captured.err
        assert "Odoo MCP Server" in help_output
        assert "ODOO_URL" in help_output

    def test_version_flag(self, capsys):
        """Test --version flag."""
        from fast_odoo_mcp.__main__ import main

        # argparse raises SystemExit for --version
        try:
            exit_code = main(["--version"])
            assert exit_code == 0
        except SystemExit as e:
            assert e.code == 0

        captured = capsys.readouterr()
        # Version output goes to stdout by default from argparse
        version_output = captured.out or captured.err
        assert f"odoo-mcp-server v{SERVER_VERSION}" in version_output

    def test_main_with_invalid_config(self, capsys, monkeypatch):
        """Test main with invalid configuration."""
        from fast_odoo_mcp.__main__ import main

        # Set invalid config
        monkeypatch.setenv("ODOO_URL", "")  # Empty URL

        exit_code = main([])

        assert exit_code == 1

        captured = capsys.readouterr()
        assert "Configuration error" in captured.err

    def test_main_with_valid_config(self, monkeypatch):
        """Test main with valid configuration."""
        from fast_odoo_mcp.__main__ import main

        # Set valid config
        monkeypatch.setenv("ODOO_URL", "http://localhost:8069")
        monkeypatch.setenv("ODOO_API_KEY", "test_key")

        # Mock the server and its run_stdio method
        with patch("fast_odoo_mcp.__main__.OdooMCPServer") as mock_server_class:
            mock_server = Mock()

            # Create a coroutine that completes immediately
            async def mock_run_stdio():
                pass

            mock_server.run_stdio = mock_run_stdio
            mock_server_class.return_value = mock_server

            # Mock asyncio.run to execute synchronously
            def mock_asyncio_run(coro):
                # Run the coroutine to completion
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()

            with patch("asyncio.run", side_effect=mock_asyncio_run):
                exit_code = main([])

                assert exit_code == 0
                mock_server_class.assert_called_once()

    def test_main_with_http_transport(self, monkeypatch):
        """Test main with streamable-http transport."""
        from fast_odoo_mcp.__main__ import main

        monkeypatch.setenv("ODOO_URL", "http://localhost:8069")
        monkeypatch.setenv("ODOO_API_KEY", "test_key")
        # Pre-set so main()'s os.environ writes are captured by monkeypatch
        monkeypatch.setenv("ODOO_MCP_TRANSPORT", "stdio")
        monkeypatch.setenv("ODOO_MCP_HOST", "localhost")
        monkeypatch.setenv("ODOO_MCP_PORT", "8000")

        with patch("fast_odoo_mcp.__main__.OdooMCPServer") as mock_server_class:
            mock_config = Mock()
            mock_config.transport = "streamable-http"
            mock_config.host = "localhost"
            mock_config.port = 8000

            mock_server = Mock()

            async def mock_run_http(**kwargs):
                pass

            mock_server.run_http = mock_run_http
            mock_server_class.return_value = mock_server

            def mock_asyncio_run(coro):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()

            with (
                patch("fast_odoo_mcp.__main__.load_config", return_value=mock_config),
                patch("asyncio.run", side_effect=mock_asyncio_run),
            ):
                exit_code = main(["--transport", "streamable-http"])
                assert exit_code == 0


class TestFastMCPApp:
    """Test the FastMCP app configuration."""

    @pytest.fixture
    def valid_config(self):
        """Create a valid test configuration."""
        return OdooConfig(
            url=os.getenv("ODOO_URL", "http://localhost:8069"),
            api_key="test_api_key_12345",
            database="test_db",
            log_level="INFO",
            default_limit=10,
            max_limit=100,
        )

    def test_fastmcp_app_creation(self, valid_config):
        """Test that FastMCP app is properly created."""
        server = OdooMCPServer(valid_config)

        assert server.app is not None
        assert server.app.name == "odoo-mcp-server"
        assert "Odoo ERP data" in server.app.instructions

    def test_health_route_registered(self, valid_config):
        """Test that /health custom route is registered in Starlette routes."""
        server = OdooMCPServer(valid_config)

        # Inspect the actual Starlette route table via the streamable HTTP app
        starlette_app = server.app.streamable_http_app()
        route_paths = [r.path for r in starlette_app.routes if hasattr(r, "path")]
        assert "/health" in route_paths

    @pytest.mark.asyncio
    async def test_run_http_enables_configured_stateless_mode(self, valid_config):
        """Test streamable HTTP applies configured stateless session mode."""
        valid_config.stateless_http = True
        server = OdooMCPServer(valid_config)
        server._apply_http_token_auth = Mock()
        server._configure_transport_security = Mock()
        server._cleanup_connection = Mock()
        server.app.run_streamable_http_async = AsyncMock()

        await server.run_http(host="localhost", port=8000)

        assert server.app.settings.stateless_http is True
        server.app.run_streamable_http_async.assert_awaited_once()

    def test_apply_http_token_auth_is_idempotent(self, valid_config):
        """Test token auth wrapper is only applied once."""
        valid_config.http_token = "token"
        server = OdooMCPServer(valid_config)

        original = server.app.streamable_http_app
        server._apply_http_token_auth()
        wrapped = server.app.streamable_http_app
        server._apply_http_token_auth()

        assert server.app.streamable_http_app is wrapped
        assert server.app.streamable_http_app is not original

    def test_health_status_unhealthy_when_disconnected(self, valid_config):
        """Test health returns unhealthy when not connected."""
        server = OdooMCPServer(valid_config)

        health = server.get_health_status()
        assert health["status"] == "unhealthy"
        assert health["version"] == SERVER_VERSION
        assert health["connection"]["connected"] is False

    def test_health_status_healthy_when_connected(self, valid_config):
        """Test health returns healthy when connected."""
        server = OdooMCPServer(valid_config)
        server.connection_manager.get_health_status = Mock(
            return_value={
                "connected": True,
                "authenticated": True,
                "api_version": "xmlrpc",
                "database": "test_db",
                "reconnect_count": 0,
                "operation_count": 1,
                "retry_count": 0,
                "last_connect_at": "2026-04-28T00:00:00+00:00",
                "last_error_at": None,
                "last_error": None,
                "uptime_seconds": 1,
                "performance": None,
            }
        )

        health = server.get_health_status()
        assert health["status"] == "healthy"
        assert health["connection"]["connected"] is True
        assert health["connection"]["retry_count"] == 0
