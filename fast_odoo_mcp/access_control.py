"""Access control for Odoo MCP Server.

Uses Odoo's native check_access_rights to verify permissions.
Works with both JSON/2 (Odoo 19+) and XML-RPC (Odoo 14-18).
No additional Odoo modules required.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .config import OdooConfig
from .odoo_connection import OdooConnectionError

logger = logging.getLogger(__name__)


class AccessControlError(Exception):
    """Exception for access control failures."""

    pass


@dataclass
class ModelPermissions:
    """Permissions for a specific model."""

    model: str
    enabled: bool
    can_read: bool = False
    can_write: bool = False
    can_create: bool = False
    can_unlink: bool = False

    def can_perform(self, operation: str) -> bool:
        """Check if a specific operation is allowed."""
        operation_map = {
            "read": self.can_read,
            "write": self.can_write,
            "create": self.can_create,
            "unlink": self.can_unlink,
            "delete": self.can_unlink,  # Alias
        }
        return operation_map.get(operation, False)


@dataclass
class CacheEntry:
    """Cache entry for permission data."""

    data: Any
    timestamp: datetime

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry is expired."""
        return datetime.now() - self.timestamp > timedelta(seconds=ttl_seconds)


class AccessController:
    """Controls access to Odoo models via Odoo's native check_access_rights.

    Works with both JSON/2 (Odoo 19+) and XML-RPC (Odoo 14-18) connections.
    No additional Odoo modules required.
    """

    CACHE_TTL = 300

    SAFE_METHOD_PREFIXES = (
        "action_",
        "button_",
        "onchange_",
        "_onchange_",
    )

    SAFE_METHOD_NAMES = frozenset(
        {
            "copy",
            "toggle_active",
            "default_get",
            "onchange",
            "read_group",
            "name_search",
            "name_create",
            # Standard Odoo workflow actions
            "action_done",
            "action_cancel",
            "action_confirm",
            "action_confirm_assign",
            "action_validate",
            "action_close",
            "action_draft",
            "action_approve",
            "action_refuse",
            "action_reset",
            "action_unlock",
            "action_lock",
            "action_post",
            "action_send",
            "action_quotation_send",
            "action_invoice_create",
            "action_invoice_paid",
            "action_cancel_invoice",
            "action_view_invoice",
            "action_view_delivery",
            "action_view_purchase",
            "action_view_sales",
            "action_assign",
            "action_launch",
            "action_archive",
            "action_unarchive",
            # Mail/message methods
            "message_post",
            "message_subscribe",
            "message_unsubscribe",
            "message_notify",
            # Approval workflow methods (web_approval module)
            "commit_flow_approval",
            "turn_approval",
            "transfer_reading",
        }
    )

    BLOCKED_METHOD_PATTERNS = (
        "_",
        "execute",
        "execute_kw",
        "__",
    )

    def __init__(self, config: OdooConfig, connection: Any = None, cache_ttl: int = CACHE_TTL):
        """Initialize access controller.

        Args:
            config: OdooConfig with connection details
            connection: Odoo connection (JSON/2 or XML-RPC) used to check
                        permissions via check_access_rights. When provided,
                        model access reflects the user's actual Odoo ACLs.
            cache_ttl: Cache time-to-live in seconds
        """
        self.config = config
        self.connection = connection
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_lock = threading.RLock()
        # Per-model locks to prevent cache stampede under concurrent access
        self._model_locks: Dict[str, threading.Lock] = {}
        self._model_locks_lock = threading.Lock()

        if connection is not None:
            logger.info(
                "Access control via check_access_rights, cached for %d seconds.",
                cache_ttl,
            )
        else:
            logger.info("No connection — access control delegated to Odoo server.")

    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired(self.cache_ttl):
                    logger.debug(f"Cache hit for {key}")
                    return entry.data
                else:
                    logger.debug(f"Cache expired for {key}")
                    del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        """Set value in cache."""
        with self._cache_lock:
            self._cache[key] = CacheEntry(data=data, timestamp=datetime.now())
        logger.debug(f"Cached {key}")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        with self._cache_lock:
            self._cache.clear()
        logger.info("Cleared access control cache")

    def _is_model_allowed_by_policy(self, model: str) -> bool:
        if model in self.config.model_blocklist:
            return False
        if self.config.model_allowlist and model not in self.config.model_allowlist:
            return False
        return True

    def _get_model_lock(self, model: str) -> threading.Lock:
        """Get or create a per-model lock (prevents cache stampede)."""
        with self._model_locks_lock:
            if model not in self._model_locks:
                self._model_locks[model] = threading.Lock()
            return self._model_locks[model]

    def _get_connection_model_permissions(self, model: str) -> "ModelPermissions":
        """Fetch permissions for a single model via Odoo's check_access_rights.

        Uses per-model locking to prevent cache stampede: when multiple
        concurrent requests check the same model, only the first one makes
        the RPC calls; others wait and reuse the cached result.

        Raises:
            OdooConnectionError: If the connection fails during permission checks.
        """
        if not self._is_model_allowed_by_policy(model):
            return ModelPermissions(model=model, enabled=False)

        if self.connection is None:
            return ModelPermissions(model=model, enabled=False)

        cache_key = f"_j2_{model}"
        # Fast path: check cache without lock
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        # Slow path: per-model lock prevents concurrent permission checks
        # for the same model (avoids 4x RPC stampede)
        with self._get_model_lock(model):
            # Double-check cache after acquiring lock
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

            # Retry once on connection errors
            for attempt in range(2):
                try:
                    can_read = self.connection.check_access_rights(model, "read")
                    can_write = self.connection.check_access_rights(model, "write")
                    can_create = self.connection.check_access_rights(model, "create")
                    can_unlink = self.connection.check_access_rights(model, "unlink")
                    break
                except OdooConnectionError:
                    if attempt > 0:
                        raise
                    logger.warning(
                        "Connection error checking permissions for %s, retrying...", model
                    )

            perms = ModelPermissions(
                model=model,
                enabled=can_read,
                can_read=can_read,
                can_write=can_write,
                can_create=can_create,
                can_unlink=can_unlink,
            )
            self._set_cache(cache_key, perms)
            logger.debug(
                "JSON/2 permissions for %s: read=%s write=%s create=%s unlink=%s",
                model,
                can_read,
                can_write,
                can_create,
                can_unlink,
            )
            return perms

    def get_enabled_models(self) -> List[Dict[str, str]]:
        """Get list of all MCP-enabled models.

        Returns:
            List of dicts with 'model' and 'name' keys

        Raises:
            AccessControlError: If request fails
        """
        # All models are accessible — Odoo's own ACLs enforce permissions
        # per user via check_access_rights at the operation level.
        return []

    def is_model_enabled(self, model: str) -> bool:
        """Check if a model is MCP-enabled.

        Args:
            model: The Odoo model name (e.g., 'res.partner')

        Returns:
            True if model is enabled, False otherwise
        """
        return self._get_connection_model_permissions(model).enabled

    def get_model_permissions(self, model: str) -> ModelPermissions:
        """Get permissions for a specific model.

        Args:
            model: The Odoo model name

        Returns:
            ModelPermissions object with permission details

        Raises:
            AccessControlError: If request fails
        """
        return self._get_connection_model_permissions(model)

    def check_operation_allowed(self, model: str, operation: str) -> Tuple[bool, Optional[str]]:
        """Check if an operation is allowed on a model.

        Args:
            model: The Odoo model name
            operation: The operation to check (read, write, create, unlink)

        Returns:
            Tuple of (allowed, error_message)
        """
        # Write allowlist: when set, only listed models allow write operations
        if operation in ("write", "create", "unlink") and self.config.write_allowlist:
            if model not in self.config.write_allowlist:
                return (
                    False,
                    f"Write operation '{operation}' not allowed on model '{model}' (not in ODOO_MCP_WRITE_ALLOWLIST)",
                )

        permissions = self._get_connection_model_permissions(model)
        if not permissions.can_perform(operation):
            return False, f"Operation '{operation}' not allowed on model '{model}'"
        return True, None

    def validate_model_access(self, model: str, operation: str) -> None:
        """Validate model access, raising exception if denied.

        Args:
            model: The Odoo model name
            operation: The operation to perform

        Raises:
            AccessControlError: If access is denied
        """
        allowed, error_msg = self.check_operation_allowed(model, operation)
        if not allowed:
            raise AccessControlError(error_msg or f"Access denied to {model}.{operation}")

    def validate_method_call(self, model: str, method: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a method can be called on a model via MCP.

        Security policy:
        1. The model must be accessible (at least read permission).
        2. The method must be in the safe list or match a safe prefix.
        3. Methods starting with double underscore are always blocked.
        4. In readonly mode, only read-like methods are allowed.
        5. The user must have write permission for state-changing methods.

        Args:
            model: Odoo model name
            method: Method name to call

        Returns:
            Tuple of (allowed, error_message)
        """
        if not self._is_model_allowed_by_policy(model):
            return False, f"Model '{model}' is not accessible via MCP"

        permissions = self._get_connection_model_permissions(model)
        if not permissions.enabled:
            return False, f"No read access to model '{model}'"

        if method.startswith("__"):
            return False, f"Dunder methods ('{method}') are not callable via MCP"

        is_safe = (
            method in self.SAFE_METHOD_NAMES
            or any(method.startswith(p) for p in self.SAFE_METHOD_PREFIXES)
            or method in self.config.safe_methods
        )
        if not is_safe:
            hint = (
                "Add it to ODOO_MCP_SAFE_METHODS to allow this method. "
                f"Allowed: built-in safe names, prefixes ({', '.join(self.SAFE_METHOD_PREFIXES)}), "
                f"or custom methods via ODOO_MCP_SAFE_METHODS"
            )
            return False, (f"Method '{method}' is not in the MCP safe method list. {hint}")

        state_changing_methods = {
            "create",
            "write",
            "unlink",
            "copy",
            "toggle_active",
            "message_post",
            "message_subscribe",
            "message_unsubscribe",
            "message_notify",
            "import_data",
        }
        is_state_changing = (
            method in state_changing_methods
            or method.startswith("action_")
            or method.startswith("button_")
        )
        if is_state_changing:
            if self.config.readonly:
                return False, (
                    f"Method '{method}' changes data, but the server is in "
                    f"readonly mode (ODOO_MCP_READONLY=true)"
                )
            if self.config.write_allowlist and model not in self.config.write_allowlist:
                return False, (
                    f"Method '{method}' on '{model}' is blocked by ODOO_MCP_WRITE_ALLOWLIST"
                )
            if not permissions.can_write:
                return False, f"No write permission on model '{model}' for method '{method}'"

        return True, None

    def filter_enabled_models(self, models: List[str]) -> List[str]:
        """Filter list of models to only include enabled ones.

        Args:
            models: List of model names to filter

        Returns:
            List of enabled model names
        """
        # In JSON/2 mode, filter to models where user has at least read access
        if self.config.api_version == "json2":
            return [m for m in models if self._get_connection_model_permissions(m).can_read]

        try:
            enabled_models = self.get_enabled_models()
            enabled_set = {m["model"] for m in enabled_models}
            return [m for m in models if m in enabled_set]
        except AccessControlError as e:
            logger.error(f"Failed to filter models: {e}")
            return []

    def get_all_permissions(self) -> Dict[str, ModelPermissions]:
        """Get permissions for all enabled models.

        Returns:
            Dict mapping model names to their permissions
        """
        permissions = {}

        try:
            enabled_models = self.get_enabled_models()

            for model_info in enabled_models:
                model = model_info["model"]
                try:
                    permissions[model] = self.get_model_permissions(model)
                except AccessControlError as e:
                    logger.warning(f"Failed to get permissions for {model}: {e}")

        except AccessControlError as e:
            logger.error(f"Failed to get all permissions: {e}")

        return permissions
