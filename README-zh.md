中文 | **[English](README.md)**

# Odoo MCP 服务器 (MCP Server for Odoo)

[![CI](https://github.com/hjdhnx/fast-odoo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hjdhnx/fast-odoo-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hjdhnx/fast-odoo-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/hjdhnx/fast-odoo-mcp)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with ty](https://img.shields.io/badge/checked%20with-ty-blue?labelColor=orange)](https://github.com/astral-sh/ty)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

这是一个 MCP (Model Context Protocol) 服务器，它使 Claude 等 AI 助手能够与 Odoo ERP 系统进行交互。通过自然语言即可访问业务数据、搜索记录、创建新条目、更新现有数据以及管理您的 Odoo 实例。

**适用于任何 Odoo 实例！** 此修改版本直接使用 Odoo 原生的 XML-RPC 和 JSON/2 接口，这意味着 **不需要在 Odoo 中安装任何模块**。它开箱即用，适用于任何标准 Odoo 安装 (v14.0 到 v19.0+)。

## 特性

- 🔍 **搜索和检索** 任何 Odoo 记录（客户、产品、发票等）
- ✨ **创建新记录**，支持字段验证和权限检查
- ✏️ **更新现有数据**，支持智能字段处理
- 🗑️ **删除记录**，遵循模型级别的权限设置
- 🔢 **统计记录**，根据特定条件计数
- 📋 **检查模型字段**，了解数据结构
- 🔐 **安全访问**，支持 API Key 或 用户名/密码 身份验证
- 🎯 **智能分页**，针对大型数据集进行优化
- 🧠 **智能字段选择** — 自动为每个模型挑选最相关的字段
- 💬 **LLM 优化输出**，采用层次化文本格式
- 🌍 **多语言支持** — 以您偏好的语言获取响应
- 🚀 **YOLO 模式**，无需安装模块即可快速访问任何 Odoo 实例

## 安装

### 前置条件

- Python 3.10 或更高版本
- 可访问的 Odoo 实例：
  - 任何启用了 XML-RPC 或 JSON/2 的 Odoo 版本（14.0 到 19.0+）
  - **不需要安装任何 Odoo 模块**
  - 完全通过原生 Odoo API 运行

### 首先安装 UV

MCP 服务器运行在您的**本地计算机**（安装了 Claude Desktop 的地方），而不是您的 Odoo 服务器上。您需要在本地机器上安装 UV：

<details>
<summary>macOS/Linux</summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
</details>

<details>
<summary>Windows</summary>

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
</details>

安装完成后，重启终端以确保 UV 已加入您的 PATH 环境变量。

### 通过 MCP 设置安装 (推荐)

将此配置添加到您的 MCP 设置中：

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

<details>
<summary>Claude Desktop</summary>

添加到 `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>Claude Code</summary>

添加到项目根目录的 `.mcp.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```

或使用 CLI 命令：

```bash
claude mcp add odoo \
  --env ODOO_URL=https://your-odoo-instance.com \
  --env ODOO_API_KEY=your-api-key-here \
  --env ODOO_DB=your-database-name \
  -- uvx fast-odoo-mcp
```
</details>

<details>
<summary>Cursor</summary>

添加到 `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>VS Code (使用 GitHub Copilot)</summary>

添加到工作区的 `.vscode/mcp.json`:

```json
{
  "servers": {
    "odoo": {
      "type": "stdio",
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```

> **注意:** VS Code 使用 `"servers"` 作为根键名，而不是 `"mcpServers"`。
</details>

<details>
<summary>Windsurf</summary>

添加到 `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uvx",
      "args": ["fast-odoo-mcp"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

<details>
<summary>Zed</summary>

添加到 `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "odoo": {
      "command": {
        "path": "uvx",
        "args": ["fast-odoo-mcp"],
        "env": {
          "ODOO_URL": "https://your-odoo-instance.com",
          "ODOO_API_KEY": "your-api-key-here",
          "ODOO_DB": "your-database-name"
        }
      }
    }
  }
}
```
</details>

### 其他安装方法

<details>
<summary>使用 Docker</summary>

使用 Docker 运行 — 无需安装 Python：

```json
{
  "mcpServers": {
    "odoo": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "ODOO_URL=http://host.docker.internal:8069",
        "-e", "ODOO_API_KEY=your-api-key-here",
        "hjdhnx/fast-odoo-mcp"
      ]
    }
  }
}
```

> **注意:** 使用 `host.docker.internal` 而不是 `localhost` 来连接宿主机上运行的 Odoo。

对于 HTTP 传输：

```bash
docker run --rm -p 8000:8000 \
  -e ODOO_URL=http://host.docker.internal:8069 \
  -e ODOO_API_KEY=your-api-key-here \
  hjdhnx/fast-odoo-mcp --transport streamable-http --host 0.0.0.0
```

镜像也可在 GHCR 上获取: `ghcr.io/hjdhnx/fast-odoo-mcp`
</details>

<details>
<summary>使用 pip</summary>

```bash
# 全局安装
pip install fast-odoo-mcp

# 或使用 pipx 进行隔离安装
pipx install fast-odoo-mcp
```

然后在您的 MCP 配置中使用 `fast-odoo-mcp` 作为命令。
</details>

<details>
<summary>从源码安装</summary>

```bash
git clone https://github.com/hjdhnx/fast-odoo-mcp.git
cd fast-odoo-mcp
pip install -e .
```

然后在您的 MCP 配置中使用该包的完整路径。
</details>

## 配置

### 环境变量

服务器需要以下环境变量：

| 变量 | 是否必填 | 描述 | 示例 |
|----------|----------|-------------|---------|
| `ODOO_URL` | 是 | 您的 Odoo 实例 URL | `https://mycompany.odoo.com` |
| `ODOO_API_KEY` | 是* | 用于身份验证的 API Key | `0ef5b399e9ee9c11b053dfb6eeba8de473c29fcd` |
| `ODOO_USER` | 是* | 用户名 (如果不使用 API Key) | `admin` |
| `ODOO_PASSWORD` | 是* | 密码 (如果不使用 API Key) | `admin` |
| `ODOO_DB` | 否 | 数据库名称 (未设置则自动检测) | `mycompany` |
| `ODOO_LOCALE` | 否 | Odoo 响应的语言/区域设置 | `zh_CN`, `en_US` |
| `ODOO_YOLO` | 否 | YOLO 模式 - 绕过 MCP 安全限制 (⚠️ 仅限开发) | `off`, `read`, `true` |

*必须提供 `ODOO_API_KEY`，或者同时提供 `ODOO_USER` 和 `ODOO_PASSWORD`。

**注意:**
- 如果您的服务器限制了数据库列表访问，则必须指定 `ODOO_DB`
- 推荐使用 API Key 身份验证以获得更好的安全性
- 服务器还会从工作目录中的 `.env` 文件加载环境变量

#### 高级配置

| 变量 | 默认值 | 描述 |
|----------|---------|-------------|
| `ODOO_MCP_DEFAULT_LIMIT` | `10` | 每次搜索默认返回的记录数 |
| `ODOO_MCP_MAX_LIMIT` | `100` | 每次请求允许的最大记录限制 |
| `ODOO_MCP_MAX_SMART_FIELDS` | `15` | 智能字段选择返回的最大字段数 |
| `ODOO_MCP_LOG_LEVEL` | `INFO` | 日志级别 (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `ODOO_MCP_LOG_JSON` | `false` | 启用结构化 JSON 日志输出 |
| `ODOO_MCP_LOG_FILE` | — | 滚动日志文件路径 (10 MB, 5 个备份) |
| `ODOO_MCP_TRANSPORT` | `stdio` | 传输类型 (`stdio`, `sse`, `streamable-http`) |
| `ODOO_MCP_HOST` | `localhost` | HTTP 传输绑定的主机 |
| `ODOO_MCP_PORT` | `8000` | HTTP 传输绑定的端口 |
| `ODOO_MCP_DISABLED_TOOLS` | — | 逗号分隔的禁用工具列表（如 `create_record,delete_record`） |
| `ODOO_MCP_READONLY` | `true` | 只读模式（阻止所有写操作） |
| `ODOO_MCP_HTTP_TOKEN` | — | HTTP 传输的 Bearer Token 认证 |
| `ODOO_MCP_STRICT_SECURITY` | `true` | 启用严格安全检查（非本地 HTTP 必须设置 Token） |
| `ODOO_MCP_MAX_WORKERS` | `20` | 线程池最大工作线程数 |
| `ODOO_MCP_MAX_BULK_SIZE` | `100` | 批量操作的最大记录数（创建/更新/删除） |
| `ODOO_MCP_MODEL_ALLOWLIST` | — | 逗号分隔的允许访问的模型名（空=允许所有） |
| `ODOO_MCP_MODEL_BLOCKLIST` | — | 逗号分隔的禁止访问的模型名 |
| `ODOO_MCP_WRITE_ALLOWLIST` | — | 逗号分隔的允许写操作的模型名 |
| `ODOO_MCP_ALLOWED_HOSTS` | — | 逗号分隔的允许主机（DNS rebinding 防护） |
| `ODOO_MCP_ALLOWED_ORIGINS` | — | 逗号分隔的允许来源（CORS） |
| `ODOO_MCP_STATELESS_HTTP` | `true` | 启用无状态 HTTP 模式（无会话持久化） |

### 传输选项

服务器支持多种传输协议，以适应不同的使用场景：

#### 1. **stdio** (默认)
标准输入/输出传输 - 被 Claude Desktop 等桌面 AI 应用程序使用。

```bash
# 默认传输 - 无需额外配置
uvx fast-odoo-mcp
```

#### 2. **streamable-http**
标准的 HTTP 传输，用于类似 REST API 的访问和远程连接。

```bash
# 使用 HTTP 传输运行
uvx fast-odoo-mcp --transport streamable-http --host 0.0.0.0 --port 8000

# 或使用环境变量
export ODOO_MCP_TRANSPORT=streamable-http
export ODOO_MCP_HOST=0.0.0.0
export ODOO_MCP_PORT=8000
uvx fast-odoo-mcp
```

HTTP 端点将在以下地址可用: `http://localhost:8000/mcp/`

> **注意**: SSE (Server-Sent Events) 传输已在 MCP 协议版本 2025-03-26 中弃用。请改用 streamable-http 传输进行基于 HTTP 的通信。需要 MCP 库 v1.9.4 或更高版本才能进行适当的会话管理。

<details>
<summary>运行 streamable-http 传输进行远程访问</summary>

```json
{
  "mcpServers": {
    "odoo-remote": {
      "command": "uvx",
      "args": ["fast-odoo-mcp", "--transport", "streamable-http", "--port", "8080"],
      "env": {
        "ODOO_URL": "https://your-odoo-instance.com",
        "ODOO_API_KEY": "your-api-key-here",
        "ODOO_DB": "your-database-name"
      }
    }
  }
}
```
</details>

### 身份验证与访问控制

与原版的 `fast-odoo-mcp` 不同，此定制版本**无需安装任何自定义 Odoo 模块**。它直接利用 Odoo 原生的 XML-RPC 或 JSON/2 端点。

您的访问权限完全由您提供的标准 Odoo 用户凭据（`ODOO_USER` 和 `ODOO_PASSWORD`）决定。MCP 服务器将自动继承该用户的访问权限、记录规则和模型权限。

- **建议:** 在您的 Odoo 实例中创建一个专用的 "MCP API 用户"，并仅分配 AI 执行任务所需的特定访问权限（群组）。

### 🔒 只读模式与工具禁用

如果你希望 MCP 服务**只允许查询，禁止增删改**（防止 AI 滥用导致数据被误操作），可以通过环境变量 `ODOO_MCP_DISABLED_TOOLS` 来禁用指定的工具：

```bash
# Docker 示例：禁用所有写操作工具（只读模式）
docker run -d --name odoo-mcp-server \
  -e ODOO_MCP_DISABLED_TOOLS="create_record,update_record,delete_record,create_records,update_records,delete_records" \
  ...其他参数...
```

**可禁用的工具名称：**

| 工具名称 | 说明 |
| :--- | :--- |
| `create_record` | 创建单条记录 |
| `update_record` | 更新单条记录 |
| `delete_record` | 删除单条记录 |
| `create_records` | 批量创建记录 |
| `update_records` | 批量更新记录 |
| `delete_records` | 批量删除记录 |

配置后，AI 尝试调用被禁用的工具时会收到"工具已被管理员禁用"的错误提示，从源头杜绝误操作风险。

> **注意:** 原文档提到了 YOLO 模式和 `ODOO_YOLO` 环境变量。在这个统一版本中，连接类已更新，通过标准 API 提供通用访问，无需特殊的绕过标志。`ODOO_YOLO` 变量仍然可以用于测试，但标准身份验证在开箱即用状态下即可完美运行。

## 使用示例

配置完成后，您可以这样向 Claude 提问：

**搜索与检索:**
- "显示所有来自西班牙的客户"
- "查找库存低于 10 件的产品"
- "列出今天金额超过 1000 美元的销售订单"
- "搜索上个月未支付的发票"
- "统计我们有多少名在职员工"
- "显示微软的联系信息"

**创建与管理:**
- "为 Acme Corporation 创建一个新的客户联系人"
- "添加一个名为 'Premium Widget' 的新产品，价格为 99.99 美元"
- "为明天下午 2 点创建一个日历事件"
- "将客户 John Doe 的电话号码更新为 +1-555-0123"
- "将订单 SO/2024/001 的状态更改为已确认"
- "删除我们之前创建的测试联系人"

## 可用工具 (Tools)

### `search_records`
带有过滤条件的任意 Odoo 模型记录搜索。

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true], ["country_id.code", "=", "ES"]],
  "fields": ["name", "email", "phone"],
  "limit": 10
}
```

**字段选择选项:**
- 忽略 `fields` 或设置为 `null`: 返回智能选择的常用字段
- 指定字段列表: 仅返回指定的字段
- 使用 `["__all__"]`: 返回所有字段 (谨慎使用)

### `get_record`
通过 ID 检索特定记录。

```json
{
  "model": "res.partner",
  "record_id": 42,
  "fields": ["name", "email", "street", "city"]
}
```

**字段选择选项:**
- 忽略 `fields` 或设置为 `null`: 返回带有元数据的智能选择常用字段
- 指定字段列表: 仅返回指定的字段
- 使用 `["__all__"]`: 返回不带元数据的所有字段

### `list_models`
列出所有允许 MCP 访问的模型。

```json
{}
```

### `list_resource_templates`
列出可用的资源 URI 模板及其模式。

```json
{}
```

### `create_record`
在 Odoo 中创建新记录。

```json
{
  "model": "res.partner",
  "values": {
    "name": "New Customer",
    "email": "customer@example.com",
    "is_company": true
  }
}
```

### `update_record`
更新现有记录。

```json
{
  "model": "res.partner",
  "record_id": 42,
  "values": {
    "phone": "+1234567890",
    "website": "https://example.com"
  }
}
```

### `delete_record`
从 Odoo 中删除记录。

```json
{
  "model": "res.partner",
  "record_id": 42
}
```

### `create_records`
批量创建多条记录。

```json
{
  "model": "res.partner",
  "records": [
    {"name": "客户 A", "email": "a@example.com"},
    {"name": "客户 B", "email": "b@example.com"}
  ]
}
```

### `update_records`
批量更新多条记录。

```json
{
  "model": "res.partner",
  "records": [
    {"id": 1, "phone": "+1111111111"},
    {"id": 2, "phone": "+2222222222"}
  ]
}
```

### `delete_records`
批量删除多条记录。

```json
{
  "model": "res.partner",
  "ids": [42, 43, 44]
}
```

### `execute_method`
执行 Odoo 模型上的任意方法。

```json
{
  "model": "sale.order",
  "method": "action_confirm",
  "args": [42]
}
```

### `simulate_onchange`
模拟模型字段的 onchange 行为。

```json
{
  "model": "sale.order",
  "values": {"partner_id": 1},
  "field_name": "partner_id"
}
```

### `get_model_methods`
列出 Odoo 模型上可用的方法。

```json
{
  "model": "sale.order"
}
```

### `validate_domain`
验证 Odoo 搜索域表达式。

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true], ["country_id.code", "=", "US"]]
}
```

### `server_info`
获取服务器版本和配置信息。

```json
{}
```

### `get_public_config`
获取公开的（非敏感）服务器配置。

```json
{}
```

### 智能字段选择

当您省略 `fields` 参数 (或将其设置为 `null`) 时，服务器会自动使用评分算法为每个模型选择最相关的字段：

- **基础字段** 如 `id`, `name`, `display_name`, 和 `active` 始终被包含
- **业务相关字段** (state, amount, email, phone, partner 等) 被优先选择
- **技术字段** (消息线程、活动跟踪、网站元数据) 被排除
- **昂贵的字段** (二进制、HTML、大文本、未存储的计算字段) 被跳过

默认限制是每次请求 15 个字段。响应中包含元数据，显示返回了哪些字段以及有多少个总可用字段。您可以使用 `ODOO_MCP_MAX_SMART_FIELDS` 调整限制，或使用 `fields: ["__all__"]` 完全绕过它。

## 资源 (Resources)

服务器还通过资源 URI 提供对 Odoo 数据的直接访问：

| URI 模式 | 描述 |
|------------|-------------|
| `odoo://{model}/record/{id}` | 通过 ID 检索特定记录 |
| `odoo://{model}/search` | 使用默认设置搜索记录 (前 10 条) |
| `odoo://{model}/count` | 统计模型中的所有记录数 |
| `odoo://{model}/fields` | 获取模型的字段定义和元数据 |

**示例:**
- `odoo://res.partner/record/1` — 获取 ID 为 1 的业务伙伴
- `odoo://product.product/search` — 列出前 10 个产品
- `odoo://res.partner/count` — 统计所有业务伙伴
- `odoo://product.product/fields` — 显示产品的所有字段

> **注意:** 资源 URI 不支持查询参数 (如 `?domain=...`)。对于过滤、分页和字段选择，请改用 `search_records` 工具。

## 工作原理

```
AI 助手 (Claude, Copilot 等)
        ↓ MCP 协议 (stdio 或 HTTP)
   fast-odoo-mcp
        ↓ XML-RPC
   Odoo 实例
```

服务器将 MCP 工具调用转换为 Odoo XML-RPC 请求。它处理身份验证、访问控制、字段选择、数据格式化和错误处理 — 将 Odoo 数据以对 LLM 友好的层次化文本格式呈现。

## 安全性

- 在生产环境中始终使用 HTTPS
- 确保您的 API Key 安全并定期轮换
- 谨慎配置模型访问权限 - 仅启用必要的模型
- MCP 模块（如果您选择使用的话）遵循 Odoo 内置的访问权限和记录规则，但是 **在不安装模块的情况下直接使用原生的 XML-RPC** 同样安全地遵循了所有规则。
- 每个 API Key 都与具有特定权限的特定用户相关联

## 故障排除

<details>
<summary>连接问题</summary>

如果您遇到连接错误：
1. 验证您的 Odoo URL 是否正确且可访问
2. 检查 Odoo 服务器是否允许 XML-RPC 或 JSON/2 连接
3. 确保您的防火墙允许连接到 Odoo
</details>

<details>
<summary>身份验证错误</summary>

如果身份验证失败：
1. 验证您的 API Key 在 Odoo 中是否处于活动状态
2. 检查用户是否具有适当的权限
3. 尝试重新生成 API Key
4. 对于用户名/密码验证，确保未启用双因素认证 (2FA)
</details>

<details>
<summary>模型访问错误</summary>

如果您无法访问某些模型：
1. 确保该模型存在，且您的 `ODOO_USER` 在 Odoo 中具有正确的访问权限 (Access Rights) 和记录规则 (Record Rules)。
2. 在 Odoo 中，前往 设置 > 用户和公司 > 用户 来修改权限。
</details>

<details>
<summary>"spawn uvx ENOENT" 错误</summary>

此错误意味着 UV 未安装或不在您的 PATH 环境变量中：

**解决方案 1: 安装 UV** (参见上面的安装部分)

**解决方案 2: macOS PATH 问题**
macOS 上的 Claude Desktop 不会继承您 shell 的 PATH。尝试：
1. 完全退出 Claude Desktop (Cmd+Q)
2. 打开终端
3. 从终端启动 Claude:
   ```bash
   open -a "Claude"
   ```

**解决方案 3: 使用完整路径**
找到 UV 的位置并使用完整路径：
```bash
which uvx
# 示例输出: /Users/yourname/.local/bin/uvx
```

然后更新您的配置：
```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["fast-odoo-mcp"]
}
```
</details>

<details>
<summary>数据库配置问题</summary>

如果您在列出数据库时看到 "Access Denied" (拒绝访问)：
- 这是正常的 - 某些 Odoo 实例出于安全考虑限制了数据库列表访问
- 请确保在配置中指定了 `ODOO_DB`
- 服务器将使用您指定的数据库而不进行验证

示例配置：
```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "ODOO_DB": "your-database-name"
  }
}
```
注意：如果您的服务器限制了数据库列表，则必须提供 `ODOO_DB`。
</details>

<details>
<summary>"SSL: CERTIFICATE_VERIFY_FAILED" 错误</summary>

当 Python 无法验证 SSL 证书时（通常在 macOS 或企业网络上），会发生此错误。

**解决方案**: 在环境配置中添加 SSL 证书路径：

```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "SSL_CERT_FILE": "/etc/ssl/cert.pem"
  }
}
```

这告诉 Python 在哪里找到系统的 SSL 证书包以进行 HTTPS 连接。路径 `/etc/ssl/cert.pem` 是大多数系统上的标准位置。
</details>

<details>
<summary>调试模式</summary>

启用调试日志以获取更多信息：

```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "ODOO_MCP_LOG_LEVEL": "DEBUG"
  }
}
```
</details>

## 开发

<details>
<summary>从源码运行</summary>

```bash
# 克隆仓库
git clone https://github.com/hjdhnx/fast-odoo-mcp.git
cd fast-odoo-mcp

# 以开发模式安装
pip install -e ".[dev]"

# 运行测试
pytest --cov

# 运行服务器
python -m fast_odoo_mcp

# 检查版本
python -m fast_odoo_mcp --version
```
</details>

<details>
<summary>使用 MCP Inspector 测试</summary>

```bash
# 使用 uvx
npx @modelcontextprotocol/inspector uvx fast-odoo-mcp

# 使用本地安装
npx @modelcontextprotocol/inspector python -m fast_odoo_mcp
```
</details>

## 测试

### 运行测试

```bash
# 单元测试 (无需 Odoo)
uv run pytest -m "not yolo and not mcp" --cov

# YOLO 集成测试 (原版 Odoo，无需 MCP 模块)
uv run pytest -m "yolo" -v

# MCP 集成测试 (Odoo + 已安装 MCP 模块)
uv run pytest -m "mcp" -v

# 所有测试
uv run pytest --cov

# 运行特定测试类别
uv run pytest tests/test_tools.py -v
uv run pytest tests/test_server_foundation.py -v
```

## 许可证

本项目采用 Mozilla Public License 2.0 (MPL-2.0) 许可证 - 有关详细信息，请参阅 [LICENSE](LICENSE) 文件。

## 贡献

非常欢迎各位的贡献！请参阅 [CONTRIBUTING](CONTRIBUTING.md) 指南了解详细信息。

## 支持

如果您喜欢这个项目，请不要忘记给它一个星标（star）！ :star:
