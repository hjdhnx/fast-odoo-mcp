# Odoo MCP 接入 Dify 指南

Dify 官方已经原生支持接入标准的 MCP (Model Context Protocol) 服务。通过将 Odoo MCP 接入 Dify，你可以轻松构建能够直接查询和操作 Odoo ERP 数据的 AI 智能体 (Agent) 和工作流。

由于 Dify 通常作为服务端运行，与 MCP 对接最推荐的方式是使用 **HTTP (SSE) 传输模式**，而不是桌面 IDE（如 Trae/Cursor）常用的 `stdio` 模式。

以下是完整的配置与使用流程。

---

## 步骤一：启动 Odoo MCP 服务 (SSE 模式)

你需要让 MCP 服务监听一个端口（例如 8000），以便 Dify 能够通过网络请求访问到它。我们推荐使用 Docker 启动，这样环境更加隔离和稳定。

### 方式 A：使用 Docker 构建并启动（推荐）

由于我们对这个 MCP 服务的代码进行了深度的汉化、修复和定制优化，在新的 Linux 服务器上，你需要先将本项目的所有代码上传到服务器中，然后自行构建 Docker 镜像。

**1. 构建 Docker 镜像**

在服务器的代码根目录（即 `Dockerfile` 所在的目录）下，执行以下命令进行打包：

```bash
docker build -t my-odoo-mcp .
```

**2. 运行 Docker 容器**

镜像构建完成后，执行以下命令启动服务（注意镜像名已经改为刚才打包的 `my-odoo-mcp`，而不是拉取远端原作者的镜像）：

```bash
docker run -d --name odoo-mcp-server \
  --restart unless-stopped \
  --ulimit nofile=65536:65536 \
  -p 8000:8000 \
  -e ODOO_URL="http://你的Odoo地址:8069" \
  -e ODOO_DB="你的数据库名" \
  -e ODOO_USER="你的账号" \
  -e ODOO_PASSWORD="你的密码" \
  my-odoo-mcp --transport sse --host 0.0.0.0 --port 8000
```

> **注意：** 
> - 如果你的 Odoo 也是跑在本地机器上的 Docker 里，`ODOO_URL` 请使用 `http://host.docker.internal:8069` 以便容器之间通信。
> - 如果你使用的是 API Key 认证，将 `-e ODOO_USER` 和 `-e ODOO_PASSWORD` 替换为 `-e ODOO_API_KEY="你的APIKey"`。

### 🔒 只读模式（推荐用于对外提供查询服务）

如果你希望 MCP 服务**只允许查询，禁止增删改**（防止 AI 滥用导致数据被误操作），只需在启动命令中增加一个环境变量 `ODOO_MCP_DISABLED_TOOLS`：

```bash
docker run -d --name odoo-mcp-server \
  --restart unless-stopped \
  --ulimit nofile=65536:65536 \
  -p 8000:8000 \
  -e ODOO_URL="http://你的Odoo地址:8069" \
  -e ODOO_DB="你的数据库名" \
  -e ODOO_USER="你的账号" \
  -e ODOO_PASSWORD="你的密码" \
  -e ODOO_MCP_DISABLED_TOOLS="create_record,update_record,delete_record,create_records,update_records,delete_records" \
  my-odoo-mcp --transport sse --host 0.0.0.0 --port 8000
```

这样配置后，AI 只能调用 `search_records`、`get_record`、`list_models`、`server_info` 等只读工具。一旦 AI 尝试调用被禁用的写操作工具，会直接收到"工具已被管理员禁用"的错误提示。

**可禁用的工具名称列表：**
| 工具名称 | 说明 |
| :--- | :--- |
| `create_record` | 创建单条记录 |
| `update_record` | 更新单条记录 |
| `delete_record` | 删除单条记录 |
| `create_records` | 批量创建记录 |
| `update_records` | 批量更新记录 |
| `delete_records` | 批量删除记录 |

### 方式 B：使用纯本地 Python 环境启动

如果你不想使用 Docker，也可以使用本地的 Python 虚拟环境启动：

```powershell
# 1. 设置环境变量
$env:ODOO_URL="http://你的Odoo地址:8069"
$env:ODOO_DB="你的数据库名"
$env:ODOO_USER="你的账号"
$env:ODOO_PASSWORD="你的密码"

# 2. 以 sse 模式启动，并绑定 0.0.0.0
D:\mypython\odoo312\Scripts\python.exe -m fast_odoo_mcp --transport sse --host 0.0.0.0 --port 8000
```

**验证启动成功：**
启动后，MCP 服务会在 `http://<你的IP>:8000` 运行。Dify 需要连接的标准 SSE 端点为：
**`http://<你的IP>:8000/sse`**

---

## 步骤二：在 Dify 中配置 MCP 工具

1. 登录你的 Dify 平台。
2. 点击顶部导航栏的 **“工具 (Tools)”**。
3. 在左侧菜单找到并点击 **“MCP”**。
4. 点击页面右上角的 **“添加 MCP 服务器 (Add MCP Server)”** 或 **“+”** 号。
5. 填写以下连接信息：
   * **名称 (Name)**: `Odoo-MCP` (或任意你喜欢的名字)
   * **传输方式 (Transport)**: 选择 **`SSE`** (Server-Sent Events)
   * **URL**: 填写 `http://<你的MCP服务器IP>:8000/sse`
     *(如果你的 Dify 是通过 Docker 部署在同一台宿主机上，这里通常填 `http://host.docker.internal:8000/sse`)*
6. 点击 **“保存”** 或 **“测试连接”**。

连接成功后，Dify 会自动解析出 Odoo MCP 提供的所有工具（如 `search_records`, `get_record`, `create_record` 等）。由于我们已经对工具进行了汉化，Dify 界面上会直接显示易于理解的中文工具描述和参数说明。

---

## 步骤三：在 Dify Agent 或工作流中使用

将工具添加到 Dify 后，你需要创建一个智能体 (Agent) 来使用这些工具。

1. 在 Dify 的“工作室”中，创建一个新的 **Agent 应用**（或者在 Chatflow 中添加 Agent 节点）。
2. 在 Agent 的配置界面中，找到 **“工具 (Tools)”** 配置区，点击添加。
3. 从弹出的工具列表中，找到 `Odoo-MCP`，勾选你需要让 AI 使用的工具（建议全部勾选，或者至少勾选 `search_records`, `get_record`, `list_models`）。
4. **【关键】配置系统提示词 (System Prompt)**：
   为了防止 AI 产生幻觉（例如猜测不存在的字段或错误使用 Domain 语法），你必须在 Agent 的“提示词 (Instructions)”中写入以下 Odoo MCP 专用规则：

```text
你是一个专业的 Odoo ERP 助手。你有权通过提供的 Odoo MCP 工具查询和修改系统数据。

在执行任务时，你必须严格遵守以下原则：

1. 零猜测原则 (Zero Hallucination)
   - 永远不要猜测 Odoo 模型的字段名称。
   - 当你需要了解某个表结构时，先使用 `get_record` (不传 fields) 查一条记录看看结构，或者使用 `list_models` 确认表名。
   - 绝不要使用不在当前模型中的字段作为搜索条件或更新值。

2. 智能字段依赖 (Smart Fields)
   - 在调用 `search_records` 或 `get_record` 时，除非用户明确要求了特定字段，否则请始终省略 `fields` 参数（或传 null）。
   - 让工具自动为你返回最相关的智能字段，这能有效避免因请求了二进制字段或不存在的字段而导致的错误。

3. 准确的 Domain 语法 (Domain Syntax)
   - Odoo 的 domain 是一个列表的列表，例如：[["name", "ilike", "张三"], ["is_company", "=", false]]
   - 绝不能将 domain 写成字典格式（如 {"name": "张三"}），这会导致严重错误。
   - 比较布尔值时使用 true/false，不要加引号。

4. 谨慎执行修改操作
   - 在调用 `create_record`, `update_record`, `delete_record` 之前，确保你已经完全理解了用户的意图。
   - 如果不确定，可以先查询确认数据现状，并在回复中告知用户你将要进行的操作。
```

## 测试你的 Odoo Agent

配置完成后，你可以在 Dify 右侧的预览窗口中进行测试。

**你可以尝试发送以下指令：**
* “帮我查询系统中最新的3条公司公告。”
* “查找名字里包含‘王佳’的员工，告诉我他的基础信息。”
* “统计一下今天创建的所有销售订单的总金额。”

Dify 的 Agent 会根据你的提示词，自主规划调用 `search_records` 或其他工具，从你的 Odoo 数据库中获取真实数据并总结回答你。