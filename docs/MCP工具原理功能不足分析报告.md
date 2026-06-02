# Odoo MCP 工具原理、功能与不足分析报告

分析对象：`fast-odoo-mcp`

本文档用于说明当前项目的真实定位、技术实现、可用能力、安全边界和不足。结论先行：当前项目是一个 **通用 Odoo ORM/MCP 网关**，适合内部受信场景、开发辅助和受控自动化；不建议把它作为直接开放给外部不受信用户的生产入口。

## 1. 项目定位

`fast-odoo-mcp` 是一个 Python MCP Server。它把 Odoo 模型、字段、记录和 ORM 方法包装成 MCP tools/resources，让 Claude、Cursor、Trae、Dify 等外部 AI 客户端能够通过自然语言间接访问 Odoo。

项目核心特点：

- 不要求在 Odoo 端安装额外模块；
- Odoo 14-18 使用 XML-RPC；
- Odoo 19+ 自动切换到 JSON/2；
- 通过 MCP 暴露查询、读取、字段发现、创建、更新、删除、业务方法调用等能力；
- 使用智能字段选择减少大字段、HTML、二进制字段和 XML-RPC 序列化问题；
- 默认只读，支持 HTTP token、模型 allow/block list、写模型白名单等生产保护开关。

需要特别注意：它本质上仍然使用服务端配置的 Odoo 凭据访问 Odoo。MCP 客户端一旦连上该服务，就在该服务配置的权限范围内调用 Odoo。因此它不是“多租户外部授权系统”，也不是字段级/方法级/记录域级的独立权限网关。

## 2. 启动与运行链路

包入口定义在 `pyproject.toml`：

```toml
[project.scripts]
fast-odoo-mcp = "fast_odoo_mcp.__main__:main"
```

主入口 `fast_odoo_mcp/__main__.py` 负责：

- 解析 `--transport`、`--host`、`--port`；
- 从环境变量或 `.env` 加载配置；
- 创建 `OdooMCPServer`；
- 根据 transport 运行 `stdio`、`sse` 或 `streamable-http`。

当前支持的 transport：

- `stdio`：默认模式，适合 Claude Desktop、Cursor、Trae 等本地 MCP 客户端；
- `streamable-http`：标准 HTTP MCP 传输，适合远程服务化部署；
- `sse`：仍保留兼容，但 MCP 协议中已逐步弃用，推荐新部署使用 `streamable-http`。

HTTP transport 有额外安全校验：

- 必须显式设置 `ODOO_MCP_HOST` 和 `ODOO_MCP_PORT`；
- `ODOO_MCP_STRICT_SECURITY=true` 且绑定非本地主机时必须设置 `ODOO_MCP_HTTP_TOKEN`；
- 绑定 `0.0.0.0` 时也必须提供 token；
- 可配置 `ODOO_MCP_ALLOWED_HOSTS` 和 `ODOO_MCP_ALLOWED_ORIGINS`。

## 3. 服务架构

主服务类在 `fast_odoo_mcp/server.py`。

核心组件：

- `OdooMCPServer`：创建 FastMCP 实例，注册 tools/resources，管理生命周期；
- `ConnectionManager`：统一维护 Odoo 连接、自动探测 API 版本、重连、并发限制；
- `AccessController`：基于 Odoo 原生 `check_access_rights` 和本地策略做模型级权限检查；
- `OdooConnection`：Odoo 14-18 XML-RPC 连接实现；
- `OdooJSON2Connection`：Odoo 19+ JSON/2 连接实现；
- `OdooToolHandler`：注册和实现 MCP tools；
- `OdooResourceHandler`：注册和实现 MCP resources；
- `PerformanceManager`：字段缓存、连接复用、性能统计。

服务还提供健康检查端点：

- `GET /health`
- `GET /ready`
- `GET /metrics`

这些端点用于部署探活和基础运行状态观测。

## 4. Odoo 版本兼容

版本探测逻辑在 `fast_odoo_mcp/version_detect.py`。服务启动时会调用 Odoo 的 `/xmlrpc/2/common` `version()` 方法读取服务器版本。

兼容策略：

- Odoo 14-18：使用 XML-RPC `/xmlrpc/db`、`/xmlrpc/2/common`、`/xmlrpc/2/object`；
- Odoo 19+：使用 JSON/2 `/json/2/{model}/{method}`；
- 探测失败：回退 XML-RPC；
- Odoo 20：需要重点关注 Odoo 官方对 XML-RPC/JSON-RPC 的移除计划，生产上应优先验证 JSON/2 路径。

连接协议通过 `fast_odoo_mcp/connection_protocol.py` 抽象，工具层只依赖统一接口：

- `search`
- `read`
- `search_read`
- `search_count`
- `fields_get`
- `create`
- `create_bulk`
- `write`
- `unlink`
- `execute_kw`
- `check_access_rights`

这让上层 MCP tools 不需要关心底层是 XML-RPC 还是 JSON/2。

## 5. MCP 暴露的能力

### 5.1 Resources

Resources 主要用于按 URI 读取 Odoo 数据：

- `odoo://{model}/record/{record_id}`：读取单条记录；
- `odoo://{model}/search`：按默认参数搜索模型记录；
- `odoo://{model}/count`：统计模型记录数；
- `odoo://{model}/fields`：查看模型字段定义。

由于 MCP resource 对复杂查询参数支持有限，复杂搜索、分页、排序和字段选择主要通过 tools 完成。

### 5.2 只读 Tools

当前主要只读工具：

- `search_records`：按 domain 搜索记录，支持字段、limit、offset、order；
- `get_record`：按 ID 读取单条记录，支持智能字段或指定字段；
- `list_models`：列出可访问模型及操作权限；
- `get_model_fields`：查看模型字段定义，可按字段名或显示名过滤；
- `validate_domain`：校验 domain 并返回匹配数量；
- `list_resource_templates`：列出可用 resource URI 模板；
- `get_public_config`：返回可公开给 MCP 客户端的运行配置；
- `server_info`：返回服务版本、连接状态、Odoo API 版本和公司信息；
- `simulate_onchange`：模拟 Odoo onchange；
- `get_model_methods`：返回可被 `execute_method` 发现和调用的方法范围。

### 5.3 写操作 Tools

写操作默认受 `ODOO_MCP_READONLY=true` 限制。关闭只读模式后，可能注册：

- `create_record`
- `update_record`
- `delete_record`
- `create_records`
- `update_records`
- `delete_records`

批量操作上限由 `ODOO_MCP_MAX_BULK_SIZE` 控制，当前默认值为 100。

### 5.4 业务方法调用

`execute_method` 是高能力工具，可调用 Odoo 模型方法，例如：

- `sale.order.action_confirm`
- `account.move.action_post`
- `stock.picking.button_validate`
- `res.partner.toggle_active`
- `read_group`
- `name_search`

当前安全策略是：

- 方法必须在安全名单内，或以 `action_`、`button_`、`onchange_`、`_onchange_` 等前缀开头；
- `__dunder__` 方法禁止调用；
- 只读模式下禁止调用会改变数据的方法；
- 状态变更类方法要求模型具备写权限，并受 `ODOO_MCP_WRITE_ALLOWLIST` 约束。

但对外部不受信用户而言，这仍然过宽。业务按钮方法内部可能做复杂副作用，单靠前缀安全名单不足以表达每个外部用户的精细授权。

## 6. 智能字段选择

智能字段选择是当前项目中很实用的 AI 适配能力。默认不盲目返回所有字段，而是根据字段元数据和业务关键字挑选一组较安全、较常用的字段。

默认优先保留：

- `id`
- `name`
- `display_name`
- `active`
- `company_id`

默认排除：

- `_` 开头字段；
- `message_`、`activity_`、`website_message_`；
- `create_uid`、`write_uid`、`create_date`、`write_date`；
- `access_token`、`access_url` 等敏感或技术字段；
- `binary`、`image`、`html`；
- `one2many`、`many2many`；
- 非存储的昂贵计算字段。

字段会按类型和业务关键词打分，例如 `state`、`status`、`amount`、`date`、`partner`、`email`、`phone`、`company`、`currency`、`ref`、`number` 等。最大返回数量由 `ODOO_MCP_MAX_SMART_FIELDS` 控制，默认 15。

## 7. 当前安全机制

当前代码已经具备一些生产保护能力：

- `ODOO_MCP_READONLY=true`：默认只读，写工具不会注册；
- `ODOO_MCP_DISABLED_TOOLS`：按工具名禁用能力；
- `ODOO_MCP_MODEL_ALLOWLIST`：模型访问白名单；
- `ODOO_MCP_MODEL_BLOCKLIST`：模型访问黑名单；
- `ODOO_MCP_WRITE_ALLOWLIST`：写操作模型白名单；
- `ODOO_MCP_HTTP_TOKEN`：HTTP/SSE transport 的 Bearer token；
- `ODOO_MCP_STRICT_SECURITY=true`：非本地 HTTP 绑定要求 token；
- `ODOO_MCP_MAX_LIMIT`：单次查询最大返回记录；
- `ODOO_MCP_MAX_BULK_SIZE`：批量写操作最大记录数；
- 错误脱敏：清理 traceback、内部路径、部分 Odoo 内部错误；
- Odoo 原生 `check_access_rights`：按服务端配置用户检查模型级 ACL；
- Odoo record rules：实际 search/read/write/unlink 时仍由 Odoo 执行记录规则。

这些能力适合把服务部署给内部受信 AI 客户端，或由管理员自己使用。

## 8. 主要不足与风险

### 8.1 不是多外部用户授权系统

当前服务只加载一组 Odoo 凭据。HTTP token 只保护 MCP 服务入口，不能表达“这个外部用户只能访问哪些模型、字段、记录、方法”。

如果多个外部用户共用同一个 MCP 服务，他们本质上共享同一组 Odoo 权限边界。

### 8.2 没有字段级权限

智能字段选择可以减少默认返回字段，但不是安全策略。用户仍可能显式请求字段，当前 MCP 层没有“按 API Key 配置字段白名单”的机制。

### 8.3 没有记录域级授权

Odoo record rule 会生效，但那是服务端配置用户的规则，不是每个外部 API Key 的独立记录域。当前无法做到：

- A 客户只能看自己的 partner；
- B 客户只能看某个项目；
- C 客户只能看某个公司下的订单；
- 同一模型按不同外部用户拼接不同强制 domain。

### 8.4 `execute_method` 对不受信用户风险高

`execute_method` 可以调用业务按钮和动作方法。即使只允许安全前缀，Odoo 业务方法内部仍可能：

- 确认订单；
- 过账凭证；
- 验证库存；
- 发送消息；
- 触发自动化；
- 修改关联记录。

对外部用户应该改为“每个方法显式白名单”，而不是使用通用前缀。

### 8.5 模型级 ACL 不等于业务最小授权

`check_access_rights` 只说明当前 Odoo 用户是否有模型级 read/write/create/unlink 权限。AI 应该能做的事通常比这个更窄，例如只读某几个字段、只写某个状态、只调用某个业务按钮。

### 8.6 HTTP token 不是业务权限

`ODOO_MCP_HTTP_TOKEN` 可以避免未授权访问 MCP endpoint，但它不是租户权限模型。token 泄露后，拿到 token 的人可在 MCP 服务配置的 Odoo 权限范围内调用工具。

### 8.7 `list_models` 可能暴露系统结构

当没有模型 allowlist 时，`list_models` 可能从 `ir.model` 返回大量模型信息。对内部调试有用，但对外部用户可能暴露不必要的系统结构。

## 9. 适用场景

适合：

- 开发者本地查询和排查 Odoo 数据；
- 内部受信团队使用 AI 辅助运营、实施、客服；
- 只读场景的数据问答；
- 受控环境下的业务自动化；
- Dify/Claude/Cursor 等内部工具接入 Odoo。

不适合直接用于：

- 面向外部不受信客户开放；
- 多客户共用同一个 MCP 服务；
- API Key 维度的字段级、方法级、记录级权限控制；
- 需要严格审计和租户隔离的生产开放平台。

## 10. 推荐对外方案

如果要给外部不受信用户使用，推荐新增 Odoo 模块作为权限权威源头，而不是把当前通用 MCP 服务直接暴露出去。

推荐架构：

```text
外部 AI / CLI / MCP 客户端
        |
        | Bearer API Key
        v
CLI 或 MCP 适配层
        |
        | 只调用受控 REST API
        v
Odoo 模块 mcp_api_gateway
        |
        | API Key 权限、字段白名单、方法白名单、强制 domain、审计
        v
Odoo ORM
```

关键原则：

- 外部用户不提供 Odoo 账号密码；
- 每个外部用户只拿我们发放的 API Key；
- API Key 权限在 Odoo 后台配置；
- 模型必须显式授权；
- 字段必须显式授权；
- 方法必须显式授权；
- 搜索 domain 必须和后台强制 domain 合并；
- 调用日志必须落库；
- MCP 只做协议包装，不做最终权限裁决。

详细设计见 `docs/external-access-security-design.md`。

## 11. 总体结论

当前 `fast-odoo-mcp` 已经是一个功能完整、工程化程度较高的 Odoo MCP 网关：连接、版本兼容、工具注册、智能字段、错误脱敏、只读模式、HTTP token 和基础生产保护都已经具备。

但它的安全模型仍然是“服务端配置一个 Odoo 用户，然后 MCP 客户端共享这个用户的能力”。这对内部使用可以接受；对外部不受信用户不够。

最终建议：

- 内部受信场景：继续使用当前 MCP 服务，默认只读，配模型白名单和 HTTP token；
- 外部不受信场景：不要直接开放当前 MCP 服务；
- 对外开放能力：新增 `mcp_api_gateway` Odoo 模块做授权源头，再用 CLI/MCP 做轻量适配。
