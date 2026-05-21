# 终极 Odoo MCP Docker 部署与运行指南

由于 MCP 的特殊性，使用 Docker 运行它有**两种不同的模式**，这取决于您使用的 AI 客户端支持哪种通信协议。

> **前置条件**：您已经通过 `docker build -t odoo-mcp .` 命令成功构建了本地 Docker 镜像。
> **注意**：在 Docker 容器内部，访问您宿主机（Windows本机）上运行的 Odoo 服务，请使用 `host.docker.internal` 而不是 `localhost`。

---

## 模式一：本地直接使用 Docker 作为 Command (推荐给 Claude Desktop)

如果您想让 Cursor 或 Claude Desktop 等本地 AI 工具通过 Docker 运行这个 MCP（走 `stdio` 标准输入输出模式），**不需要您提前手动去运行容器**。您只需要在 AI 客户端的配置里，把启动命令设置成 Docker 的 `run` 命令即可。

**在 Claude Desktop 的 `claude_desktop_config.json` 中配置：**

```json
{
  "mcpServers": {
    "odoo-mcp-docker": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "ODOO_URL=http://host.docker.internal:8069",
        "-e", "ODOO_DB=your_database_name",
        "-e", "ODOO_USER=admin",
        "-e", "ODOO_PASSWORD=your_password",
        "-e", "ODOO_YOLO=true",
        "odoo-mcp"
      ]
    }
  }
}
```
*(保存配置文件后，重启 Claude Desktop，它就会在后台自动用这个 Docker 镜像启动 MCP 服务进行通信了。)*

---

## 模式二：作为独立网络服务长期运行 (推荐给 Cursor / Trae)

如果您想把这个 Docker 容器当成一个一直运行的后台服务，通过网络端口暴露出来，供本地的 Cursor、Trae 或者局域网内其他人的客户端连接，请走 SSE 模式。

### 1. 在终端（PowerShell）中启动 Docker 容器

请在您的终端里执行以下命令，让它在后台监听 `8000` 端口：

```powershell
docker run -d --name odoo-mcp-server `
  -p 8000:8000 `
  -e ODOO_URL=http://host.docker.internal:8069 `
  -e ODOO_DB=your_database_name `
  -e ODOO_USER=admin `
  -e ODOO_PASSWORD=your_password `
  -e ODOO_YOLO=true `
  odoo-mcp --transport sse --host 0.0.0.0 --port 8000
```

### 2. 在您的 AI 助手 (如 Cursor / Trae) 中配置连接

运行成功后，打开您 IDE 的 MCP 设置面板：

- **Type / 类型**: 选择 `SSE`
- **Name / 名称**: `Odoo MCP Docker`
- **URL**: 填入 `http://localhost:8000/sse`

配置完成后保存，IDE 就能通过本机的 8000 端口，与运行在 Docker 里的 Odoo MCP 代理网关进行高速通信了！
