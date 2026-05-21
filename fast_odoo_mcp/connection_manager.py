"""Unified Odoo connection lifecycle and retry management."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from .access_control import AccessController
from .config import OdooConfig
from .logging_config import get_logger, perf_logger
from .odoo_connection import OdooConnection, OdooConnectionError
from .odoo_json2_connection import OdooJSON2Connection
from .performance import PerformanceManager
from .version_detect import detect_api_version

logger = get_logger(__name__)

T = TypeVar("T")


class _ConnectionProxy:
    """Thread-safe proxy that always delegates to the ConnectionManager's current connection.

    Ensures closures capturing this proxy always use the latest connection,
    even after reconnects. Attribute access is delegated at call time, not
    capture time, so retries after reconnect automatically use the new connection.
    """

    __slots__ = ("_cm",)

    def __init__(self, cm: "ConnectionManager"):
        object.__setattr__(self, "_cm", cm)

    def _resolve(self):
        conn = self._cm.connection
        if conn is not None and getattr(conn, "is_authenticated", False):
            return conn
        conn, _ = self._cm.ensure_connected()
        return conn

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


class ConnectionManager:
    """Owns the active Odoo connection and keeps handlers on a fresh instance."""

    # Limit concurrent Odoo RPC calls to avoid overwhelming the server.
    _MAX_CONCURRENT_OPS = 8

    def __init__(self, config: OdooConfig):
        self.config = config
        self._lock = threading.RLock()
        self._op_semaphore = threading.Semaphore(self._MAX_CONCURRENT_OPS)
        self.connection: Optional[OdooConnection | OdooJSON2Connection] = None
        self.access_controller: Optional[AccessController] = None
        self.performance_manager: Optional[PerformanceManager] = None
        self.reconnect_count = 0
        self._operation_count = 0
        self._retry_count = 0
        self.last_connect_at: Optional[datetime] = None
        self.last_error_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self._started_at = time.time()
        self._proxy = _ConnectionProxy(self)

    @property
    def connection_proxy(self) -> _ConnectionProxy:
        """Return a proxy that always delegates to the current connection."""
        return self._proxy

    @property
    def operation_count(self) -> int:
        with self._lock:
            return self._operation_count

    @property
    def retry_count(self) -> int:
        with self._lock:
            return self._retry_count

    def ensure_connected(self) -> tuple[OdooConnection | OdooJSON2Connection, AccessController]:
        with self._lock:
            if self._is_ready():
                return self.connection, self.access_controller  # type: ignore[return-value]

            self._connect_locked()
            return self.connection, self.access_controller  # type: ignore[return-value]

    def reconnect(self) -> tuple[OdooConnection | OdooJSON2Connection, AccessController]:
        with self._lock:
            # Another thread may have already reconnected
            if self._is_ready():
                return self.connection, self.access_controller  # type: ignore[return-value]
            self._close_locked()
            self.reconnect_count += 1
            self._connect_locked()
            return self.connection, self.access_controller  # type: ignore[return-value]

    def call_with_retry(self, operation_name: str, func: Callable[[], T]) -> T:
        with self._lock:
            self._operation_count += 1
        with self._op_semaphore:
            try:
                with perf_logger.track_operation(operation_name):
                    return func()
            except OdooConnectionError as exc:
                self._record_error(exc)
                with self._lock:
                    self._retry_count += 1
                # Only reconnect if connection is actually broken;
                # another thread may have already reconnected.
                if not self._is_ready():
                    logger.warning("Odoo connection lost, reconnecting: %s", operation_name)
                    self.reconnect()
                else:
                    logger.warning("Odoo operation failed (transient), retrying: %s", operation_name)
                with perf_logger.track_operation(f"{operation_name}_retry"):
                    return func()

    async def run_blocking(self, operation_name: str, func: Callable[[], T]) -> T:
        return await asyncio.to_thread(self.call_with_retry, operation_name, func)

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def get_health_status(self) -> dict[str, Any]:
        connection = self.connection
        performance = self.performance_manager.get_stats() if self.performance_manager else None
        connected = bool(connection and getattr(connection, "is_connected", False))
        authenticated = bool(connection and getattr(connection, "is_authenticated", False))
        database = getattr(connection, "database", None) if connection else None

        return {
            "connected": connected,
            "authenticated": authenticated,
            "api_version": self.config.api_version,
            "database": database,
            "reconnect_count": self.reconnect_count,
            "operation_count": self._operation_count,
            "retry_count": self._retry_count,
            "last_connect_at": self._format_dt(self.last_connect_at),
            "last_error_at": self._format_dt(self.last_error_at),
            "last_error": self.last_error,
            "uptime_seconds": int(time.time() - self._started_at),
            "performance": performance,
        }

    def _is_ready(self) -> bool:
        return bool(
            self.connection is not None
            and self.access_controller is not None
            and getattr(self.connection, "is_connected", False)
            and getattr(self.connection, "is_authenticated", False)
        )

    def _connect_locked(self) -> None:
        try:
            logger.info("Establishing managed connection to Odoo...")
            with perf_logger.track_operation("connection_setup"):
                api_version, server_version = detect_api_version(self.config.url)
                self.config.api_version = api_version
                logger.info(
                    "Auto-detected api_version=%s (Odoo %s)",
                    api_version,
                    server_version or "unknown",
                )

                if api_version == "json2":
                    self.performance_manager = None
                    connection: OdooConnection | OdooJSON2Connection = OdooJSON2Connection(
                        self.config
                    )
                else:
                    self.performance_manager = PerformanceManager(self.config)
                    connection = OdooConnection(
                        self.config,
                        performance_manager=self.performance_manager,
                    )

                connection.connect()
                connection.authenticate()
                self.connection = connection
                self.access_controller = AccessController(self.config, connection=self._proxy)

            self.last_connect_at = datetime.now(timezone.utc)
            self.last_error = None
            logger.info("Managed Odoo connection is ready")
        except Exception as exc:
            self._record_error(exc)
            self._close_locked()
            raise

    def _close_locked(self) -> None:
        connection = self.connection
        performance_manager = self.performance_manager
        self.connection = None
        self.access_controller = None
        self.performance_manager = None

        if connection:
            try:
                connection.disconnect()
            except Exception as exc:
                logger.warning("Error while closing Odoo connection: %s", exc)

        if performance_manager:
            try:
                performance_manager.connection_pool.clear()
                performance_manager.clear_all_caches()
            except Exception as exc:
                logger.warning("Error while clearing performance manager: %s", exc)

    def _record_error(self, exc: Exception) -> None:
        with self._lock:
            self.last_error_at = datetime.now(timezone.utc)
            self.last_error = str(exc)

    @staticmethod
    def _format_dt(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
