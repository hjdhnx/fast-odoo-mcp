# 外部用户访问 Odoo 的安全授权方案

本文档回答一个核心问题：能不能把 Odoo 能力通过 MCP 提供给外部 AI 或外部用户，同时严格控制权限？

结论：**MCP 这条路可以走，但 MCP 不应该是最终权限边界。** 对不受信外部用户，权限权威应放在 Odoo 内部模块中，由 Odoo 后台配置 API Key、模型、字段、方法和记录域；MCP 或 CLI 只做外部协议适配。

## 1. 背景与风险

当前 `fast-odoo-mcp` 是通用 Odoo MCP 网关。它用服务端配置的 Odoo 凭据，通过 XML-RPC 或 JSON/2 调用 Odoo ORM。

这对内部受信用户很方便，但直接开放给外部不受信用户存在风险：

- 外部用户不应该知道 Odoo 账号密码；
- 多个外部用户不应该共享同一套 Odoo 用户权限；
- Odoo 用户有权限，不代表 AI 或外部客户应该拥有同样权限；
- MCP 暴露的是工具能力，不天然表达字段级、方法级、记录级授权；
- `execute_method` 可触发业务按钮和动作方法，副作用不可只靠模型级 ACL 控制；
- HTTP token 只能保护入口，不能表达每个客户的业务权限。

因此，不建议把现有通用 MCP 服务直接公网交给外部用户使用。

## 2. 推荐架构

推荐新增一个 Odoo 18 模块：`mcp_api_gateway`。

```text
外部 AI / 外部系统 / CLI / MCP Client
        |
        | Authorization: Bearer <api_key>
        v
CLI 或 MCP 适配层
        |
        | HTTPS JSON API
        v
Odoo 模块 mcp_api_gateway
        |
        | API Key 校验、权限裁决、字段过滤、domain 合并、方法白名单、审计
        v
Odoo ORM
```

职责划分：

- Odoo 模块：唯一权限权威，负责认证、授权、审计和实际 ORM 调用；
- CLI：给外部系统或开发者提供命令行体验；
- MCP：给 AI 客户端提供 tools/resources，但所有操作都转发到 Odoo 模块 API；
- 当前 `fast-odoo-mcp`：继续作为内部通用网关，不直接作为外部不受信用户入口。

## 3. Odoo 模块数据模型

### 3.1 `mcp.api.key`

表示一个外部用户、外部系统或外部 AI 应用的访问凭证。

建议字段：

- `name`：名称；
- `key_hash`：API Key 哈希值，只保存 hash，不保存明文；
- `active`：是否启用；
- `expires_at`：过期时间；
- `company_ids`：允许访问的公司范围；
- `rate_limit_per_minute`：每分钟调用上限；
- `max_daily_calls`：每日调用上限；
- `last_used_at`：最后使用时间；
- `note`：备注；
- `permission_ids`：权限明细；
- `call_log_ids`：调用日志。

安全要求：

- API Key 生成后只显示一次；
- 数据库只保存 hash；
- 支持禁用和过期；
- 支持轮换；
- 权限变更应立即生效或使用很短缓存。

### 3.2 `mcp.api.permission`

表示某个 API Key 对某个 Odoo 模型的授权。

建议字段：

- `api_key_id`：所属 API Key；
- `model_name`：Odoo 模型技术名，例如 `res.partner`；
- `perm_read`：允许读取；
- `perm_create`：允许创建；
- `perm_write`：允许更新；
- `perm_unlink`：允许删除；
- `read_field_names`：读取字段白名单；
- `write_field_names`：写入字段白名单；
- `forced_domain`：强制 domain，JSON 格式；
- `method_names`：允许调用的方法白名单；
- `max_limit`：单次搜索最大返回数量；
- `active`：是否启用。

默认策略：

- 没有权限记录则拒绝；
- 模型未显式授权则拒绝；
- 字段白名单为空时拒绝返回业务字段，只允许 `id` 或直接拒绝，具体由产品策略决定；
- `unlink` 默认关闭；
- 方法调用必须逐个配置，不使用 `action_*`、`button_*` 这种泛前缀授权。

### 3.3 `mcp.api.call.log`

记录所有外部调用，便于审计和追责。

建议字段：

- `api_key_id`；
- `request_id`；
- `remote_addr`；
- `user_agent`；
- `operation`：`search/read/create/write/unlink/call_method`；
- `model_name`；
- `method_name`；
- `record_count`；
- `duration_ms`；
- `success`；
- `error_message`；
- `request_summary`；
- `response_summary`；
- `create_date`。

日志要求：

- 成功和失败都记录；
- 不记录完整敏感 payload；
- 错误信息脱敏；
- 写操作、删除操作和方法调用应重点标记。

## 4. 外部 API 设计

所有 API 使用 HTTPS 和 Bearer token：

```http
Authorization: Bearer <api_key>
Content-Type: application/json
```

建议端点：

- `POST /mcp_api/v1/search`
- `POST /mcp_api/v1/read`
- `POST /mcp_api/v1/create`
- `POST /mcp_api/v1/write`
- `POST /mcp_api/v1/unlink`
- `POST /mcp_api/v1/call_method`
- `GET /mcp_api/v1/models`
- `GET /mcp_api/v1/models/{model}/fields`

### 4.1 Search

请求：

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true]],
  "fields": ["name", "email", "phone"],
  "limit": 20,
  "offset": 0,
  "order": "name asc"
}
```

执行规则：

- 校验 API Key；
- 查找 `model` 对应权限；
- 要求 `perm_read=true`；
- 请求字段必须是 `read_field_names` 子集；
- 请求 limit 不能超过权限记录中的 `max_limit`；
- 外部 domain 与 `forced_domain` 做 AND 合并；
- 使用合并后的 domain 执行 `search_read`；
- 响应只返回允许字段。

### 4.2 Read

请求：

```json
{
  "model": "res.partner",
  "ids": [1, 2, 3],
  "fields": ["name", "email"]
}
```

执行规则：

- 要求 `perm_read=true`；
- 字段必须过读取白名单；
- 记录必须满足强制 domain；
- 不满足 domain 的记录不可返回。

### 4.3 Create

请求：

```json
{
  "model": "crm.lead",
  "values": {
    "name": "New Lead",
    "email_from": "customer@example.com"
  }
}
```

执行规则：

- 要求 `perm_create=true`；
- 写入字段必须是 `write_field_names` 子集；
- 可以注入固定默认值，例如公司、来源、负责人；
- 创建后返回字段仍受 `read_field_names` 控制。

### 4.4 Write

请求：

```json
{
  "model": "crm.lead",
  "ids": [10],
  "values": {
    "phone": "13800000000"
  }
}
```

执行规则：

- 要求 `perm_write=true`；
- 字段必须过写入白名单；
- 待写记录必须满足强制 domain；
- 写入后记录仍必须满足业务约束。

### 4.5 Unlink

请求：

```json
{
  "model": "crm.lead",
  "ids": [10]
}
```

执行规则：

- 默认拒绝；
- 只有 `perm_unlink=true` 时允许；
- 记录必须满足强制 domain；
- 建议首版不开放，或只对低风险临时模型开放。

### 4.6 Call Method

请求：

```json
{
  "model": "sale.order",
  "method": "action_confirm",
  "ids": [42],
  "args": [],
  "kwargs": {}
}
```

执行规则：

- 方法名必须出现在 `method_names`；
- 不支持泛前缀授权；
- 如果方法作用于记录，记录必须满足强制 domain；
- 方法返回值需要做 JSON 安全序列化；
- 高风险方法建议拆成专用 API，而不是透传任意方法。

## 5. 权限裁决流程

每次请求统一经过以下流程：

1. 读取 Bearer token；
2. 计算 hash，查找 active 且未过期的 `mcp.api.key`；
3. 检查限流；
4. 根据 `model` 查找 active 的 `mcp.api.permission`；
5. 校验操作权限；
6. 校验字段白名单；
7. 校验方法白名单；
8. 合并外部 domain 和后台强制 domain；
9. 对记录 ID 场景先检查记录是否落在强制 domain 内；
10. 执行 ORM；
11. 过滤响应字段；
12. 写入调用日志。

必须遵循 fail closed 原则：任何解析失败、权限缺失、字段不明、domain 格式错误、方法未配置，都默认拒绝。

## 6. sudo 使用原则

不建议无边界使用 `sudo()`。

推荐策略：

- 首选使用一个低权限服务用户执行；
- 模块自身策略先裁决模型、字段、domain、方法；
- 只有在读取权限配置、写调用日志等模块内部管理动作时使用 `sudo()`；
- 对业务模型执行 CRUD 前必须完成模块权限过滤；
- 不允许外部请求直接影响 `sudo()` 的模型名、字段或方法范围。

## 7. MCP 与 CLI 如何接入

### 7.1 CLI

CLI 只调用 `mcp_api_gateway` 的 REST API：

```bash
odoo-gateway search res.partner --fields name,email --limit 20
odoo-gateway read res.partner 1 --fields name,email
odoo-gateway create crm.lead --json values.json
```

CLI 不保存 Odoo 用户名密码，只保存外部 API Key。

### 7.2 MCP

MCP Server 也只调用 REST API，不直接连 Odoo XML-RPC/JSON/2。

MCP tools 可以设计为：

- `list_allowed_models`
- `get_allowed_fields`
- `search_records`
- `get_records`
- `create_record`
- `update_record`
- `call_allowed_method`

这些工具的 schema 与当前 `fast-odoo-mcp` 类似，但权限由 Odoo 模块裁决。MCP 层不缓存长期权限，不做最终放行决定。

## 8. 与当前 fast-odoo-mcp 的关系

当前项目保留两种定位：

1. 内部通用网关：
   - 继续用 `fast-odoo-mcp`；
   - 默认只读；
   - 配 `ODOO_MCP_HTTP_TOKEN`；
   - 配模型 allow/block list；
   - 仅给受信内部用户。

2. 外部安全开放：
   - 新增 `mcp_api_gateway` Odoo 模块；
   - 新增轻量 CLI/MCP 适配层；
   - 外部用户只拿模块 API Key；
   - 权限在 Odoo 后台配置。

不建议把当前通用 RPC 型 MCP 服务直接改造成所有外部权限的最终裁决层。权限离数据越近，越容易审计、回收、调试和解释。

## 9. 首版边界

首版建议只实现：

- Odoo 18；
- API Key 管理；
- 模型级权限；
- 字段读写白名单；
- 强制 domain；
- search/read/create/write；
- 调用日志；
- `unlink` 默认关闭；
- `call_method` 只支持显式配置的方法。

后续再考虑：

- Odoo 14-17 兼容；
- Odoo 19/20 JSON/2 兼容；
- 更复杂的限流；
- webhook；
- OAuth 或短期 token；
- 审批流；
- 二阶段写操作确认；
- 更细粒度的字段脱敏规则。

## 10. 验收标准

文档和方案层面：

- 能清楚说明为什么现有 MCP 不应直接开放给外部不受信用户；
- 能清楚说明 MCP 仍然可以作为外部适配层；
- 能清楚说明权限权威为什么应放在 Odoo 模块中；
- API、模型、字段、方法、domain、审计设计足够指导后续实现。

模块实现层面：

- API Key hash 校验、禁用、过期都能拒绝；
- 未授权模型拒绝；
- 未授权字段拒绝或不返回；
- 未授权方法拒绝；
- 强制 domain 无法被外部 domain 绕过；
- 写操作只允许白名单字段；
- 每次调用都有日志；
- 不同 API Key 配不同权限时，返回数据和可执行能力不同。
