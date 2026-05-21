"""MCP Server implementation for Odoo.

This module provides the FastMCP server that exposes Odoo data
and functionality through the Model Context Protocol.
"""

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from mcp.server import FastMCP

from .access_control import AccessController
from .config import OdooConfig, get_config
from .connection_manager import ConnectionManager
from .error_handling import (
    ConfigurationError,
    ErrorContext,
    error_handler,
)
from .logging_config import get_logger, logging_config, perf_logger
from .odoo_connection import OdooConnection, OdooConnectionError
from .resources import register_resources
from .tools import register_tools

# Set up logging
logger = get_logger(__name__)

# Server version
SERVER_VERSION = "1.0.1"
GIT_COMMIT = "unknown"
_BUILD_ORIGIN = "fast-odoo-mcp-main"


class TokenAuthASGIMiddleware:
    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") in {"/health", "/ready", "/metrics"}:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin1")
        header_token = headers.get(b"x-mcp-token", b"").decode("latin1")
        expected = f"Bearer {self.token}"

        if authorization != expected and header_token != self.token:
            from starlette.responses import JSONResponse

            response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class OdooMCPServer:
    """Main MCP server class for Odoo integration.

    This class manages the FastMCP server instance and maintains
    the connection to Odoo. The server lifecycle is managed by
    establishing connection before starting and cleaning up on exit.
    """

    def __init__(self, config: Optional[OdooConfig] = None):
        """Initialize the Odoo MCP server.

        Args:
            config: Optional OdooConfig instance. If not provided,
                   will load from environment variables.
        """
        # Load configuration
        self.config = config or get_config()

        # Set up structured logging
        logging_config.setup()

        # Initialize connection and access controller through the connection manager
        self.connection_manager = ConnectionManager(self.config)
        self.connection: Optional[OdooConnection] = None
        self.access_controller: Optional[AccessController] = None
        self.performance_manager = None
        self.resource_handler = None
        self.tool_handler = None

        # Create FastMCP instance with server metadata
        self.app = FastMCP(
            name="odoo-mcp-server",
            instructions="MCP server for accessing and managing Odoo ERP data through the Model Context Protocol",
            lifespan=self._odoo_lifespan,
        )

        @self.app.custom_route("/health", methods=["GET"])
        async def health_check(request):
            from starlette.responses import JSONResponse

            return JSONResponse(self.get_health_status())

        @self.app.custom_route("/ready", methods=["GET"])
        async def ready_check(request):
            from starlette.responses import JSONResponse

            status = self.get_health_status()
            code = 200 if status["connection"].get("authenticated") else 503
            return JSONResponse(status, status_code=code)

        @self.app.custom_route("/metrics", methods=["GET"])
        async def metrics_check(request):
            from starlette.responses import JSONResponse

            health = self.get_health_status()
            return JSONResponse(
                {
                    "status": health["status"],
                    "version": health["version"],
                    "connection": health["connection"],
                    "performance": health.get("performance"),
                }
            )

        @self.app.completion()
        async def handle_completion(ref, argument, context):
            from mcp.types import Completion

            if argument.name == "model":
                model_names = self._get_model_names()
                partial = argument.value or ""
                if partial:
                    matches = [m for m in model_names if partial.lower() in m.lower()]
                else:
                    matches = model_names
                return Completion(values=matches[:20])
            return None

        # Track if this is the first (server-level) lifespan invocation
        self._lifespan_initialized = False
        self._executor: Optional[ThreadPoolExecutor] = None
        self._http_auth_applied = False

        self._register_tools()
        self._register_resources()

        logger.info(f"Initialized Odoo MCP Server v{SERVER_VERSION}")

    @contextlib.asynccontextmanager
    async def _odoo_lifespan(self, app: FastMCP):
        """Manage Odoo connection lifecycle for FastMCP.

        In SSE/HTTP mode, FastMCP may invoke lifespan per client connection.
        We only perform setup on the first invocation and skip cleanup
        on subsequent ones to avoid "Too many open files" errors.
        """
        is_first = not self._lifespan_initialized
        if is_first:
            self._lifespan_initialized = True
            try:
                with perf_logger.track_operation("server_startup"):
                    self._configure_executor()
                    self._ensure_connection()
                    self._register_resources()
                yield {}
            finally:
                logger.info("FastMCP lifespan ended; keeping managed Odoo connection available")
        else:
            yield {}

    def _configure_executor(self):
        """Set a bounded executor for blocking Odoo RPC calls."""
        if self._executor is not None:
            return
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        asyncio.get_running_loop().set_default_executor(self._executor)

    def _ensure_connection(self):
        """Ensure connection to Odoo is established.

        Raises:
            ConnectionError: If connection fails
            ConfigurationError: If configuration is invalid
        """
        try:
            self.connection_manager.ensure_connected()
            # Use proxy so all handler closures survive reconnects
            self.connection = self.connection_manager.connection_proxy
            self.access_controller = self.connection_manager.access_controller
            self.performance_manager = self.connection_manager.performance_manager
        except Exception as e:
            context = ErrorContext(operation="connection_setup")
            if isinstance(e, (OdooConnectionError, ConfigurationError)):
                raise
            error_handler.handle_error(e, context=context)

    def _cleanup_connection(self):
        """Clean up Odoo connection."""
        logger.info("Closing managed Odoo connection...")
        self.connection_manager.close()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
        self.connection = None
        self.access_controller = None
        self.performance_manager = None
        self.resource_handler = None
        self.tool_handler = None

    def _register_resources(self):
        """Register resource handlers."""
        if self.resource_handler is None:
            conn = self.connection or (
                self.connection_manager.connection_proxy if self.connection_manager else None
            )
            ac = self.access_controller
            if conn and ac:
                self.resource_handler = register_resources(
                    self.app,
                    conn,
                    ac,
                    self.config,
                    connection_manager=self.connection_manager,
                )
                logger.info("Registered MCP resources")

    def _register_tools(self):
        """Register tool handlers."""
        if self.tool_handler is None:
            self.tool_handler = register_tools(
                self.app,
                self.connection,
                self.access_controller,
                self.config,
                connection_manager=self.connection_manager,
            )
            logger.info("Registered MCP tools")

    async def run_stdio(self):
        """Run the server using stdio transport."""
        try:
            logger.info("Starting MCP server with stdio transport...")
            await self.app.run_stdio_async()
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except (OdooConnectionError, ConfigurationError):
            raise
        except Exception as e:
            context = ErrorContext(operation="server_run")
            error_handler.handle_error(e, context=context)
        finally:
            self._cleanup_connection()

    def run_stdio_sync(self):
        """Synchronous wrapper for run_stdio.

        This is provided for compatibility with synchronous code.
        """
        import asyncio

        asyncio.run(self.run_stdio())

    # SSE transport has been deprecated in MCP protocol version 2025-03-26
    # Use streamable-http transport instead

    def _apply_http_token_auth(self) -> None:
        if not self.config.http_token or self._http_auth_applied:
            return

        original_streamable_http_app = self.app.streamable_http_app
        original_sse_app = self.app.sse_app
        token = self.config.http_token

        def streamable_http_app_with_auth():
            return TokenAuthASGIMiddleware(original_streamable_http_app(), token)

        def sse_app_with_auth(mount_path=None):
            return TokenAuthASGIMiddleware(original_sse_app(mount_path), token)

        self.app.streamable_http_app = streamable_http_app_with_auth
        self.app.sse_app = sse_app_with_auth
        self._http_auth_applied = True

    def _configure_transport_security(self, host: str) -> None:
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if host == "0.0.0.0" and self.config.strict_security and not self.config.http_token:
            raise ConfigurationError(
                "ODOO_MCP_HTTP_TOKEN is required when binding HTTP transport to 0.0.0.0"
            )

        allowed_hosts = set(self.config.allowed_hosts)
        allowed_origins = set(self.config.allowed_origins)
        if host not in local_hosts and host != "0.0.0.0":
            allowed_hosts.add(f"{host}:*")
            allowed_origins.add(f"http://{host}:*")
            allowed_origins.add(f"https://{host}:*")

        for allowed_host in sorted(allowed_hosts):
            self.app.settings.transport_security.allowed_hosts.append(allowed_host)

        for allowed_origin in sorted(allowed_origins):
            self.app.settings.transport_security.allowed_origins.append(allowed_origin)

    async def run_sse(self, host: str = "localhost", port: int = 8000):
        """Run the server using standard SSE transport.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        try:
            logger.info(f"Starting MCP server with SSE transport on {host}:{port}...")
            self.app.settings.host = host
            self.app.settings.port = port

            self._apply_http_token_auth()
            self._configure_transport_security(host)

            await self.app.run_sse_async()
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except (OdooConnectionError, ConfigurationError):
            raise
        except Exception as e:
            context = ErrorContext(operation="server_run_sse")
            error_handler.handle_error(e, context=context)
        finally:
            self._cleanup_connection()

    async def run_http(self, host: str = "localhost", port: int = 8000):
        """Run the server using streamable HTTP transport.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        try:
            logger.info(f"Starting MCP server with HTTP transport on {host}:{port}...")
            self.app.settings.host = host
            self.app.settings.port = port
            self.app.settings.stateless_http = self.config.stateless_http
            logger.info(f"Streamable HTTP stateless mode: {self.config.stateless_http}")

            self._apply_http_token_auth()
            self._configure_transport_security(host)

            await self.app.run_streamable_http_async()
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except (OdooConnectionError, ConfigurationError):
            raise
        except Exception as e:
            context = ErrorContext(operation="server_run_http")
            error_handler.handle_error(e, context=context)
        finally:
            self._cleanup_connection()

    def get_capabilities(self) -> Dict[str, Dict[str, bool]]:
        """Get server capabilities.

        Returns:
            Dict with server capabilities
        """
        return {
            "capabilities": {
                "resources": True,  # Exposes Odoo data as resources
                "tools": True,  # Provides tools for Odoo operations
                "prompts": False,  # Prompts will be added in later phases
            }
        }

    def get_health_status(self) -> Dict[str, Any]:
        """Get server health status with error metrics.

        Returns:
            Dict with health status and metrics
        """
        connection = self.connection_manager.get_health_status()
        is_connected = bool(connection.get("authenticated"))

        return {
            "status": "healthy" if is_connected else "unhealthy",
            "version": SERVER_VERSION,
            "connection": connection,
            "performance": connection.get("performance"),
        }

    def _get_model_names(self) -> list[str]:
        """Get available model names for autocomplete."""
        if not self.access_controller:
            return []
        try:
            models = self.access_controller.get_enabled_models()
            if models:
                return [m["model"] for m in models]
            # YOLO mode returns [] meaning "all allowed" — query ir.model directly
            if self.connection and self.connection.is_authenticated:
                records = self.connection.search_read("ir.model", [], ["model"], limit=200)
                return [r["model"] for r in records]
            return []
        except Exception as e:
            logger.debug(f"Failed to get model names for autocomplete: {e}")
            return []
