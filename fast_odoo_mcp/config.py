"""Configuration management for Odoo MCP Server.

This module handles loading and validation of environment variables
for connecting to Odoo via XML-RPC.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Literal, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class OdooConfig:
    """Configuration for Odoo connection and MCP server settings."""

    # Required fields
    url: str

    # Authentication (one method required)
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # Optional fields with defaults
    database: Optional[str] = None
    log_level: str = "INFO"
    default_limit: int = 10
    max_limit: int = 100
    max_smart_fields: int = 15
    locale: Optional[str] = "zh_CN"

    # MCP transport configuration
    transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    host: str = "localhost"
    port: int = 8000

    # YOLO mode configuration
    yolo_mode: str = "off"  # "off", "read", or "true"

    # Tool access control: tools whose names are in this set will NOT be registered
    disabled_tools: FrozenSet[str] = frozenset()

    # Production safety controls
    readonly: bool = True
    model_allowlist: FrozenSet[str] = frozenset()
    model_blocklist: FrozenSet[str] = frozenset()
    write_allowlist: FrozenSet[str] = frozenset()
    max_bulk_size: int = 100
    http_token: Optional[str] = None
    strict_security: bool = True
    max_workers: int = 20
    allowed_hosts: FrozenSet[str] = frozenset()
    allowed_origins: FrozenSet[str] = frozenset()
    stateless_http: bool = True

    # API version: set by auto-detection after connecting (json2 for Odoo 19+, xmlrpc for 14-18)
    api_version: Literal["auto", "xmlrpc", "json2"] = "auto"

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate URL
        if not self.url:
            raise ValueError("ODOO_URL is required")

        # Ensure URL format
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("ODOO_URL must start with http:// or https://")

        # Validate YOLO mode
        valid_yolo_modes = {"off", "read", "true"}
        if self.yolo_mode not in valid_yolo_modes:
            raise ValueError(
                f"Invalid YOLO mode: {self.yolo_mode}. "
                f"Must be one of: {', '.join(valid_yolo_modes)}"
            )

        # Validate authentication (relaxed for YOLO mode)
        has_api_key = bool(self.api_key)
        has_credentials = bool(self.username and self.password)

        # In YOLO mode, we might need username even with API key for standard auth
        if self.is_yolo_enabled:
            if not has_credentials and not (has_api_key and self.username):
                raise ValueError("YOLO mode requires either username/password or username/API key")
        else:
            if not has_api_key and not has_credentials:
                raise ValueError(
                    "Authentication required: provide either ODOO_API_KEY or "
                    "both ODOO_USER and ODOO_PASSWORD"
                )

        # Validate numeric fields
        if self.default_limit <= 0:
            raise ValueError("ODOO_MCP_DEFAULT_LIMIT must be positive")

        if self.max_limit <= 0:
            raise ValueError("ODOO_MCP_MAX_LIMIT must be positive")

        if self.default_limit > self.max_limit:
            raise ValueError("ODOO_MCP_DEFAULT_LIMIT cannot exceed ODOO_MCP_MAX_LIMIT")

        if self.max_smart_fields <= 0:
            raise ValueError("ODOO_MCP_MAX_SMART_FIELDS must be positive")

        if self.max_bulk_size <= 0:
            raise ValueError("ODOO_MCP_MAX_BULK_SIZE must be positive")

        if self.max_workers <= 0:
            raise ValueError("ODOO_MCP_MAX_WORKERS must be positive")

        # Validate security-sensitive transport settings
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if self.strict_security and self.transport in ("sse", "streamable-http"):
            if self.host not in local_hosts and not self.http_token:
                raise ValueError(
                    "ODOO_MCP_HTTP_TOKEN is required for non-local HTTP transports when strict security is enabled"
                )

        # Validate log level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log level: {self.log_level}. "
                f"Must be one of: {', '.join(valid_log_levels)}"
            )

        # Validate transport
        valid_transports = {"stdio", "sse", "streamable-http"}
        if self.transport not in valid_transports:
            raise ValueError(
                f"Invalid transport: {self.transport}. "
                f"Must be one of: {', '.join(valid_transports)}"
            )

        # Validate port
        if not isinstance(self.port, int) or self.port < 1 or self.port > 65535:
            raise ValueError(
                f"Invalid port: {self.port}. Port must be an integer between 1 and 65535"
            )

        logger.debug(
            f"Configuration validated successfully: transport={self.transport}, host={self.host}, port={self.port}, log_level={self.log_level}"
        )

    @property
    def uses_api_key(self) -> bool:
        """Check if configuration uses API key authentication."""
        return bool(self.api_key)

    @property
    def uses_credentials(self) -> bool:
        """Check if configuration uses username/password authentication."""
        return bool(self.username and self.password)

    @property
    def is_yolo_enabled(self) -> bool:
        """Check if any YOLO mode is active."""
        return self.yolo_mode != "off"

    @property
    def is_write_allowed(self) -> bool:
        """Check if write operations are allowed in current mode."""
        return self.yolo_mode == "true"

    def get_endpoint_paths(self) -> Dict[str, str]:
        """Get appropriate endpoint paths based on mode.

        The DB endpoint always uses the server-wide ``/xmlrpc/db`` path
        so that database listing works even when multiple databases exist
        (MCP addon routes require a DB context that isn't available yet).

        Returns:
            Dict[str, str]: Mapping of endpoint names to paths
        """
        if self.is_yolo_enabled:
            # Use standard Odoo endpoints in YOLO mode
            return {"db": "/xmlrpc/db", "common": "/xmlrpc/2/common", "object": "/xmlrpc/2/object"}
        else:
            # Always use standard Odoo endpoints (since we removed the mcp_server plugin requirement)
            return {
                "db": "/xmlrpc/db",
                "common": "/xmlrpc/2/common",
                "object": "/xmlrpc/2/object",
            }

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "OdooConfig":
        """Create configuration from environment variables.

        Args:
            env_file: Optional path to .env file

        Returns:
            OdooConfig: Validated configuration object
        """
        return load_config(env_file)


def load_config(env_file: Optional[Path] = None) -> OdooConfig:
    """Load configuration from environment variables and .env file.

    Args:
        env_file: Optional path to .env file. If not provided,
                 looks for .env in current directory.

    Returns:
        OdooConfig: Validated configuration object

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    # Check if we have a .env file or environment variables
    if env_file:
        if not env_file.exists():
            raise ValueError(
                f"Configuration file not found: {env_file}\n"
                "Please create a .env file based on .env.example"
            )
        load_dotenv(env_file)
    else:
        # Try to load .env from current directory
        default_env = Path(".env")
        env_loaded = False

        if default_env.exists():
            load_dotenv(default_env)
            env_loaded = True

        # If no .env file found and no ODOO_URL in environment, raise error
        if not env_loaded and not os.getenv("ODOO_URL"):
            raise ValueError(
                "No .env file found and ODOO_URL not set in environment.\n"
                "Please create a .env file based on .env.example or set environment variables."
            )

    # Helper function to get int with default
    def get_int_env(key: str, default: int) -> int:
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{key} must be a valid integer") from None

    # Helper function to parse YOLO mode
    def get_yolo_mode() -> str:
        yolo_env = os.getenv("ODOO_YOLO", "off").strip().lower()
        # Map various inputs to valid modes
        if yolo_env in ["", "false", "0", "off", "no"]:
            return "off"
        elif yolo_env in ["read", "readonly", "read-only"]:
            return "read"
        elif yolo_env in ["true", "1", "yes", "full"]:
            return "true"
        else:
            # Invalid value - will be caught by validation
            return yolo_env

    def get_bool_env(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def get_set_env(key: str) -> FrozenSet[str]:
        return frozenset(item.strip() for item in os.getenv(key, "").split(",") if item.strip())

    # Create configuration
    config = OdooConfig(
        url=os.getenv("ODOO_URL", "").strip(),
        api_key=os.getenv("ODOO_API_KEY", "").strip() or None,
        username=os.getenv("ODOO_USER", "").strip() or None,
        password=os.getenv("ODOO_PASSWORD", "").strip() or None,
        database=os.getenv("ODOO_DB", "").strip() or None,
        log_level=os.getenv("ODOO_MCP_LOG_LEVEL", "INFO").strip(),
        default_limit=get_int_env("ODOO_MCP_DEFAULT_LIMIT", 10),
        max_limit=get_int_env("ODOO_MCP_MAX_LIMIT", 100),
        max_smart_fields=get_int_env("ODOO_MCP_MAX_SMART_FIELDS", 15),
        transport=os.getenv("ODOO_MCP_TRANSPORT", "stdio").strip(),
        host=os.getenv("ODOO_MCP_HOST", "localhost").strip(),
        port=get_int_env("ODOO_MCP_PORT", 8000),
        locale=os.getenv("ODOO_LOCALE", "zh_CN").strip() or None,
        yolo_mode=get_yolo_mode(),
        disabled_tools=frozenset(
            t.strip().lower()
            for t in os.getenv("ODOO_MCP_DISABLED_TOOLS", "").split(",")
            if t.strip()
        ),
        readonly=get_bool_env("ODOO_MCP_READONLY", True),
        model_allowlist=get_set_env("ODOO_MCP_MODEL_ALLOWLIST"),
        model_blocklist=get_set_env("ODOO_MCP_MODEL_BLOCKLIST"),
        write_allowlist=get_set_env("ODOO_MCP_WRITE_ALLOWLIST"),
        max_bulk_size=get_int_env("ODOO_MCP_MAX_BULK_SIZE", 100),
        http_token=os.getenv("ODOO_MCP_HTTP_TOKEN", "").strip() or None,
        strict_security=get_bool_env("ODOO_MCP_STRICT_SECURITY", True),
        max_workers=get_int_env("ODOO_MCP_MAX_WORKERS", 20),
        allowed_hosts=get_set_env("ODOO_MCP_ALLOWED_HOSTS"),
        allowed_origins=get_set_env("ODOO_MCP_ALLOWED_ORIGINS"),
        stateless_http=get_bool_env("ODOO_MCP_STATELESS_HTTP", True),
    )

    # Validate that HTTP transports explicitly provide host and port if security requires it
    # We maintain localhost/8000 as default for stdio/convenience, but if users
    # explicitly want to avoid hardcoded defaults, they should set them.
    if config.transport in ("sse", "streamable-http"):
        if not os.getenv("ODOO_MCP_HOST"):
            raise ValueError(
                "ODOO_MCP_HOST (or --host argument) must be explicitly set for HTTP transports to avoid accidental exposure."
            )
        if not os.getenv("ODOO_MCP_PORT"):
            raise ValueError(
                "ODOO_MCP_PORT (or --port argument) must be explicitly set for HTTP transports to avoid accidental port binding."
            )

    return config


# Singleton configuration instance
_config: Optional[OdooConfig] = None


def get_config() -> OdooConfig:
    """Get the singleton configuration instance.

    Returns:
        OdooConfig: The configuration object

    Raises:
        ValueError: If configuration is not yet loaded
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: OdooConfig) -> None:
    """Set the singleton configuration instance.

    This is primarily useful for testing.

    Args:
        config: The configuration object to set
    """
    global _config
    _config = config


def reset_config() -> None:
    """Reset the singleton configuration instance.

    This is primarily useful for testing.
    """
    global _config
    _config = None
