"""Unified Odoo connection lifecycle and retry management."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional, TypeVar

from .access_control import AccessController
from .config import OdooConfig
from .logging_config import get_logger, perf_logger
from .odoo_connection import OdooConnection, OdooConnectionError
from .odoo_json2_connection import OdooJSON2Connection
from .performance import PerformanceManager
from .version_detect import detect_api_version

logger = get_logger(__name__)

T = TypeVar("T")
OperationClass = Literal["light", "heavy", "write"]


# Non-idempotent ORM operations whose retry is unsafe. The first attempt may
# have already committed on the Odoo side (e.g. credit.record action_submit
# already flipped state draft→confirmed), so a retry after a transient
# response-stage failure (timeout / dropped connection) hits a state or
# constraint error and masks the fact that the write actually succeeded.
# Only read/search calls are safe to retry on a transient OdooConnectionError.
_NON_IDEMPOTENT_MARKERS = (
    "execute_action",  # execute_method(model, "action_*")
    "execute_write",
    "execute_create",
    "execute_unlink",
    "create_record",
    "create_records",
    "update_record",
    "update_records",
    "delete_record",
    "delete_records",
    "onchange_execute",
)


def _is_non_idempotent_operation(operation_name: str) -> bool:
    name = (operation_name or "").lower()
    return any(marker in name for marker in _NON_IDEMPOTENT_MARKERS)


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
        self._op_semaphores: dict[OperationClass, threading.Semaphore] = {
            "light": threading.Semaphore(config.light_concurrency),
            "heavy": threading.Semaphore(config.heavy_concurrency),
            "write": threading.Semaphore(config.write_concurrency),
        }
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

    def call_with_retry(
        self,
        operation_name: str,
        func: Callable[[], T],
        *,
        operation_class: OperationClass = "light",
    ) -> T:
        with self._lock:
            self._operation_count += 1
        semaphore = self._op_semaphores[operation_class]
        wait_started = time.monotonic()
        with semaphore:
            wait_seconds = time.monotonic() - wait_started
            if wait_seconds > 1:
                logger.warning(
                    "Odoo operation waited %.1fs in %s queue: %s",
                    wait_seconds,
                    operation_class,
                    operation_name,
                )
            try:
                with perf_logger.track_operation(operation_name):
                    return func()
            except OdooConnectionError as exc:
                self._record_error(exc)
                lowered = str(exc).lower()
                # Never retry deterministic errors: None serialization, or
                # business errors (xmlrpc Fault / Odoo UserError) which
                # odoo_connection wraps as "Operation failed: ...". Retrying
                # them only wastes a call — the result is identical.
                is_deterministic = "cannot marshal none" in lowered or "operation failed" in lowered
                # Never retry non-idempotent write/action operations even on
                # genuinely transient errors (timeout / dropped connection):
                # the first attempt often already committed on the Odoo side,
                # and a retry hits a state/constraint error that masks the
                # success. Root cause of credit.record action_submit reporting
                # "仅草稿状态的记录可提交" while state was in fact confirmed.
                if is_deterministic or _is_non_idempotent_operation(operation_name):
                    raise
                with self._lock:
                    self._retry_count += 1
                # Only reconnect if connection is actually broken;
                # another thread may have already reconnected.
                if not self._is_ready():
                    logger.warning("Odoo connection lost, reconnecting: %s", operation_name)
                    self.reconnect()
                else:
                    logger.warning(
                        "Odoo operation failed (transient), retrying: %s", operation_name
                    )
                with perf_logger.track_operation(f"{operation_name}_retry"):
                    return func()

    async def run_blocking(
        self,
        operation_name: str,
        func: Callable[[], T],
        *,
        operation_class: OperationClass = "light",
    ) -> T:
        return await asyncio.to_thread(
            self.call_with_retry, operation_name, func, operation_class=operation_class
        )

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
