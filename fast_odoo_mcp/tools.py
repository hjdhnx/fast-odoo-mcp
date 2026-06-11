"""MCP tool handlers for Odoo operations.

This module implements MCP tools for performing operations on Odoo data.
Tools are different from resources - they can have side effects and perform
actions like creating, updating, or deleting records.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .access_control import AccessControlError, AccessController
from .config import OdooConfig
from .connection_manager import ConnectionManager, OperationClass
from .connection_protocol import OdooConnectionProtocol
from .error_handling import (
    NotFoundError,
    ValidationError,
)
from .error_sanitizer import ErrorSanitizer
from .logging_config import get_logger, perf_logger
from .odoo_connection import OdooConnectionError
from .schemas import (
    BulkCreateResult,
    BulkDeleteResult,
    BulkUpdateResult,
    CreateResult,
    DeleteResult,
    ExecuteMethodResult,
    FieldSelectionMetadata,
    ModelMethodResult,
    ModelsResult,
    OnchangeResult,
    PublicConfigResult,
    RecordResult,
    ResourceTemplatesResult,
    SearchResult,
    ServerInfoResult,
    UpdateResult,
)

logger = get_logger(__name__)

DEFAULT_MAX_BULK_SIZE = 100


class OdooToolHandler:
    """Handles MCP tool requests for Odoo operations."""

    def __init__(
        self,
        app: FastMCP,
        connection: Optional[OdooConnectionProtocol] = None,
        access_controller: Optional[AccessController] = None,
        config: Optional[OdooConfig] = None,
        connection_manager: Optional[ConnectionManager] = None,
    ):
        """Initialize tool handler."""
        self.app = app
        self.connection_manager = connection_manager
        # Use proxy when connection_manager is available so closures always
        # delegate to the current connection (survives reconnects).
        if connection_manager is not None:
            self.connection = connection_manager.connection_proxy
        else:
            self.connection = connection
        self.access_controller = access_controller
        self.config = config
        self._perf_manager = None

        self._register_tools()

    @property
    def perf_manager(self):
        if self._perf_manager is not None:
            return self._perf_manager
        from .performance import PerformanceManager

        if (
            self.connection_manager is not None
            and self.connection_manager.performance_manager is not None
        ):
            self._perf_manager = self.connection_manager.performance_manager
        elif self.connection is not None and hasattr(self.connection, "performance_manager"):
            self._perf_manager = self.connection.performance_manager
        elif self.config is not None:
            self._perf_manager = PerformanceManager(self.config)
        else:
            self._perf_manager = PerformanceManager(OdooConfig(url="http://localhost:8069"))
        return self._perf_manager

    async def _get_user_context(
        self,
    ) -> Tuple[OdooConnectionProtocol, AccessController, str]:
        """Get connection and access controller for the current request.

        Returns:
            Tuple of (connection, access_controller, "stdio")

        Raises:
            ValidationError: If no connection is available
        """
        if self.connection_manager is not None:
            # Use the proxy (always delegates to the current connection)
            connection = self.connection_manager.connection_proxy
            # Fetch the current access controller (refreshed on reconnect)
            _, access_controller = self.connection_manager.ensure_connected()
            return connection, access_controller, "stdio"

        if self.connection is not None and self.access_controller is not None:
            # Re-authenticate if the connection has been disconnected or timed out
            if not self.connection.is_authenticated:
                logger.info("Connection lost or unauthenticated. Re-authenticating...")
                try:
                    self.connection.connect()
                    self.connection.authenticate()
                except Exception as e:
                    logger.error(f"Failed to re-authenticate: {e}")
                    raise ValidationError("Failed to re-authenticate with Odoo") from e
            return self.connection, self.access_controller, "stdio"

        raise ValidationError("No Odoo connection available")

    def _normalize_limit(self, limit: int) -> int:
        default_limit = self.config.default_limit if self.config else 10
        max_limit = self.config.max_limit if self.config else 100
        if limit <= 0:
            return default_limit
        if limit > max_limit:
            return max_limit
        return limit

    def _sanitize_public_url(self, url: Optional[str]) -> str:
        if not url:
            return "not configured"
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname or ""
            netloc = hostname
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
        except Exception:
            return "invalid url"

    async def _odoo_call(
        self, operation_name: str, func, operation_class: OperationClass = "light"
    ):
        if self.connection_manager is not None:
            return await self.connection_manager.run_blocking(
                operation_name, func, operation_class=operation_class
            )
        return func()

    def _format_datetime(self, value: str) -> str:
        """Format datetime values to ISO 8601 with timezone."""
        if not value or not isinstance(value, str):
            return value

        # Handle Odoo's compact datetime format (YYYYMMDDTHH:MM:SS)
        if len(value) == 17 and "T" in value and "-" not in value:
            try:
                dt = datetime.strptime(value, "%Y%m%dT%H:%M:%S")
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except ValueError:
                pass

        # Handle standard Odoo datetime format (YYYY-MM-DD HH:MM:SS)
        if " " in value and len(value) == 19:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except ValueError:
                pass

        return value

    def _process_record_dates(
        self,
        record: Dict[str, Any],
        model: str,
        connection: Optional[OdooConnectionProtocol] = None,
    ) -> Dict[str, Any]:
        """Process datetime fields in a record to ensure proper formatting."""
        conn = connection or self.connection
        # Common datetime field names in Odoo
        known_datetime_fields = {
            "create_date",
            "write_date",
            "date",
            "datetime",
            "date_start",
            "date_end",
            "date_from",
            "date_to",
            "date_order",
            "date_invoice",
            "date_due",
            "last_update",
            "last_activity",
            "activity_date_deadline",
        }

        # First try to get field metadata
        fields_info = None
        try:
            fields_info = conn.fields_get(model)
        except Exception:
            # Field metadata unavailable, will use fallback detection
            pass

        # Process each field in the record
        for field_name, field_value in record.items():
            if not isinstance(field_value, str):
                continue

            should_format = False

            # Check if field is identified as datetime from metadata
            if fields_info and isinstance(fields_info, dict) and field_name in fields_info:
                field_type = fields_info[field_name].get("type")
                if field_type == "datetime":
                    should_format = True

            # Check if field name suggests it's a datetime field
            if not should_format and field_name in known_datetime_fields:
                should_format = True

            # Check if field name ends with common datetime suffixes
            if not should_format and any(
                field_name.endswith(suffix) for suffix in ["_date", "_datetime", "_time"]
            ):
                should_format = True

            # Pattern-based detection for datetime-like strings
            if not should_format and (
                (
                    len(field_value) == 17 and "T" in field_value and "-" not in field_value
                )  # 20250607T21:55:52
                or (
                    len(field_value) == 19 and " " in field_value and field_value.count("-") == 2
                )  # 2025-06-07 21:55:52
            ):
                should_format = True

            # Apply formatting if needed
            if should_format:
                formatted = self._format_datetime(field_value)
                if formatted != field_value:
                    record[field_name] = formatted

        return record

    def _should_include_field_by_default(self, field_name: str, field_info: Dict[str, Any]) -> bool:
        """Determine if a field should be included in default response.

        Args:
            field_name: Name of the field
            field_info: Field metadata from fields_get()

        Returns:
            True if field should be included in default response
        """
        # Always include essential fields
        always_include = {"id", "name", "display_name", "active", "company_id"}
        if field_name in always_include:
            return True

        # Exclude system/technical fields by prefix
        exclude_prefixes = ("_", "message_", "activity_", "website_message_")
        if field_name.startswith(exclude_prefixes):
            return False

        # Exclude specific technical fields
        exclude_fields = {
            "write_date",
            "create_date",
            "write_uid",
            "create_uid",
            "__last_update",
            "access_token",
            "access_warning",
            "access_url",
        }
        if field_name in exclude_fields:
            return False

        # Get field type
        field_type = field_info.get("type", "")

        # Exclude binary and large fields
        if field_type in ("binary", "image", "html"):
            return False

        # Exclude expensive computed fields (non-stored)
        if field_info.get("compute") and not field_info.get("store", True):
            return False

        # Exclude one2many and many2many fields (can be large)
        if field_type in ("one2many", "many2many"):
            return False

        # Include required fields
        if field_info.get("required"):
            return True

        # Include simple stored fields that are searchable
        if field_info.get("store", True) and field_info.get("searchable", True):
            if field_type in (
                "char",
                "text",
                "boolean",
                "integer",
                "float",
                "date",
                "datetime",
                "selection",
                "many2one",
            ):
                return True

        return False

    def _score_field_importance(self, field_name: str, field_info: Dict[str, Any]) -> int:
        """Score field importance for smart default selection.

        Args:
            field_name: Name of the field
            field_info: Field metadata from fields_get()

        Returns:
            Importance score (higher = more important)
        """
        # Tier 1: Essential fields (always included)
        if field_name in {"id", "name", "display_name", "active"}:
            return 1000

        # Exclude system/technical fields by prefix
        exclude_prefixes = ("_", "message_", "activity_", "website_message_")
        if field_name.startswith(exclude_prefixes):
            return 0

        # Exclude specific technical fields
        exclude_fields = {
            "write_date",
            "create_date",
            "write_uid",
            "create_uid",
            "__last_update",
            "access_token",
            "access_warning",
            "access_url",
        }
        if field_name in exclude_fields:
            return 0

        score = 0

        # Tier 2: Required fields are very important
        if field_info.get("required"):
            score += 500

        # Tier 3: Field type importance
        field_type = field_info.get("type", "")
        type_scores = {
            "char": 200,
            "boolean": 180,
            "selection": 170,
            "integer": 160,
            "float": 160,
            "monetary": 140,
            "date": 150,
            "datetime": 150,
            "many2one": 120,  # Relations useful but not primary
            "text": 80,
            "one2many": 40,
            "many2many": 40,  # Heavy relations
            "binary": 10,
            "html": 10,
            "image": 10,  # Heavy content
        }
        score += type_scores.get(field_type, 50)

        # Tier 4: Storage and searchability bonuses
        if field_info.get("store", True):
            score += 80
        if field_info.get("searchable", True):
            score += 40

        # Tier 5: Business-relevant field patterns (bonus)
        business_patterns = [
            "state",
            "status",
            "stage",
            "priority",
            "company",
            "currency",
            "amount",
            "total",
            "date",
            "user",
            "partner",
            "email",
            "phone",
            "address",
            "street",
            "city",
            "country",
            "code",
            "ref",
            "number",
        ]
        if any(pattern in field_name.lower() for pattern in business_patterns):
            score += 60

        # Exclude expensive computed fields (non-stored)
        if field_info.get("compute") and not field_info.get("store", True):
            score = min(score, 30)  # Cap computed fields at low score

        # Exclude large field types completely
        if field_type in ("binary", "image", "html"):
            return 0

        # Exclude one2many and many2many fields (can be large)
        if field_type in ("one2many", "many2many"):
            return 0

        return max(score, 0)

    def _get_smart_default_fields(
        self,
        model: str,
        connection: Optional[OdooConnectionProtocol] = None,
        preloaded_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        conn = connection or self.connection
        try:
            if preloaded_fields is not None:
                fields_info = preloaded_fields
            else:
                fields_info = conn.fields_get(model)

            # Score all fields by importance
            field_scores = []
            for field_name, field_info in fields_info.items():
                score = self._score_field_importance(field_name, field_info)
                if score > 0:  # Only include fields with positive scores
                    field_scores.append((field_name, score))

            # Sort by score (highest first)
            field_scores.sort(key=lambda x: x[1], reverse=True)

            # Select top N fields based on configuration
            max_fields = self.config.max_smart_fields
            selected_fields = [field_name for field_name, _ in field_scores[:max_fields]]

            # Ensure essential fields are always included
            essential_fields = ["id", "name", "display_name", "active"]
            for field in essential_fields:
                if field in fields_info and field not in selected_fields:
                    selected_fields.append(field)

            # Remove duplicates while preserving order
            final_fields = []
            seen = set()
            for field in selected_fields:
                if field not in seen:
                    final_fields.append(field)
                    seen.add(field)

            # Ensure we have at least essential fields
            if not final_fields:
                final_fields = [f for f in essential_fields if f in fields_info]

            logger.debug(
                f"Smart default fields for {model}: {len(final_fields)} of {len(fields_info)} fields "
                f"(max configured: {max_fields})"
            )
            return final_fields

        except Exception as e:
            logger.warning(f"Could not determine default fields for {model}: {e}")
            # Return None to indicate we should get all fields
            return None

    def _register_tools(self):
        """Register all tool handlers with FastMCP."""

        disabled = self.config.disabled_tools if self.config else frozenset()
        readonly_tools = {
            "create_record",
            "update_record",
            "delete_record",
            "create_records",
            "update_records",
            "delete_records",
        }

        if self.config and self.config.readonly:
            disabled = disabled | readonly_tools

        def _is_disabled(tool_name: str) -> bool:
            if tool_name.lower() in disabled:
                logger.info(
                    f"Tool '{tool_name}' is disabled by ODOO_MCP_DISABLED_TOOLS configuration"
                )
                return True
            return False

        configured_default_limit = self.config.default_limit if self.config else 10

        @self.app.tool(
            title="Search Records",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def search_records(
            model: str,
            domain: Optional[str | list[Any]] = None,
            fields: Optional[str | list[str]] = None,
            limit: int = configured_default_limit,
            offset: int = 0,
            order: Optional[str] = None,
            include_total: bool = True,
        ) -> SearchResult:
            """在Odoo模型中搜索记录。

            Args:
                model: Odoo模型名称 (例如 'res.partner')
                domain: Odoo domain过滤条件 - 可以是:
                    - 列表: [['is_company', '=', True]]
                    - JSON字符串: "[['is_company', '=', true]]"
                    - None: 返回所有记录 (默认)
                fields: 字段选择选项 - 可以是:
                    - None (默认): 返回智能选择的常用字段
                    - 列表: ["field1", "field2", ...] - 仅返回指定的字段
                    - JSON字符串: '["field1", "field2"]' - 解析为列表
                    - ["__all__"] 或 '["__all__"]': 返回所有字段 (警告: 可能导致序列化错误)
                limit: 返回记录的最大数量；省略时使用服务端 ODOO_MCP_DEFAULT_LIMIT，超过 ODOO_MCP_MAX_LIMIT 时会被截断
                offset: 跳过的记录数量
                order: 排序方式 (例如 'name asc')
                include_total: 是否额外执行 search_count 返回总数；大量查询可设为 false 以减少一次 Odoo RPC

            Returns:
                搜索结果，包含记录、总数和分页信息
            """
            result = await self._handle_search_tool(
                model, domain, fields, limit, offset, order, include_total
            )
            return SearchResult(**result)

        @self.app.tool(
            title="Get Record",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def get_record(
            model: str,
            record_id: int,
            fields: Optional[str | list[str]] = None,
        ) -> RecordResult:
            """通过ID获取特定记录，支持智能字段选择。

            此工具支持选择性获取字段以优化性能和响应大小。
            默认情况下，根据模型的字段元数据返回智能选择的常用字段。

            Args:
                model: Odoo模型名称 (例如 'res.partner')
                record_id: 记录ID
                fields: 字段选择选项:
                    - None (默认): 返回智能选择的常用字段
                    - ["field1", "field2", ...]: 仅返回指定字段
                    - ["__all__"]: 返回所有字段 (警告: 数据量可能非常大)

            字段发现工作流:
            1. 要查看模型的所有可用字段，使用资源:
               read("odoo://res.partner/fields")
            2. 然后请求特定字段:
               get_record("res.partner", 1, fields=["name", "email", "phone"])

            Examples:
                # 获取智能默认字段 (推荐)
                get_record("res.partner", 1)

                # 仅获取特定字段
                get_record("res.partner", 1, fields=["name", "email", "phone"])

                # 获取所有字段 (谨慎使用)
                get_record("res.partner", 1, fields=["__all__"])

            Returns:
                包含请求字段的记录数据。当使用智能默认时，
                会包含带有字段统计信息的元数据。
            """
            result = await self._handle_get_record_tool(model, record_id, fields)
            return result

        @self.app.tool(
            title="List Models",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def list_models(
            search: Optional[str] = None, limit: int = configured_default_limit, offset: int = 0
        ) -> ModelsResult:
            """列出允许MCP访问的模型。

            Args:
                search: 可选模型技术名或显示名关键字。
                limit: 最大返回数量；省略时使用服务端 ODOO_MCP_DEFAULT_LIMIT，超过 ODOO_MCP_MAX_LIMIT 时会被截断。
                offset: 跳过的模型数量。

            Returns:
                包含模型技术名称、显示名称以及允许操作(read, write, create, unlink)的列表。
            """
            result = await self._handle_list_models_tool(search, limit, offset)
            return ModelsResult(**result)

        @self.app.tool(
            title="Get Model Fields",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def get_model_fields(
            model: str,
            search: Optional[str] = None,
        ) -> Dict[str, Any]:
            """获取模型字段定义，可按字段名或显示名过滤。"""
            return await self._handle_get_model_fields_tool(model, search)

        @self.app.tool(
            title="Validate Domain",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def validate_domain(
            model: str,
            domain: Optional[str | list[Any]] = None,
        ) -> Dict[str, Any]:
            """校验Odoo domain语法并返回匹配数量。"""
            return await self._handle_validate_domain_tool(model, domain)

        @self.app.tool(
            title="List Resource Templates",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def list_resource_templates() -> ResourceTemplatesResult:
            """列出可用的资源URI模板。

            由于带有参数的MCP资源被注册为模板，
            它们不会出现在标准资源列表中。此工具提供
            关于可使用的可用资源模式的信息。

            Returns:
                包含示例和启用模型的资源模板定义。
            """
            result = await self._handle_list_resource_templates_tool()
            return ResourceTemplatesResult(**result)

        @self.app.tool(
            title="Get Public Config",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def get_public_config() -> PublicConfigResult:
            """获取可公开给 MCP 客户端使用的运行时配置。"""
            from .server import _BUILD_ORIGIN, SERVER_VERSION

            config = self.config
            return PublicConfigResult(
                default_limit=config.default_limit if config else 10,
                max_limit=config.max_limit if config else 100,
                readonly=config.readonly if config else True,
                transport=config.transport if config else "stdio",
                api_version=config.api_version if config else "unknown",
                odoo_url=self._sanitize_public_url(config.url if config else None),
                server_version=SERVER_VERSION,
                runtime_id=_BUILD_ORIGIN,
                max_bulk_size=config.max_bulk_size if config else DEFAULT_MAX_BULK_SIZE,
                max_smart_fields=config.max_smart_fields if config else 15,
                strict_security=config.strict_security if config else True,
                stateless_http=config.stateless_http if config else True,
            )

        @self.app.tool(
            title="Server Info",
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def server_info() -> ServerInfoResult:
            """获取MCP服务器版本和连接状态。

            Returns:
                服务器版本、git commit、API版本和Odoo连接状态。
            """
            from .server import _BUILD_ORIGIN, GIT_COMMIT, SERVER_VERSION

            try:
                connection, _ac, _sub = await self._get_user_context()
                is_connected = (
                    connection.is_authenticated
                    if hasattr(connection, "is_authenticated")
                    else False
                )
                api_version = self.config.api_version if self.config else "json2"
                # Use the connection's actual URL (tenant URL), not the global config
                odoo_url = getattr(connection, "_base_url", None) or (
                    self.config.url if self.config else "multi-tenant"
                )
            except Exception:
                is_connected = False
                api_version = self.config.api_version if self.config else "unknown"
                odoo_url = "not connected"

            # Fetch companies for context (helps with multi-company setups)
            companies = []
            if is_connected:
                try:
                    companies = await self._odoo_call(
                        "tool_server_info_companies",
                        lambda: connection.search_read(
                            "res.company", [], fields=["id", "name"], limit=10
                        ),
                    )
                except Exception:
                    pass
            health = None
            if self.connection_manager is not None:
                health = self.connection_manager.get_health_status()

            return ServerInfoResult(
                version=SERVER_VERSION,
                git_commit=GIT_COMMIT,
                api_version=api_version,
                odoo_url=odoo_url,
                connected=is_connected,
                runtime_id=_BUILD_ORIGIN,
                companies=companies,
                health=health,
            )

        # --- Write Operations (conditionally registered) ---

        if not _is_disabled("create_record"):

            @self.app.tool(
                title="Create Record",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
            async def create_record(
                model: str,
                values: Dict[str, Any],
            ) -> CreateResult:
                """在Odoo模型中创建新记录。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    values: 新记录的字段值

                Returns:
                    创建的记录详情，包含ID、URL和确认信息。
                """
                result = await self._handle_create_record_tool(model, values)
                return CreateResult(**result)

        if not _is_disabled("update_record"):

            @self.app.tool(
                title="Update Record",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
            )
            async def update_record(
                model: str,
                record_id: int,
                values: Dict[str, Any],
            ) -> UpdateResult:
                """更新现有记录。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    record_id: 要更新的记录ID
                    values: 要更新的字段值

                Returns:
                    更新后的记录详情和确认信息。
                """
                result = await self._handle_update_record_tool(model, record_id, values)
                return UpdateResult(**result)

        if not _is_disabled("delete_record"):

            @self.app.tool(
                title="Delete Record",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
            async def delete_record(
                model: str,
                record_id: int,
            ) -> DeleteResult:
                """删除一条记录。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    record_id: 要删除的记录ID

                Returns:
                    删除确认信息，包含被删除记录的名称和ID。
                """
                result = await self._handle_delete_record_tool(model, record_id)
                return DeleteResult(**result)

        # --- Bulk Operations (conditionally registered) ---

        if not _is_disabled("create_records"):

            @self.app.tool(
                title="Create Records (Bulk)",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
            async def create_records(
                model: str,
                vals_list: List[Dict[str, Any]],
            ) -> BulkCreateResult:
                """在一次操作中创建多条记录 (最大配置数量)。

                比重复调用 create_record 快得多。在导入数据、
                批量创建记录或任何涉及多条记录的场景中使用此工具。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    vals_list: 字典列表，每个字典包含一条记录的字段值。
                        示例: [{"name": "Alice"}, {"name": "Bob"}]

                Returns:
                    创建的记录ID列表，包含数量和确认信息。
                """
                result = await self._handle_create_records_tool(model, vals_list)
                return BulkCreateResult(**result)

        if not _is_disabled("update_records"):

            @self.app.tool(
                title="Update Records (Bulk)",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
            )
            async def update_records(
                model: str,
                record_ids: List[int],
                values: Dict[str, Any],
            ) -> BulkUpdateResult:
                """在一次操作中将相同的值更新到多条记录 (最大配置数量)。

                用于大规模更新，如给联系人打标签、更改状态、
                或同时对多条记录应用相同的更改。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    record_ids: 要更新的记录ID列表
                    values: 要应用到所有指定记录的字段值

                Returns:
                    更新的记录ID列表，包含数量和确认信息。
                """
                result = await self._handle_update_records_tool(model, record_ids, values)
                return BulkUpdateResult(**result)

        if not _is_disabled("delete_records"):

            @self.app.tool(
                title="Delete Records (Bulk)",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
            async def delete_records(
                model: str,
                record_ids: List[int],
            ) -> BulkDeleteResult:
                """在一次操作中删除多条记录 (最大配置数量)。

                Args:
                    model: Odoo模型名称 (例如 'res.partner')
                    record_ids: 要删除的记录ID列表

                Returns:
                    删除的记录ID列表，包含数量和确认信息。
                """
                result = await self._handle_delete_records_tool(model, record_ids)
                return BulkDeleteResult(**result)

        # --- Advanced RPC Operations ---

        if not _is_disabled("execute_method"):

            @self.app.tool(
                title="Execute Method",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
            async def execute_method(
                model: str,
                method: str,
                record_ids: Optional[List[int]] = None,
                args: Optional[List[Any]] = None,
                kwargs: Optional[Dict[str, Any]] = None,
            ) -> ExecuteMethodResult:
                """在Odoo模型上执行任意安全方法（按钮点击、业务动作等）。

                这是执行表单按钮点击和业务流程的核心工具。
                通过XML-RPC的execute_kw直接调用Odoo模型方法。

                典型用途:
                - 点击按钮: execute_method("sale.order", "action_confirm", record_ids=[5])
                - 确认发票: execute_method("account.move", "action_post", record_ids=[10])
                - 验证库存: execute_method("stock.picking", "button_validate", record_ids=[3])
                - 取消订单: execute_method("purchase.order", "button_cancel", record_ids=[7])
                - 归档/取消归档: execute_method("res.partner", "toggle_active", record_ids=[1])
                - name_search: execute_method("res.partner", "name_search", kwargs={"name": "test"})
                - read_group: execute_method("sale.order", "read_group",
                    args=[[["state", "=", "sale"]], ["amount_total:sum"]], kwargs={"groupby": ["partner_id"], "limit": 10})

                安全策略:
                - 只允许调用白名单方法或以 action_、button_、onchange_ 开头的方法
                - readonly模式下禁止调用会修改数据的方法
                - 需要模型的写权限才能调用状态变更方法

                Args:
                    model: Odoo模型名称 (例如 'sale.order')
                    method: 要调用的方法名 (例如 'action_confirm')
                    record_ids: 记录ID列表。对于需要记录上下文的方法（如按钮点击）必须提供。
                        方法签名中 self 即为这些记录。
                        对于类级别方法（如 name_search、read_group）可不提供。
                    args: 方法的额外位置参数 (可选)
                    kwargs: 方法的关键字参数 (可选)

                Returns:
                    方法调用的原始返回值和执行状态
                """
                result = await self._handle_execute_method_tool(
                    model, method, record_ids, args, kwargs
                )
                return ExecuteMethodResult(**result)

        if not _is_disabled("call_json_endpoint"):

            @self.app.tool(
                title="Call JSON Endpoint",
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
            )
            async def call_json_endpoint(
                endpoint: str,
                params: Optional[Dict[str, Any]] = None,
            ) -> Dict[str, Any]:
                """调用Odoo HTTP JSON端点（用于需要HTTP上下文的控制器方法）。

                某些Odoo方法（如web_approval审批流程）是HTTP控制器，依赖request.env上下文，
                无法通过XML-RPC的execute_method调用。此工具通过HTTP JSON请求直接调用这些端点。

                典型用途:
                - 提交审批: call_json_endpoint("/web/approval/commit_approval", {"model": "sale.order", "res_id": 5})
                - 其他需要HTTP上下文的控制器端点

                安全策略:
                - 只允许调用/web/开头的已知安全端点
                - readonly模式下只允许GET类操作

                Args:
                    endpoint: Odoo JSON端点路径 (例如 '/web/approval/commit_approval')
                    params: 传递给端点的参数字典 (可选)

                Returns:
                    端点的JSON响应
                """
                result = await self._handle_call_json_endpoint_tool(endpoint, params)
                return result

        if not _is_disabled("simulate_onchange"):

            @self.app.tool(
                title="Simulate Onchange",
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
            async def simulate_onchange(
                model: str,
                field_name: str,
                field_value: Any = None,
                record_id: Optional[int] = None,
                values: Optional[Dict[str, Any]] = None,
            ) -> OnchangeResult:
                """模拟Odoo字段的onchange行为，预测字段值变化。

                当你在UI中修改一个字段时，Odoo会自动触发onchange计算。
                此工具让你可以在不实际修改记录的情况下预览这些变化。

                典型用途:
                - 修改客户时预览地址变化
                - 修改产品时预览价格计算
                - 修改税率时预览税额变化
                - 创建新记录时预览默认值填充

                Examples:
                    # 修改销售订单的客户，预览变化
                    simulate_onchange("sale.order", "partner_id", 1, record_id=5)

                    # 创建新记录时修改产品，预览行变化
                    simulate_onchange("sale.order.line", "product_id", 3,
                        values={"order_id": 5})

                Args:
                    model: Odoo模型名称 (例如 'sale.order')
                    field_name: 触发onchange的字段名 (例如 'partner_id')
                    field_value: 字段的新值
                    record_id: 已有记录的ID (修改场景)。不提供则为新建场景。
                    values: 表单中其他字段的当前值 (新建场景必填)

                Returns:
                    onchange返回的value、warning和domain
                """
                result = await self._handle_simulate_onchange_tool(
                    model, field_name, field_value, record_id, values
                )
                return OnchangeResult(**result)

        if not _is_disabled("get_model_methods"):

            @self.app.tool(
                title="Get Model Methods",
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
            async def get_model_methods(
                model: str,
                search: Optional[str] = None,
            ) -> ModelMethodResult:
                """获取模型上可用的业务方法（按钮动作等）。

                通过反射分析模型的Python源码，提取可被 execute_method 调用的方法。
                主要用于发现表单按钮对应的动作方法名。

                典型用途:
                - 查看销售订单有哪些按钮动作: get_model_methods("sale.order")
                - 搜索确认相关方法: get_model_methods("sale.order", search="confirm")
                - 查看发票可执行的操作: get_model_methods("account.move")

                Args:
                    model: Odoo模型名称 (例如 'sale.order')
                    search: 可选关键字，过滤方法名或显示名

                Returns:
                    模型上可用的方法列表，包含方法名和描述
                """
                result = await self._handle_get_model_methods_tool(model, search)
                return ModelMethodResult(**result)

    def _parse_domain_param(self, domain: Optional[Any]) -> List[Any]:
        if domain is None:
            return []
        if isinstance(domain, str):
            try:
                parsed_domain = json.loads(domain)
            except json.JSONDecodeError:
                try:
                    json_domain = domain.replace("'", '"')
                    json_domain = json_domain.replace("True", "true").replace("False", "false")
                    parsed_domain = json.loads(json_domain)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        f"Invalid domain parameter. Expected JSON array, got: {domain[:100]}..."
                    ) from e
        else:
            parsed_domain = domain

        if not isinstance(parsed_domain, list):
            raise ValidationError(f"Domain must be a list, got {type(parsed_domain).__name__}")
        return parsed_domain

    def _parse_fields_param(self, fields: Optional[Any]) -> Optional[List[str]]:
        if fields is None:
            return None
        parsed_fields = fields
        if isinstance(fields, str):
            try:
                parsed_fields = json.loads(fields)
            except json.JSONDecodeError as e:
                raise ValidationError(
                    f"Invalid fields parameter. Expected JSON array, got: {fields[:100]}..."
                ) from e
        if not isinstance(parsed_fields, list):
            raise ValidationError(f"Fields must be a list, got {type(parsed_fields).__name__}")
        if not all(isinstance(field, str) for field in parsed_fields):
            raise ValidationError("Fields must be a list of field names")
        return parsed_fields

    async def _handle_search_tool(
        self,
        model: str,
        domain: Optional[Any],
        fields: Optional[Any],
        limit: int,
        offset: int,
        order: Optional[str],
        include_total: bool = True,
    ) -> Dict[str, Any]:
        """Handle search tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_search", model=model):
                # Check model access
                access_controller.validate_model_access(model, "read")

                # Ensure we're connected
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                # Handle domain parameter - can be string or list
                parsed_domain = self._parse_domain_param(domain)
                logger.debug(f"Parsed domain: {parsed_domain}")

                # Handle fields parameter - can be string or list
                parsed_fields = self._parse_fields_param(fields)

                limit = self._normalize_limit(limit)

                total_count = None
                if include_total:
                    total_count = await self._odoo_call(
                        "tool_search_count",
                        lambda: connection.search_count(model, parsed_domain),
                        operation_class="heavy",
                    )

                # Determine which fields to fetch (before search_read)
                fields_to_fetch = parsed_fields
                if parsed_fields is None:
                    fields_to_fetch = self._get_smart_default_fields(model, connection)
                    logger.debug(
                        f"Using smart defaults for {model} search: {len(fields_to_fetch) if fields_to_fetch else 'all'} fields"
                    )
                elif parsed_fields == ["__all__"]:
                    fields_to_fetch = None
                    logger.debug(f"Fetching all fields for {model} search")

                # Search + read in one RPC call (was 2 separate calls: search + read)
                records = []
                search_kwargs = {}
                if limit is not None:
                    search_kwargs["limit"] = limit
                if offset is not None:
                    search_kwargs["offset"] = offset
                if order:
                    search_kwargs["order"] = order

                operation_class = (
                    "heavy" if limit >= 50 or parsed_fields == ["__all__"] else "light"
                )
                records = await self._odoo_call(
                    "tool_search_read",
                    lambda: connection.search_read(
                        model, parsed_domain, fields=fields_to_fetch, **search_kwargs
                    ),
                    operation_class=operation_class,
                )
                records = [
                    self._process_record_dates(record, model, connection) for record in records
                ]

                if total_count is None:
                    total_count = offset + len(records)

                return {
                    "records": records,
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "model": model,
                }

        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in search_records tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Search failed: {sanitized_msg}") from e

    async def _handle_get_record_tool(
        self,
        model: str,
        record_id: int,
        fields: Optional[List[str]],
    ) -> RecordResult:
        """Handle get record tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_get_record", model=model):
                # Check model access
                access_controller.validate_model_access(model, "read")

                # Ensure we're connected
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                # Determine which fields to fetch
                fields_to_fetch = fields
                use_smart_defaults = False
                total_fields = None
                field_selection_method = "explicit"
                all_fields_info = None

                if fields is None:
                    all_fields_info = self.perf_manager.get_cached_fields(model)
                    if all_fields_info is None:
                        all_fields_info = await self._odoo_call(
                            "tool_get_record_fields_get",
                            lambda: connection.fields_get(model),
                        )
                        self.perf_manager.cache_fields(model, all_fields_info)
                    fields_to_fetch = self._get_smart_default_fields(
                        model, connection, all_fields_info
                    )
                    use_smart_defaults = True
                    field_selection_method = "smart_defaults"
                    total_fields = len(all_fields_info)
                    logger.debug(
                        f"Using smart defaults for {model}: {len(fields_to_fetch) if fields_to_fetch else 'all'} fields"
                    )
                elif fields == ["__all__"]:
                    fields_to_fetch = None
                    field_selection_method = "all"
                    logger.debug(f"Fetching all fields for {model}")
                else:
                    logger.debug(f"Fetching specific fields for {model}: {fields}")

                cached_record = self.perf_manager.get_cached_record(
                    model, record_id, fields_to_fetch
                )
                if cached_record is not None:
                    record = cached_record
                else:
                    records = await self._odoo_call(
                        "tool_get_record_read",
                        lambda: connection.read(model, [record_id], fields_to_fetch),
                    )
                    if not records:
                        raise ValidationError(f"Record not found: {model} with ID {record_id}")
                    record = self._process_record_dates(records[0], model, connection)
                    self.perf_manager.cache_record(model, record, fields_to_fetch, ttl_seconds=60)

                metadata = None
                if use_smart_defaults:
                    metadata = FieldSelectionMetadata(
                        fields_returned=len(record),
                        field_selection_method=field_selection_method,
                        total_fields_available=total_fields,
                        note=f"Limited fields returned for performance. Use fields=['__all__'] for all fields or see odoo://{model}/fields for available fields.",
                    )

                return RecordResult(record=record, metadata=metadata)

        except ValidationError:
            raise
        except NotFoundError as e:
            raise ValidationError(str(e)) from e
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in get_record tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to get record: {sanitized_msg}") from e

    async def _handle_list_models_tool(
        self, search: Optional[str] = None, limit: int = 0, offset: int = 0
    ) -> Dict[str, Any]:
        """Handle list models tool request with permissions."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_list_models"):
                limit = self._normalize_limit(limit)

                # Get models from MCP access controller
                models = access_controller.get_enabled_models()

                # In JSON/2 mode, get_enabled_models() returns [] because Odoo
                # handles ACLs server-side. Fetch models from ir.model instead.
                if not models and hasattr(connection, "search_read"):
                    try:
                        domain = [["transient", "=", False]]
                        if search:
                            domain = [
                                ["transient", "=", False],
                                "|",
                                ["model", "ilike", search],
                                ["name", "ilike", search],
                            ]
                        ir_models = await self._odoo_call(
                            "tool_list_models_search_read",
                            lambda: connection.search_read(
                                "ir.model",
                                domain,
                                fields=["model", "name"],
                                limit=limit,
                                offset=offset,
                                order="model asc",
                            ),
                        )
                        models = [{"model": m["model"], "name": m["name"]} for m in ir_models]
                    except Exception as e:
                        logger.warning(f"Could not fetch models from ir.model: {e}")
                        models = []
                else:
                    if search:
                        needle = search.lower()
                        models = [
                            model
                            for model in models
                            if needle in model.get("model", "").lower()
                            or needle in model.get("name", "").lower()
                        ]
                    models = models[offset : offset + limit]

                return {"models": models, "total": len(models)}
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in list_models tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to list models: {sanitized_msg}") from e

    async def _handle_get_model_fields_tool(
        self, model: str, search: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_get_model_fields", model=model):
                access_controller.validate_model_access(model, "read")
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                fields = await self._odoo_call(
                    "tool_get_model_fields",
                    lambda: connection.fields_get(model),
                )
                if search:
                    needle = search.lower()
                    fields = {
                        name: info
                        for name, info in fields.items()
                        if needle in name.lower() or needle in str(info.get("string", "")).lower()
                    }
                return {"model": model, "fields": fields, "total": len(fields)}
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except Exception as e:
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to get model fields: {sanitized_msg}") from e

    async def _handle_validate_domain_tool(
        self, model: str, domain: Optional[Any] = None
    ) -> Dict[str, Any]:
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_validate_domain", model=model):
                access_controller.validate_model_access(model, "read")
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                parsed_domain = self._parse_domain_param(domain)
                count = await self._odoo_call(
                    "tool_validate_domain_count",
                    lambda: connection.search_count(model, parsed_domain),
                )
                return {"valid": True, "model": model, "domain": parsed_domain, "count": count}
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except ValidationError:
            raise
        except Exception as e:
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Invalid domain for {model}: {sanitized_msg}") from e

    async def _handle_list_resource_templates_tool(self) -> Dict[str, Any]:
        """Handle list resource templates tool request."""
        try:
            _, access_controller, sub = await self._get_user_context()
            # Get list of enabled models that can be used with resources
            enabled_models = access_controller.get_enabled_models()
            model_names = [m["model"] for m in enabled_models if m.get("read", True)]

            # Define the resource templates
            templates = [
                {
                    "uri_template": "odoo://{model}/record/{record_id}",
                    "description": "Get a specific record by ID",
                    "parameters": {
                        "model": "Odoo model name (e.g., res.partner)",
                        "record_id": "Record ID (e.g., 10)",
                    },
                    "example": "odoo://res.partner/record/10",
                },
                {
                    "uri_template": "odoo://{model}/search",
                    "description": "Basic search returning first 10 records",
                    "parameters": {
                        "model": "Odoo model name",
                    },
                    "example": "odoo://res.partner/search",
                    "note": "Query parameters are not supported. Use search_records tool for advanced queries.",
                },
                {
                    "uri_template": "odoo://{model}/count",
                    "description": "Count all records in a model",
                    "parameters": {
                        "model": "Odoo model name",
                    },
                    "example": "odoo://res.partner/count",
                    "note": "Query parameters are not supported. Use search_records tool for filtered counts.",
                },
                {
                    "uri_template": "odoo://{model}/fields",
                    "description": "Get field definitions for a model",
                    "parameters": {"model": "Odoo model name"},
                    "example": "odoo://res.partner/fields",
                },
            ]

            # Return the resource template information
            return {
                "templates": templates,
                "enabled_models": model_names[:10],  # Show first 10 as examples
                "total_models": len(model_names),
                "note": "Resource URIs do not support query parameters. Use tools (search_records, get_record) for advanced operations with filtering, pagination, and field selection.",
            }

        except Exception as e:
            logger.error(f"Error in list_resource_templates tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to list resource templates: {sanitized_msg}") from e

    async def _handle_create_record_tool(
        self,
        model: str,
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle create record tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_create_record", model=model):
                # Check model access
                access_controller.validate_model_access(model, "create")

                # Ensure we're connected
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                # Validate required fields
                if not values:
                    raise ValidationError("No values provided for record creation")

                # Create the record
                record_id = await self._odoo_call(
                    "tool_create_record_create",
                    lambda: connection.create(model, values),
                    operation_class="write",
                )

                # Return only essential fields to minimize context usage
                # Users can use get_record if they need more fields
                essential_fields = ["id", "name", "display_name"]

                # Filter to fields that actually exist on this model
                try:
                    model_fields = await self._odoo_call(
                        "tool_model_fields_get",
                        lambda: connection.fields_get(model, ["string", "type"]),
                    )
                    essential_fields = [f for f in essential_fields if f in model_fields]
                    if "id" not in essential_fields:
                        essential_fields.insert(0, "id")
                except Exception:
                    essential_fields = ["id"]

                # Read only the essential fields
                records = await self._odoo_call(
                    "tool_record_read_essential",
                    lambda: connection.read(model, [record_id], essential_fields),
                )
                if not records:
                    raise ValidationError(
                        f"Failed to read created record: {model} with ID {record_id}"
                    )

                # Process dates in the minimal record
                record = self._process_record_dates(records[0], model, connection)

                self.perf_manager.cache_record(model, record, ttl_seconds=60)

                base_url = (
                    getattr(connection, "_base_url", None)
                    or (self.config.url if self.config else "")
                ).rstrip("/")
                record_url = f"{base_url}/web#id={record_id}&model={model}&view_type=form"

                return {
                    "success": True,
                    "record": record,
                    "url": record_url,
                    "message": f"Successfully created {model} record with ID {record_id}",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in create_record tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to create record: {sanitized_msg}") from e

    async def _handle_update_record_tool(
        self,
        model: str,
        record_id: int,
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle update record tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_update_record", model=model):
                # Check model access
                access_controller.validate_model_access(model, "write")

                # Ensure we're connected
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                # Validate input
                if not values:
                    raise ValidationError("No values provided for record update")

                # Check if record exists (only fetch ID to verify existence)
                existing = await self._odoo_call(
                    "tool_update_record_exists",
                    lambda: connection.read(model, [record_id], ["id"]),
                )
                if not existing:
                    raise NotFoundError(f"Record not found: {model} with ID {record_id}")

                # Update the record
                success = await self._odoo_call(
                    "tool_update_record_write",
                    lambda: connection.write(model, [record_id], values),
                    operation_class="write",
                )

                # Return only essential fields to minimize context usage
                # Users can use get_record if they need more fields
                essential_fields = ["id", "name", "display_name"]

                # Filter to fields that actually exist on this model
                try:
                    model_fields = await self._odoo_call(
                        "tool_model_fields_get",
                        lambda: connection.fields_get(model, ["string", "type"]),
                    )
                    essential_fields = [f for f in essential_fields if f in model_fields]
                    if "id" not in essential_fields:
                        essential_fields.insert(0, "id")
                except Exception:
                    essential_fields = ["id"]

                # Read only the essential fields
                records = await self._odoo_call(
                    "tool_record_read_essential",
                    lambda: connection.read(model, [record_id], essential_fields),
                )
                if not records:
                    raise ValidationError(
                        f"Failed to read updated record: {model} with ID {record_id}"
                    )

                # Process dates in the minimal record
                record = self._process_record_dates(records[0], model, connection)

                # Generate direct URL to the record in Odoo
                base_url = (
                    getattr(connection, "_base_url", None)
                    or (self.config.url if self.config else "")
                ).rstrip("/")
                record_url = f"{base_url}/web#id={record_id}&model={model}&view_type=form"

                return {
                    "success": success,
                    "record": record,
                    "url": record_url,
                    "message": f"Successfully updated {model} record with ID {record_id}",
                }

        except ValidationError:
            raise
        except NotFoundError as e:
            raise ValidationError(str(e)) from e
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in update_record tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to update record: {sanitized_msg}") from e

    async def _handle_delete_record_tool(
        self,
        model: str,
        record_id: int,
    ) -> Dict[str, Any]:
        """Handle delete record tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_delete_record", model=model):
                # Check model access
                access_controller.validate_model_access(model, "unlink")

                # Ensure we're connected
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                # Check if record exists
                existing = await self._odoo_call(
                    "tool_delete_record_read_existing",
                    lambda: connection.read(model, [record_id]),
                )
                if not existing:
                    raise NotFoundError(f"Record not found: {model} with ID {record_id}")

                # Store some info about the record before deletion
                record_name = existing[0].get(
                    "name", existing[0].get("display_name", f"ID {record_id}")
                )

                # Delete the record
                success = await self._odoo_call(
                    "tool_delete_record_unlink",
                    lambda: connection.unlink(model, [record_id]),
                    operation_class="write",
                )

                return {
                    "success": success,
                    "deleted_id": record_id,
                    "deleted_name": record_name,
                    "message": f"Successfully deleted {model} record '{record_name}' (ID: {record_id})",
                }

        except ValidationError:
            raise
        except NotFoundError as e:
            raise ValidationError(str(e)) from e
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in delete_record tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to delete record: {sanitized_msg}") from e

    def _bulk_limit(self) -> int:
        return self.config.max_bulk_size if self.config else DEFAULT_MAX_BULK_SIZE

    # --- Bulk Operation Handlers ---

    async def _handle_create_records_tool(
        self,
        model: str,
        vals_list: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Handle bulk create tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_create_records", model=model):
                access_controller.validate_model_access(model, "create")
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")
                if not vals_list:
                    raise ValidationError("vals_list cannot be empty")
                bulk_limit = self._bulk_limit()
                if len(vals_list) > bulk_limit:
                    raise ValidationError(
                        f"Bulk create limited to {bulk_limit} records, got {len(vals_list)}"
                    )

                created_ids = await self._odoo_call(
                    "tool_create_records_bulk",
                    lambda: connection.create_bulk(model, vals_list),
                    operation_class="write",
                )

                return {
                    "success": True,
                    "created_ids": created_ids,
                    "count": len(created_ids),
                    "model": model,
                    "message": f"Successfully created {len(created_ids)} {model} record(s)",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in create_records tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Bulk create failed: {sanitized_msg}") from e

    async def _handle_update_records_tool(
        self,
        model: str,
        record_ids: List[int],
        values: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle bulk update tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_update_records", model=model):
                access_controller.validate_model_access(model, "write")
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")
                if not record_ids:
                    raise ValidationError("record_ids cannot be empty")
                if not values:
                    raise ValidationError("values cannot be empty")
                bulk_limit = self._bulk_limit()
                if len(record_ids) > bulk_limit:
                    raise ValidationError(
                        f"Bulk update limited to {bulk_limit} records, got {len(record_ids)}"
                    )

                await self._odoo_call(
                    "tool_update_records_bulk",
                    lambda: connection.write(model, record_ids, values),
                    operation_class="write",
                )

                for rid in record_ids:
                    self.perf_manager.invalidate_record_cache(model, rid)

                return {
                    "success": True,
                    "updated_ids": record_ids,
                    "count": len(record_ids),
                    "model": model,
                    "message": f"Successfully updated {len(record_ids)} {model} record(s)",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in update_records tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Bulk update failed: {sanitized_msg}") from e

    async def _handle_delete_records_tool(
        self,
        model: str,
        record_ids: List[int],
    ) -> Dict[str, Any]:
        """Handle bulk delete tool request."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_delete_records", model=model):
                access_controller.validate_model_access(model, "unlink")
                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")
                if not record_ids:
                    raise ValidationError("record_ids cannot be empty")
                bulk_limit = self._bulk_limit()
                if len(record_ids) > bulk_limit:
                    raise ValidationError(
                        f"Bulk delete limited to {bulk_limit} records, got {len(record_ids)}"
                    )

                await self._odoo_call(
                    "tool_delete_records_bulk",
                    lambda: connection.unlink(model, record_ids),
                    operation_class="write",
                )

                for rid in record_ids:
                    self.perf_manager.invalidate_record_cache(model, rid)

                return {
                    "success": True,
                    "deleted_ids": record_ids,
                    "count": len(record_ids),
                    "model": model,
                    "message": f"Successfully deleted {len(record_ids)} {model} record(s)",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in delete_records tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Bulk delete failed: {sanitized_msg}") from e

    # --- Advanced RPC Operation Handlers ---

    async def _handle_execute_method_tool(
        self,
        model: str,
        method: str,
        record_ids: Optional[List[int]],
        args: Optional[List[Any]],
        kwargs: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation(f"tool_execute_method_{model}_{method}"):
                allowed, error_msg = access_controller.validate_method_call(model, method)
                if not allowed:
                    raise ValidationError(f"Access denied: {error_msg}")

                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                rpc_args = record_ids or []
                if args:
                    rpc_args = rpc_args + list(args)

                rpc_kwargs = kwargs or {}

                logger.info(
                    f"execute_method: {model}.{method}(args={rpc_args}, kwargs={rpc_kwargs})"
                )

                try:
                    result = await self._odoo_call(
                        f"tool_execute_{method}",
                        lambda m=model, mt=method, a=rpc_args, k=rpc_kwargs: connection.execute_kw(
                            m, mt, a, k
                        ),
                        operation_class="write"
                        if method in {"create", "write", "unlink"} or method.startswith("action_")
                        else "heavy",
                    )
                except OdooConnectionError as rpc_err:
                    none_hint = "cannot marshal None" in str(rpc_err)
                    if none_hint:
                        logger.warning(
                            f"Method {model}.{method} returned None which XML-RPC cannot serialize. "
                            f"Treating as successful execution with no return value."
                        )
                        result = None
                    else:
                        raise

                message = f"Successfully called {model}.{method}()"
                if record_ids:
                    message = f"Successfully called {model}.{method}() on records {record_ids}"
                if result is None:
                    message += " (method returned no value)"

                if record_ids:
                    for rid in record_ids:
                        self.perf_manager.invalidate_record_cache(model, rid)

                return {
                    "success": True,
                    "model": model,
                    "method": method,
                    "result": result,
                    "message": message,
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in execute_method tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Method execution failed: {sanitized_msg}") from e

    async def _handle_call_json_endpoint_tool(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle call_json_endpoint tool execution."""
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation(f"tool_json_endpoint_{endpoint}"):
                # Validate endpoint is safe
                allowed, error_msg = access_controller.validate_json_endpoint(endpoint)
                if not allowed:
                    raise ValidationError(f"Access denied: {error_msg}")

                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                logger.info(f"call_json_endpoint: {endpoint} params={params}")

                result = await self._odoo_call(
                    f"tool_json_{endpoint}",
                    lambda ep=endpoint, p=params: connection.call_json_endpoint(ep, p),
                    operation_class="write",
                )

                return {
                    "success": True,
                    "endpoint": endpoint,
                    "result": result,
                    "message": f"Successfully called {endpoint}",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in call_json_endpoint tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"JSON endpoint call failed: {sanitized_msg}") from e

    async def _handle_simulate_onchange_tool(
        self,
        model: str,
        field_name: str,
        field_value: Any,
        record_id: Optional[int],
        values: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_simulate_onchange", model=model):
                access_controller.validate_model_access(model, "read")

                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                onchange_args: List[Any] = []
                onchange_kwargs: Dict[str, Any] = {}

                if record_id:
                    existing = await self._odoo_call(
                        "tool_onchange_read_existing",
                        lambda: connection.read(model, [record_id]),
                    )
                    if not existing:
                        raise ValidationError(f"Record not found: {model} with ID {record_id}")
                    current_values = existing[0]
                    current_values[field_name] = field_value
                    if values:
                        current_values.update(values)
                    onchange_args = [current_values]
                    onchange_kwargs = {
                        "field_name": field_name,
                        "field_onchange": {field_name: "1"},
                    }
                else:
                    form_values = values or {}
                    form_values[field_name] = field_value
                    onchange_args = [form_values]
                    onchange_kwargs = {
                        "field_name": field_name,
                        "field_onchange": {field_name: "1"},
                    }

                result = await self._odoo_call(
                    "tool_onchange_execute",
                    lambda: connection.execute_kw(
                        model, "onchange", onchange_args, onchange_kwargs
                    ),
                    operation_class="heavy",
                )

                onchange_value = None
                onchange_warning = None
                onchange_domain = None

                if isinstance(result, dict):
                    onchange_value = result.get("value")
                    onchange_warning = result.get("warning")
                    onchange_domain = result.get("domain")

                return {
                    "success": True,
                    "model": model,
                    "method": "onchange",
                    "value": onchange_value,
                    "warning": onchange_warning,
                    "domain": onchange_domain,
                    "message": f"Onchange simulation completed for {model}.{field_name}",
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in simulate_onchange tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Onchange simulation failed: {sanitized_msg}") from e

    async def _handle_get_model_methods_tool(
        self,
        model: str,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            connection, access_controller, sub = await self._get_user_context()
            with perf_logger.track_operation("tool_get_model_methods", model=model):
                access_controller.validate_model_access(model, "read")

                if not connection.is_authenticated:
                    raise ValidationError("Not authenticated with Odoo")

                all_methods: List[Dict[str, Any]] = []

                safe_prefixes = AccessController.SAFE_METHOD_PREFIXES
                safe_names = AccessController.SAFE_METHOD_NAMES

                for name in sorted(safe_names):
                    method_info: Dict[str, Any] = {"name": name}
                    if name.startswith("action_"):
                        method_info["type"] = "action"
                    elif name.startswith("button_"):
                        method_info["type"] = "button"
                    elif name.startswith(("onchange_", "_onchange_")):
                        method_info["type"] = "onchange"
                    elif name in ("create", "write", "read", "unlink", "copy"):
                        method_info["type"] = "crud"
                    elif name in (
                        "search",
                        "search_read",
                        "search_count",
                        "read_group",
                        "name_get",
                        "name_search",
                        "name_create",
                    ):
                        method_info["type"] = "query"
                    elif name.startswith("message_"):
                        method_info["type"] = "mail"
                    else:
                        method_info["type"] = "utility"
                    all_methods.append(method_info)

                all_methods.append(
                    {
                        "name": "onchange",
                        "type": "onchange",
                        "description": "Simulate field onchange behavior",
                    }
                )

                model_info = await self._odoo_call(
                    "tool_get_model_info",
                    lambda: connection.search_read(
                        "ir.model",
                        [["model", "=", model]],
                        fields=["name"],
                        limit=1,
                    ),
                )
                _model_display_name = model_info[0]["name"] if model_info else model  # noqa: F841

                for prefix in safe_prefixes:
                    method_info = {
                        "name": f"{prefix}*",
                        "type": "action"
                        if prefix.startswith("action_")
                        else "button"
                        if prefix.startswith("button_")
                        else "onchange",
                        "description": f"Any method starting with '{prefix}' (wildcard)",
                        "pattern": True,
                    }
                    all_methods.append(method_info)

                if search:
                    needle = search.lower()
                    all_methods = [
                        m
                        for m in all_methods
                        if needle in m["name"].lower()
                        or needle in str(m.get("description", "")).lower()
                        or needle in str(m.get("type", "")).lower()
                    ]

                return {
                    "model": model,
                    "methods": all_methods,
                    "total": len(all_methods),
                }

        except ValidationError:
            raise
        except AccessControlError as e:
            raise ValidationError(f"Access denied: {e}") from e
        except OdooConnectionError as e:
            raise ValidationError(f"Connection error: {e}") from e
        except Exception as e:
            logger.error(f"Error in get_model_methods tool: {e}")
            sanitized_msg = ErrorSanitizer.sanitize_message(str(e))
            raise ValidationError(f"Failed to get model methods: {sanitized_msg}") from e


def register_tools(
    app: FastMCP,
    connection: Optional[OdooConnectionProtocol] = None,
    access_controller: Optional[AccessController] = None,
    config: Optional[OdooConfig] = None,
    connection_manager: Optional[ConnectionManager] = None,
) -> OdooToolHandler:
    """Register all Odoo tools with the FastMCP app.

    Args:
        app: FastMCP application instance
        connection: Odoo connection instance
        access_controller: Access control instance
        config: Odoo configuration instance

    Returns:
        The tool handler instance
    """
    handler = OdooToolHandler(
        app,
        connection=connection,
        access_controller=access_controller,
        config=config,
        connection_manager=connection_manager,
    )
    logger.info("Registered Odoo MCP tools")
    return handler
