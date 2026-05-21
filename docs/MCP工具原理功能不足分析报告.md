# Odoo MCP 工具原理、功能与不足分析报告

分析对象：`/path/to/fast-odoo-mcp`

## 1. 项目定位

这是一个 **Odoo MCP Server**，作用是把 Odoo ERP 的模型、记录、字段、CRUD 操作封装成 MCP 协议能力，让 Claude、Cursor、Trae、Dify 等 AI 客户端可以通过 MCP 工具调用 Odoo 数据。

从 `README-zh.md:9-11` 和 `pyproject.toml:5-37` 看，它是一个 Python 包，包名为 `fast-odoo-mcp`，依赖：

- `mcp>=1.26.0`
- `python-dotenv`
- `pydantic`
- `pydantic-settings`
- `httpx`

核心卖点是：

- 不强制安装 Odoo 端插件；
- Odoo 14-18 使用 XML-RPC；
- Odoo 19+ 自动切换到 JSON/2；
- 暴露通用 Odoo 查询、读取、创建、更新、删除工具；
- 提供智能字段选择，减少 AI 猜字段和大字段序列化问题。

---

## 2. 启动与运行原理

### 2.1 命令入口

包入口定义在：

- `pyproject.toml:56-57`

```toml
[project.scripts]
fast-odoo-mcp = "fast_odoo_mcp.__main__:main"
```

也就是说可以通过：

```bash
python -m fast_odoo_mcp
```

或安装后：

```bash
fast-odoo-mcp
```

启动。

### 2.2 CLI 参数与环境变量

主入口在：

- `fast_odoo_mcp/__main__.py:17-140`

它支持三种 transport：

- `stdio`
- `sse`
- `streamable-http`

对应逻辑在：

- `fast_odoo_mcp/__main__.py:109-114`

```python
if config.transport == "stdio":
    asyncio.run(server.run_stdio())
elif config.transport == "sse":
    asyncio.run(server.run_sse(host=config.host, port=config.port))
elif config.transport == "streamable-http":
    asyncio.run(server.run_http(host=config.host, port=config.port))
```

核心环境变量包括：

- `ODOO_URL`
- `ODOO_API_KEY`
- `ODOO_USER`
- `ODOO_PASSWORD`
- `ODOO_DB`
- `ODOO_YOLO`
- `ODOO_MCP_TRANSPORT`
- `ODOO_MCP_HOST`
- `ODOO_MCP_PORT`
- `ODOO_MCP_DISABLED_TOOLS`

配置加载和校验在：

- `fast_odoo_mcp/config.py:17-49`
- `fast_odoo_mcp/config.py:51-114`
- `fast_odoo_mcp/config.py:170-267`

其中 HTTP transport 要求显式配置 host 和 port，避免误暴露：

- `fast_odoo_mcp/config.py:254-265`

---

## 3. 服务生命周期与架构

主服务类是：

- `fast_odoo_mcp/server.py:35-324`

### 3.1 FastMCP 初始化

在 `fast_odoo_mcp/server.py:63-68` 创建 `FastMCP`：

```python
self.app = FastMCP(
    name="odoo-mcp-server",
    instructions="MCP server for accessing and managing Odoo ERP data through the Model Context Protocol",
    lifespan=self._odoo_lifespan,
)
```

同时注册了：

- `/health` 健康检查：`server.py:70-74`
- model 参数补全：`server.py:76-88`

### 3.2 生命周期流程

关键生命周期在：

- `fast_odoo_mcp/server.py:95-115`

首次启动时：

1. `_ensure_connection()` 建立 Odoo 连接；
2. `_register_resources()` 注册 MCP resources；
3. `_register_tools()` 注册 MCP tools；
4. 关闭时 `_cleanup_connection()` 清理连接。

### 3.3 Odoo API 版本自动探测

在：

- `fast_odoo_mcp/server.py:128-145`
- `fast_odoo_mcp/version_detect.py:33-84`

服务启动时会调用 Odoo `/xmlrpc/2/common` 的 `version()` 判断版本：

- Odoo 19+：使用 JSON/2；
- Odoo 14-18：使用 XML-RPC；
- 探测失败：回退 XML-RPC。

---

## 4. Odoo 连接层原理

项目抽象了统一连接协议：

- `fast_odoo_mcp/connection_protocol.py:10-68`

它定义了工具层需要的统一接口：

- `connect`
- `authenticate`
- `search`
- `read`
- `search_read`
- `search_count`
- `fields_get`
- `create`
- `create_bulk`
- `write`
- `unlink`
- `check_access_rights`

这样上层工具不需要关心底层是 XML-RPC 还是 JSON/2。

### 4.1 XML-RPC 连接

实现文件：

- `fast_odoo_mcp/odoo_connection.py`

主要面向 Odoo 14-18。

连接端点在：

- `fast_odoo_mcp/config.py:136-155`

```python
{
    "db": "/xmlrpc/db",
    "common": "/xmlrpc/2/common",
    "object": "/xmlrpc/2/object",
}
```

认证策略在：

- `fast_odoo_mcp/odoo_connection.py:684-735`

流程：

1. 自动选择数据库；
2. 优先尝试 API key；
3. 先试 `/mcp/auth/validate`；
4. 如果没有 Odoo MCP 模块，则回退到标准 XML-RPC API key 作为 password；
5. 再回退用户名密码。

实际执行 ORM 方法在：

- `fast_odoo_mcp/odoo_connection.py:801-853`

调用的是：

```python
object_proxy.execute_kw(database, uid, password_or_token, model, method, args, kwargs)
```

常见操作映射：

- search：`odoo_connection.py:855-866`
- read：`odoo_connection.py:868-888`
- search_read：`odoo_connection.py:890-910`
- fields_get：`odoo_connection.py:912-942`
- create：`odoo_connection.py:980-999`
- create_bulk：`odoo_connection.py:1004-1024`
- write：`odoo_connection.py:1029-1050`
- unlink：`odoo_connection.py:1055-1075`

### 4.2 JSON/2 连接

实现文件：

- `fast_odoo_mcp/odoo_json2_connection.py`

主要面向 Odoo 19+。

JSON/2 特点在文件头说明：

- `odoo_json2_connection.py:24-36`

认证头在：

- `odoo_json2_connection.py:76-89`

```python
headers = {
    "Authorization": f"Bearer {self.config.api_key}",
    "Content-Type": "application/json; charset=utf-8",
    "User-Agent": "odoo-mcp-pro/1.0 (pnl-e5f1; pantalytics.com)",
}
```

数据库通过：

```python
X-Odoo-Database
```

传入。

核心请求方法在：

- `odoo_json2_connection.py:91-144`

它把请求发到：

```python
/json/2/{model}/{method}
```

认证在：

- `odoo_json2_connection.py:244-287`

它会调用：

```python
res.users/context_get
```

确认 API key 能拿到当前用户 UID。

JSON/2 CRUD 映射：

- search：`odoo_json2_connection.py:309-320`
- read：`odoo_json2_connection.py:322-338`
- search_read：`odoo_json2_connection.py:340-360`
- search_count：`odoo_json2_connection.py:362-372`
- fields_get：`odoo_json2_connection.py:374-403`
- create：`odoo_json2_connection.py:405-422`
- create_bulk：`odoo_json2_connection.py:424-439`
- write：`odoo_json2_connection.py:441-454`
- unlink：`odoo_json2_connection.py:456-468`

---

## 5. MCP 暴露的功能

### 5.1 Resources

资源注册在：

- `fast_odoo_mcp/resources.py:77-155`

当前主要资源模板：

1. 读取单条记录：

```text
odoo://{model}/record/{record_id}
```

对应：

- `resources.py:89-105`

2. 搜索模型记录：

```text
odoo://{model}/search
```

对应：

- `resources.py:108-120`

3. 统计模型记录：

```text
odoo://{model}/count
```

对应：

- `resources.py:125-137`

4. 查看模型字段：

```text
odoo://{model}/fields
```

对应：

- `resources.py:140-155`

Resources 更适合“按 URI 读数据”，但由于 FastMCP 对查询参数支持有限，复杂搜索主要靠 tools。

### 5.2 Tools

工具注册在：

- `fast_odoo_mcp/tools.py:428-791`

主要工具：

#### 只读工具

1. `search_records`

位置：

- `tools.py:439-477`

功能：

- 按 Odoo domain 搜索记录；
- 支持字段列表；
- 支持分页、排序；
- 默认智能字段选择。

2. `get_record`

位置：

- `tools.py:479-527`

功能：

- 按模型和 ID 读取单条记录；
- 支持字段选择；
- 默认返回智能字段；
- 可用 `fields=["__all__"]` 请求全部字段。

3. `list_models`

位置：

- `tools.py:529-545`

功能：

- 列出可访问模型；
- 实际会从 `ir.model` 获取模型列表。

4. `list_resource_templates`

位置：

- `tools.py:547-567`

功能：

- 告诉 AI 可用的 resource URI 模板。

5. `server_info`

位置：

- `tools.py:569-620`

功能：

- 返回 MCP 服务版本；
- Odoo URL；
- API 版本；
- 连接状态；
- 公司信息。

#### 写操作工具

这些默认注册，但可通过 `ODOO_MCP_DISABLED_TOOLS` 禁用。

1. `create_record`

位置：

- `tools.py:624-648`

2. `update_record`

位置：

- `tools.py:650-676`

3. `delete_record`

位置：

- `tools.py:678-702`

4. `create_records`

位置：

- `tools.py:706-734`

5. `update_records`

位置：

- `tools.py:736-765`

6. `delete_records`

位置：

- `tools.py:767-790`

批量上限：

- `tools.py:44`

```python
MAX_BULK_SIZE = 1000
```

---

## 6. 智能字段选择机制

这是当前项目比较实用的设计。

相关代码：

- `fast_odoo_mcp/tools.py:191-260`
- `fast_odoo_mcp/tools.py:262-366`
- `fast_odoo_mcp/tools.py:368-426`

核心逻辑：

1. 总是优先保留：
   - `id`
   - `name`
   - `display_name`
   - `active`

2. 排除技术字段：
   - `_` 开头字段；
   - `message_`；
   - `activity_`；
   - `website_message_`；
   - `write_date`；
   - `create_date`；
   - `access_token` 等。

3. 排除大字段或容易出序列化问题的字段：
   - `binary`
   - `image`
   - `html`
   - `one2many`
   - `many2many`

4. 根据字段类型和业务关键字打分：
   - `state`
   - `status`
   - `amount`
   - `date`
   - `partner`
   - `email`
   - `phone`
   - `company`
   - `currency`
   - `ref`
   - `number`

5. 最多返回 `ODOO_MCP_MAX_SMART_FIELDS` 个字段，默认 15。

这个机制能明显减少 AI 查询 Odoo 时常见的两个问题：

- 猜不存在字段导致 `Invalid field`；
- 一次读出二进制、HTML、消息追踪字段导致响应巨大或 XML-RPC 序列化失败。

---

## 7. 权限与安全机制

### 7.1 依赖 Odoo 原生 ACL

访问控制在：

- `fast_odoo_mcp/access_control.py`

核心是调用 Odoo 的：

```python
check_access_rights
```

位置：

- `access_control.py:113-147`
- `access_control.py:196-223`

每次执行工具前，都会校验：

- read
- write
- create
- unlink

例如：

- 搜索前校验 read：`tools.py:806-807`
- 创建前校验 create：`tools.py:1095-1096`
- 更新前校验 write：`tools.py:1167-1168`
- 删除前校验 unlink：`tools.py:1245-1246`

权限结果缓存 5 分钟：

- `access_control.py:65-66`

```python
CACHE_TTL = 300
```

### 7.2 可禁用写工具

配置字段：

- `config.py:45-46`
- `config.py:247-251`

注册工具时检查：

- `tools.py:431-437`

可以通过：

```bash
ODOO_MCP_DISABLED_TOOLS="create_record,update_record,delete_record,create_records,update_records,delete_records"
```

部署成只读模式。

### 7.3 错误脱敏

错误清洗在：

- `fast_odoo_mcp/error_sanitizer.py`

它会移除：

- Python 文件路径；
- 行号；
- traceback；
- 内部模块名；
- 内存地址；
- 部分 Odoo 内部异常。

主逻辑：

- `error_sanitizer.py:65-113`

XML-RPC 错误也会清洗：

- `odoo_connection.py:841-845`

---

## 8. 性能设计

性能相关文件：

- `fast_odoo_mcp/performance.py`

主要能力：

1. LRU + TTL 缓存：

- `performance.py:83-256`

2. 字段元数据缓存：

- XML-RPC：`odoo_connection.py:924-940`
- JSON/2：`odoo_json2_connection.py:388-402`

3. 连接池：

- `performance.py` 中有 transport 和连接复用逻辑；
- `odoo_connection.py:157-165` 使用 `PerformanceManager` 获取优化连接。

4. 查询分页限制：

- 配置默认值：`config.py:32-34`
- 搜索时限制：`tools.py:862-866`

```python
if limit <= 0:
    limit = self.config.default_limit
elif limit > self.config.max_limit:
    limit = self.config.max_limit
```

---

## 9. 文档与部署方式

文档比较齐全：

- `README.md`
- `README-zh.md`
- `QUICKSTART.md`
- `DOCKER_GUIDE.md`
- `dify-start.md`
- `dify-use.md`
- `dify-llm.md`
- `prompt.md`

Dockerfile：

- `Dockerfile:0-30`

它使用 Python 3.12 slim，多阶段构建，最终非 root 用户 `mcp` 运行。

支持部署方式：

1. 本地 stdio；
2. Cursor / Trae / Claude Desktop command 模式；
3. SSE；
4. streamable-http；
5. Docker；
6. SSH 远程命令；
7. Dify HTTP/SSE 接入。

---

## 10. 测试覆盖

测试目录较完整：

- `tests/test_access_control.py`
- `tests/test_authentication.py`
- `tests/test_basic_resources.py`
- `tests/test_caching.py`
- `tests/test_config.py`
- `tests/test_error_handling.py`
- `tests/test_error_sanitizer.py`
- `tests/test_integration_e2e.py`
- `tests/test_odoo_connection_basic.py`
- `tests/test_odoo_connection_crud.py`
- `tests/test_tools.py`
- `tests/test_transport_integration.py`
- `tests/test_write_operations.py`
- `tests/test_xmlrpc_operations.py`

CI 文件：

- `.github/workflows/ci.yml`

覆盖：

- Ruff；
- ty 类型检查；
- 单元测试；
- Odoo 18 + Postgres 集成测试；
- MCP integration tests。

总体来看，测试覆盖面不错，尤其是连接、权限、缓存、错误清洗、工具行为都有涉及。

---

## 11. 当前工具的优势

### 11.1 通用性强

不绑定某个业务模型，不需要为每个 Odoo 模块单独写工具。只要知道模型名和字段，就能操作任意模型。

### 11.2 兼容 Odoo 多版本

通过版本探测自动选择：

- Odoo 14-18：XML-RPC；
- Odoo 19+：JSON/2。

这对长期维护比较重要。

### 11.3 不强制安装 Odoo 模块

当前版本已经改成主要依赖 Odoo 原生 API。`README-zh.md:11` 明确说明无需安装额外模块。

### 11.4 工具描述中文化

`tools.py` 中工具 docstring 已经中文化，对 Dify、Trae 等中文 Agent 场景友好。

### 11.5 智能字段选择实用

默认不返回全部字段，避免：

- 大字段污染上下文；
- HTML/binary 序列化失败；
- AI 猜字段错误后反复重试。

### 11.6 支持只读部署

通过 `ODOO_MCP_DISABLED_TOOLS` 可以把写工具不注册，适合生产只读查询场景。

---

## 12. 主要不足与风险

### 12.1 写工具默认启用，生产环境风险较高

虽然可用 `ODOO_MCP_DISABLED_TOOLS` 禁用写工具，但默认情况下：

- `create_record`
- `update_record`
- `delete_record`
- 批量 create/update/delete

都会注册。

如果接入的是 Dify、Trae、Claude Desktop 这种 Agent，模型误判或提示词注入都可能导致真实 Odoo 数据变更。

建议生产默认改为只读，写操作必须显式开启。

---

### 12.2 HTTP/SSE MCP 层缺少独立鉴权

Odoo 侧有账号/API key，但 HTTP/SSE 暴露出来的 MCP 服务本身没有看到独立认证机制。

也就是说，如果服务用：

```bash
--transport sse --host 0.0.0.0 --port 8000
```

暴露出去，访问 MCP endpoint 的人理论上可以借用服务端配置好的 Odoo 凭据操作 Odoo。

文档建议用 Nginx/Caddy/SSH，但代码层面没有强制。

建议增加：

- MCP 层 Bearer token；
- IP allowlist；
- 反向代理鉴权；
- 每个 client 独立 Odoo 凭据，而不是全局凭据。

---

### 12.3 绑定 `0.0.0.0` 时关闭 DNS rebinding protection

位置：

- `server.py:233-239`
- `server.py:262-268`

当 host 是 `0.0.0.0` 时：

```python
self.app.settings.transport_security.enable_dns_rebinding_protection = False
```

这解决了部署可访问性问题，但安全性下降。

建议仅在明确配置 `ODOO_MCP_ALLOW_INSECURE_BIND=true` 时允许关闭，或者默认只允许 localhost。

---

### 12.4 没有业务级模型白名单

当前 `AccessController.get_enabled_models()` 返回空列表：

- `access_control.py:158-169`

注释含义是“所有模型可访问，由 Odoo ACL 控制”。

这在技术上可用，但在 AI 工具场景下风险偏高。因为 Odoo 用户有权限不代表 AI 应该能操作所有模型，例如：

- `res.users`
- `ir.config_parameter`
- `ir.module.module`
- 会计凭证
- 工资、人事敏感数据
- 系统配置模型

建议增加：

```bash
ODOO_MCP_ALLOWED_MODELS=res.partner,sale.order,crm.lead
ODOO_MCP_BLOCKED_MODELS=res.users,ir.config_parameter,...
```

### 12.5 只做模型级 ACL，不做记录规则预判

`check_access_rights` 只检查模型级权限，不等于记录级规则完全通过。

实际 Odoo record rule 仍会在 search/read/write/unlink 时生效，但 MCP 层无法提前解释“为什么某条记录不可见/不可写”。

这会导致 Agent 体验上出现：

- list_models 显示模型可操作；
- 实际记录操作失败；
- 错误信息可能被清洗得比较泛化。

### 12.6 批量操作上限 1000 仍然偏大

位置：

- `tools.py:44`

```python
MAX_BULK_SIZE = 1000
```

对于 Odoo 来说，批量删除/更新 1000 条生产数据风险很高。尤其 AI Agent 可能误把搜索结果全部传入删除。

建议：

- 默认批量写上限降低到 50 或 100；
- 删除操作单独更低；
- 增加 dry-run / confirmation token 机制；
- 批量写必须显式开启。

### 12.7 domain 字符串解析比较脆弱

位置：

- `tools.py:813-846`

当 domain 是字符串时，会先 `json.loads`，失败后简单把单引号换双引号、`True/False` 换成小写。

这个策略在简单 domain 可用，但复杂情况下可能误处理字符串值中的引号。

建议：

- 明确要求 domain 必须是 JSON array；
- 或支持 Python literal 用 `ast.literal_eval`；
- 返回更明确的 domain 示例和错误提示。

### 12.8 `list_models` 可能暴露过多模型信息

位置：

- `tools.py:995-1020`

当 `get_enabled_models()` 为空时，会从 `ir.model` 读取所有非 transient 模型。

这对 AI 很有帮助，但也可能暴露系统结构，包括一些不希望 Agent 看到的模型。

建议和模型白名单/黑名单结合。

### 12.9 JSON/2 权限检查失败时有“放行”逻辑

位置：

- `odoo_json2_connection.py:470-500`

如果 JSON/2 的 `check_access_rights` 返回 Not found，代码会：

```python
return True
```

设计意图是让实际操作自己失败，但这意味着 MCP 层权限预检可能过宽。

XML-RPC 也有类似逻辑：

- `odoo_connection.py:944-966`
- `odoo_connection.py:1080-1102`

除模型不存在外，其他异常会假设允许。

建议安全模式下改为 fail closed，也就是权限检查异常默认拒绝。

### 12.10 配置中 YOLO 概念容易误导

`ODOO_YOLO` 支持：

- `off`
- `read`
- `true`

但从当前 `config.py:146-155` 看，无论 yolo 与否都使用标准 Odoo endpoint。文档中 “YOLO 模式” 被描述成“无敌”“允许 AI 无视部分限制”，这在生产语义上容易让用户误配。

建议：

- 文档弱化 YOLO；
- 默认不要推荐 `ODOO_YOLO=true`；
- 把生产配置和开发配置分开。

---

## 13. 改进建议优先级

### P0：生产安全

1. 默认禁用所有写工具；
2. 增加 MCP HTTP/SSE 层鉴权；
3. 加入模型 allowlist / blocklist；
4. 权限检查异常默认拒绝，而不是默认允许；
5. 禁止默认公网暴露。

### P1：防误操作

1. 批量写操作上限降低；
2. 删除操作增加 dry-run；
3. 写操作返回前要求确认或二阶段提交；
4. 对高危模型默认禁止写入：
   - `res.users`
   - `ir.config_parameter`
   - `ir.module.module`
   - `account.move`
   - `hr.employee`
   - 薪资相关模型

### P2：AI 使用体验

1. 增强 `list_models`，支持按关键词搜索模型；
2. 增加 `describe_model` 工具，一次返回模型说明、常用字段、示例 domain；
3. 增加 domain 校验工具；
4. 对 Invalid field 错误返回建议字段；
5. 支持按中文业务名映射模型，例如“客户”→`res.partner`，“销售订单”→`sale.order`。

### P3：可观测性

1. 记录每次 MCP 工具调用的：
   - tool name；
   - model；
   - operation；
   - record count；
   - user；
   - duration；
   - success/failure；
2. 写操作单独审计；
3. 增加 Prometheus metrics 或 structured JSON log；
4. `/health` 增加 Odoo latency、API version、database、last error。

---

## 14. 总体结论

当前目录下的 MCP 工具本质上是一个 **通用 Odoo ORM 网关**：上层用 MCP 暴露 tools/resources，下层通过 XML-RPC 或 JSON/2 调用 Odoo 原生 API，中间用智能字段选择、权限检查、错误清洗和缓存提升 AI 调用的可用性。

它的功能完整度已经比较高，适合：

- 本地开发查询 Odoo 数据；
- AI 辅助排查业务数据；
- Dify/Claude/Cursor 接入 Odoo；
- 快速构建 Odoo 查询型 Agent；
- 在受控环境下做 CRUD 自动化。

但如果用于生产或团队共享，最大问题是 **安全边界不够强**：

- 写工具默认启用；
- HTTP/SSE 层没有独立鉴权；
- 没有模型白名单；
- 批量写/删能力较强；
- 权限检查异常时部分逻辑偏向放行。

我的建议是：

**开发环境可以直接使用；生产环境必须先改成“默认只读 + MCP 层鉴权 + 模型白名单 + 写操作二次确认”。**