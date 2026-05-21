# Odoo MCP Server 快速部署指南

本文档说明 fast-odoo-mcp 的 3 种部署方式，并解释常用环境变量的含义、默认值和配置注意事项。

支持的 3 种 MCP 传输方式：

1. stdio：本地 MCP 客户端直接启动进程，通过标准输入输出通信。
2. streamable-http：推荐的 HTTP 部署方式，适合常驻服务、远程访问、反向代理和高并发。
3. sse：旧版 SSE 兼容方式，仅建议旧客户端无法使用 streamable-http 时启用。

## 1. 部署前准备

进入项目目录：

```bash
cd /path/to/fast-odoo-mcp
```

推荐使用 uv 安装依赖：

```bash
uv sync
```

也可以使用普通 Python 虚拟环境：

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e .
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
```

至少需要准备：

- ODOO_URL
- ODOO_DB
- 认证方式二选一：ODOO_API_KEY，或 ODOO_USER + ODOO_PASSWORD

标准安全模式下，服务访问 Odoo MCP 插件提供的 XML-RPC 路径：

- /mcp/xmlrpc/common
- /mcp/xmlrpc/object

如果要直接连接 Odoo 原生 XML-RPC，请使用 ODOO_YOLO=read 或 ODOO_YOLO=true。生产环境应谨慎启用 YOLO，尤其不要用管理员账号配合 ODOO_YOLO=true。

## 2. 推荐 .env 模板

在项目根目录创建 .env：

```env
# Odoo 基础连接
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database
ODOO_USER=admin
ODOO_PASSWORD=admin
# ODOO_API_KEY=your-api-key

# MCP 传输方式：stdio / streamable-http / sse
ODOO_MCP_TRANSPORT=stdio
ODOO_MCP_HOST=localhost
ODOO_MCP_PORT=8000

# 安全默认值
ODOO_MCP_READONLY=true
ODOO_MCP_STRICT_SECURITY=true
# HTTP/SSE 暴露到非 localhost 时必须配置
# ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token

# 并发和查询限制
ODOO_MCP_MAX_WORKERS=20
ODOO_MCP_DEFAULT_LIMIT=10
ODOO_MCP_MAX_LIMIT=100
ODOO_MCP_MAX_BULK_SIZE=100
ODOO_MCP_MAX_SMART_FIELDS=15

# 模型访问范围，可按需启用
# ODOO_MCP_MODEL_ALLOWLIST=res.partner,sale.order,account.move
# ODOO_MCP_MODEL_BLOCKLIST=res.users,ir.config_parameter

# 写操作模型白名单（需 ODOO_MCP_READONLY=false 生效）
# 留空=所有模型可写，设置后仅列出的模型允许 create/write/unlink，其余模型只读
# ODOO_MCP_WRITE_ALLOWLIST=res.partner,sale.order

# 可选：禁用指定 MCP 工具，逗号分隔
# ODOO_MCP_DISABLED_TOOLS=create_record,update_record,delete_record

# 日志与语言
ODOO_MCP_LOG_LEVEL=INFO
# ODOO_LOCALE=zh_CN

# YOLO 直连 Odoo 原生接口：off / read / true
ODOO_YOLO=off
```

## 3. 方法一：stdio 本地部署

stdio 是默认方式。MCP 客户端启动本服务进程，并通过标准输入输出通信。

适合：

- Claude Desktop / Claude Code / Cursor 等本机 MCP 客户端。
- 本地开发和调试。
- 不需要开放 HTTP 端口的场景。

.env 示例：

```env
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database
ODOO_USER=admin
ODOO_PASSWORD=admin
ODOO_MCP_TRANSPORT=stdio
ODOO_MCP_READONLY=true
ODOO_MCP_STRICT_SECURITY=true
ODOO_YOLO=off
```

启动：

```bash
python -m fast_odoo_mcp --transport stdio
```

如果 .env 已配置 ODOO_MCP_TRANSPORT=stdio，也可以直接执行：

```bash
python -m fast_odoo_mcp
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "odoo": {
      "command": "python",
      "args": ["-m", "fast_odoo_mcp", "--transport", "stdio"],
      "cwd": "/path/to/fast-odoo-mcp",
      "env": {
        "ODOO_URL": "http://localhost:8069",
        "ODOO_DB": "your_odoo_database",
        "ODOO_USER": "admin",
        "ODOO_PASSWORD": "admin",
        "ODOO_MCP_READONLY": "true",
        "ODOO_YOLO": "off"
      }
    }
  }
}
```

如果使用项目虚拟环境里的 Python，command 可以改为：

```json
"/path/to/fast-odoo-mcp/.venv/Scripts/python.exe"
```


## 4. 方法二：streamable-http 服务部署（推荐生产方式）

streamable-http 是推荐的 HTTP 传输方式，适合服务常驻、远程 MCP 客户端访问、反向代理和高并发场景。

适合：

- 多客户端连接。
- Docker、systemd、PM2、Windows 服务等常驻部署。
- Nginx/Caddy 反向代理。
- 高并发调用。

### 4.1 本机 HTTP 启动

.env：

```env
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database
ODOO_USER=admin
ODOO_PASSWORD=admin

ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=localhost
ODOO_MCP_PORT=8000
ODOO_MCP_READONLY=true
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_MAX_WORKERS=20
ODOO_YOLO=off
```

启动：

```bash
python -m fast_odoo_mcp --transport streamable-http --host localhost --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

### 4.2 对局域网或服务器公网开放

只要绑定非 localhost，尤其是 0.0.0.0，生产环境必须配置 ODOO_MCP_HTTP_TOKEN。

.env：

```env
ODOO_URL=http://odoo.internal:8069
ODOO_DB=your_odoo_database
ODOO_USER=mcp_user
ODOO_PASSWORD=strong-password

ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_READONLY=true
ODOO_MCP_MAX_WORKERS=30
ODOO_YOLO=off
```

启动：

```bash
python -m fast_odoo_mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

MCP 业务请求需要携带认证头，二选一：

```http
Authorization: Bearer replace-with-a-long-random-token
```

或：

```http
X-MCP-Token: replace-with-a-long-random-token
```

注意：/health、/ready、/metrics 是探活接口，默认放行；MCP 业务请求会校验 token。

### 4.3 反向代理建议

建议 MCP 服务只监听本机或内网地址：

```env
ODOO_MCP_HOST=127.0.0.1
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
```

然后用 Nginx/Caddy 提供 HTTPS、访问控制和日志审计。

注意事项：

- 外部访问必须使用 HTTPS。
- 不要把无 token 的 MCP HTTP 服务直接暴露到公网。
- 反向代理要保留 Authorization 或 X-MCP-Token 请求头。
- 如果外部域名访问失败，检查服务的 allowed hosts/origins 是否包含目标 host。


### 4.4 Docker Compose 服务器部署示例

如果要在服务器上长期运行 HTTP MCP 服务，推荐使用 Docker Compose 部署 `streamable-http`，并配置 `ODOO_MCP_HTTP_TOKEN`。

#### 目录结构示例

```text
/opt/fast-odoo-mcp/
├── docker-compose.yml
└── .env
```

#### `.env` 示例

```env
ODOO_URL=http://odoo:8069
ODOO_DB=your_odoo_database
ODOO_USER=mcp_user
ODOO_PASSWORD=strong-password

ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_READONLY=true
ODOO_MCP_MAX_WORKERS=30
ODOO_MCP_DEFAULT_LIMIT=10
ODOO_MCP_MAX_LIMIT=100
ODOO_MCP_MAX_BULK_SIZE=100
ODOO_YOLO=off
```

如果 Odoo 不在同一个 Docker 网络里，把 `ODOO_URL` 改成服务器可访问的地址，例如：

```env
ODOO_URL=http://192.168.1.100:8069
```

#### `docker-compose.yml` 示例：直接从当前源码构建

本仓库根目录已经提供 `docker-compose.yml`，路径是：

```text
/path/to/fast-odoo-mcp/docker-compose.yml
```

把项目目录复制到服务器后，在该目录内执行 `docker compose up -d --build` 即可。下面是文件内容示例。

这里的运行原理是：

- `build: .` 表示 Docker Compose 使用当前目录的 `Dockerfile` 构建镜像。
- `image: my-odoo-mcp:latest` 表示构建出来的镜像名称和标签。
- `container_name: fast-odoo-mcp` 表示运行后的容器名称，不是镜像名称。
- 执行 `docker compose up -d --build` 时会自动 build 镜像，不需要你先手动执行 `docker build`。
- 如果镜像已存在且 Dockerfile 或源码没有变化，可以执行 `docker compose up -d` 直接启动。
- 如果你想手动构建，也可以执行 `docker compose build`，或 `docker build -t my-odoo-mcp:latest .`。
- 你可以用 `docker images | grep my-odoo-mcp` 查看构建出来的镜像。
- 你可以用 `docker ps` 查看运行中的容器名，例如 `odoo-mcp-server-client-a` 和 `odoo-mcp-server-client-b`。
- 修改 Python 代码、Dockerfile 或依赖后，重新执行 `docker compose up -d --build`；只改 `.env.client-a` / `.env.client-b` 时，一般执行 `docker compose up -d` 或 `docker compose restart` 即可。


```yaml
services:
  fast-odoo-mcp:
    image: my-odoo-mcp:latest
    build: .
    container_name: fast-odoo-mcp
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8000:8000"
    command:
      - python
      - -m
      - fast_odoo_mcp
      - --transport
      - streamable-http
      - --host
      - 0.0.0.0
      - --port
      - "8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f fast-odoo-mcp
```

停止：

```bash
docker compose down
```

#### `docker-compose.yml` 示例：和 Odoo 在同一 Compose 网络

如果 Odoo 也在同一个 `docker-compose.yml` 或同一个 Docker 网络中，`ODOO_URL` 可以写服务名，例如 `http://odoo:8069`。

```yaml
services:
  fast-odoo-mcp:
    image: my-odoo-mcp:latest
    build: .
    container_name: fast-odoo-mcp
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8000:8000"
    networks:
      - odoo-net
    command:
      - python
      - -m
      - fast_odoo_mcp
      - --transport
      - streamable-http
      - --host
      - 0.0.0.0
      - --port
      - "8000"

networks:
  odoo-net:
    external: true
```

如果 Odoo Compose 网络不是 `odoo-net`，用下面命令查看实际网络名：

```bash
docker network ls
```

#### 服务器防火墙和反向代理建议

生产环境更推荐只让 MCP 容器监听本机或内网，再通过 Nginx/Caddy 暴露 HTTPS。

如果只允许本机反向代理访问，可以把端口映射改成：

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Nginx 反向代理时要保留认证头：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header X-MCP-Token $http_x_mcp_token;
}
```

外部 MCP 客户端访问时仍需要带：

```http
Authorization: Bearer replace-with-a-long-random-token
```

或：

```http
X-MCP-Token: replace-with-a-long-random-token
```


#### 执行 `docker compose up -d --build` 的策略和已有容器冲突说明

`docker compose up -d --build` 的执行策略可以理解为：

1. 先读取当前目录的 `docker-compose.yml`。
2. 看到 `build: .` 后，使用当前目录的 `Dockerfile` 构建镜像。
3. 如果配置了 `image: my-odoo-mcp:latest`，构建结果会被命名为 `my-odoo-mcp:latest`。
4. 然后根据 service 配置创建或更新容器。
5. 如果容器已经由同一个 Compose 项目创建，Compose 会复用并按配置重建。
6. 如果服务器上已经有手动 `docker run` 创建的同名容器，Compose 不会自动接管，通常会因为容器名冲突失败。
7. 如果宿主机端口已被旧容器占用，Compose 不会自动抢占端口，会报端口占用错误。

也就是说，如果你原本已经用 `docker run` 启动过占用 `8000` 和 `8001` 的容器，直接执行本文档当前示例不一定会成功。

当前双服务 Compose 示例使用：

```yaml
ports:
  - "8001:8000"
```

和：

```yaml
ports:
  - "8002:8000"
```

这表示：

- 容器内部都监听 `8000`。
- 第一个 MCP 服务映射到宿主机 `8001`。
- 第二个 MCP 服务映射到宿主机 `8002`。

如果你旧的 `docker run` 容器已经占用了宿主机 `8001`，新的 Compose 第一个服务会端口冲突。

如果旧容器名称刚好也是：

```text
odoo-mcp-server-client-a
odoo-mcp-server-client-b
```

那么即使端口不冲突，也会发生容器名冲突。

迁移前建议先检查：

```bash
docker ps --format "table {{.Names}}	{{.Ports}}"
```

查看镜像：

```bash
docker images | grep my-odoo-mcp
```

如果你想保留旧容器继续运行，可以把 Compose 端口改成没被占用的端口，例如：

```yaml
ports:
  - "8011:8000"
```

和：

```yaml
ports:
  - "8012:8000"
```

然后启动：

```bash
docker compose up -d --build
```

如果你想用 Compose 替代旧的 `docker run` 容器，推荐流程是：

```bash
# 1. 先查看旧容器名称和端口
docker ps --format "table {{.Names}}	{{.Ports}}"

# 2. 停止旧容器
docker stop odoo-mcp-server-client-a odoo-mcp-server-client-b

# 3. 删除旧容器。删除容器不会删除镜像，也不会删除你当前项目代码。
docker rm odoo-mcp-server-client-a odoo-mcp-server-client-b

# 4. 用 Compose 重新构建并启动
docker compose up -d --build

# 5. 查看新容器状态
docker compose ps
```

如果旧容器名称不是这两个，请把命令里的名称替换成 `docker ps` 查到的实际名称。

如果只是改了 `.env.client-a` 或 `.env.client-b`，不需要重新 build 镜像，通常执行：

```bash
docker compose up -d
```

或：

```bash
docker compose restart
```

如果改了 Python 源码、`Dockerfile`、`pyproject.toml` 或依赖锁文件，需要重新 build：

```bash
docker compose up -d --build
```

#### 同时部署两个 MCP 服务

如果你原来是用两条 `docker run` 同时启动两个 MCP 服务，例如一个连集团内网 Odoo，一个连另一个线上 Odoo，用 Docker Compose 时推荐拆成两个 service。

核心原则：

- 两个 service 可以共用同一个镜像，例如 `image: my-odoo-mcp:latest`。
- `build: .` 只需要构建一次；Compose 会把同一个镜像用于两个容器。
- `image` 是镜像名，`container_name` 是容器名，两者不是一回事。
- 每个 service 使用不同的 `container_name`。
- 每个 service 使用不同的 `env_file`，分别保存各自的 Odoo 地址、账号、数据库和 token。
- 容器内部都可以监听 `8000`，但宿主机端口必须不同，例如 `8001:8000` 和 `8002:8000`。
- 推荐使用 `streamable-http`，不要再用旧的 `sse`，除非客户端只支持 SSE。

目录结构示例：

```text
/opt/fast-odoo-mcp/
├── docker-compose.yml
├── .env.client-a
└── .env.client-b
```

`.env.client-a` 示例：

```env
ODOO_URL=http://192.168.1.100:8069
ODOO_DB=group_database
ODOO_USER=mcp_user
ODOO_PASSWORD=strong-password

ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=replace-with-group-token
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_READONLY=true
ODOO_MCP_MAX_WORKERS=20
ODOO_MCP_DEFAULT_LIMIT=10
ODOO_MCP_MAX_LIMIT=100
ODOO_YOLO=off
```

`.env.client-b` 示例：

```env
ODOO_URL=https://your-odoo.example.com:8069
ODOO_DB=your-database
ODOO_USER=mcp_user
ODOO_PASSWORD=strong-password

ODOO_MCP_TRANSPORT=streamable-http
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=your-secret-token
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_READONLY=true
ODOO_MCP_MAX_WORKERS=20
ODOO_MCP_DEFAULT_LIMIT=10
ODOO_MCP_MAX_LIMIT=100
ODOO_MCP_DISABLED_TOOLS=create_record,update_record,delete_record,create_records,update_records,delete_records
ODOO_YOLO=off
```

对应的 `docker-compose.yml`：

```yaml
services:
  odoo-mcp-server-client-a:
    image: my-odoo-mcp:latest
    build: .
    container_name: odoo-mcp-server-client-a
    restart: unless-stopped
    env_file:
      - .env.client-a
    environment:
      ODOO_MCP_TRANSPORT: streamable-http
      ODOO_MCP_HOST: 0.0.0.0
      ODOO_MCP_PORT: "8000"
    ports:
      - "8001:8000"
    command:
      - --transport
      - streamable-http
      - --host
      - 0.0.0.0
      - --port
      - "8000"
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen(http://127.0.0.1:8000/ready, timeout=5)"
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  odoo-mcp-server-client-b:
    image: my-odoo-mcp:latest
    build: .
    container_name: odoo-mcp-server-client-b
    restart: unless-stopped
    env_file:
      - .env.client-b
    environment:
      ODOO_MCP_TRANSPORT: streamable-http
      ODOO_MCP_HOST: 0.0.0.0
      ODOO_MCP_PORT: "8000"
    ports:
      - "8002:8000"
    command:
      - --transport
      - streamable-http
      - --host
      - 0.0.0.0
      - --port
      - "8000"
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen(http://127.0.0.1:8000/ready, timeout=5)"
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

启动两个服务：

```bash
docker compose up -d --build
```

只启动其中一个服务：

```bash
docker compose up -d odoo-mcp-server-client-a
docker compose up -d odoo-mcp-server-client-b
```

查看日志：

```bash
docker compose logs -f odoo-mcp-server-client-a
docker compose logs -f odoo-mcp-server-client-b
```

健康检查：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/ready
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/ready
```

外部 MCP 客户端连接时：

- 集团服务对应宿主机端口 `8001`，token 使用 `.env.client-a` 里的 `ODOO_MCP_HTTP_TOKEN`。
- Client B 服务对应宿主机端口 `8002`，token 使用 `.env.client-b` 里的 `ODOO_MCP_HTTP_TOKEN`。
- 两个服务必须配置不同的 MCP 名称，避免客户端里重名。

如果你的旧客户端仍然只能使用 SSE，把两个 service 里的环境变量和 command 改成：

```yaml
environment:
  ODOO_MCP_TRANSPORT: sse
  ODOO_MCP_HOST: 0.0.0.0
  ODOO_MCP_PORT: "8000"
command:
  - --transport
  - sse
  - --host
  - 0.0.0.0
  - --port
  - "8000"
```

但新部署建议优先使用 `streamable-http`。


#### Docker Compose 部署检查

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/metrics
```

如果 `/ready` 不是 200，优先检查：

- 容器内是否能访问 `ODOO_URL`。
- `ODOO_DB` 是否正确。
- `ODOO_USER` / `ODOO_PASSWORD` 或 `ODOO_API_KEY` 是否正确。
- Odoo 端是否安装并启用了 MCP 插件接口。
- 如果绑定 `0.0.0.0`，是否配置了 `ODOO_MCP_HTTP_TOKEN`。

## 5. 方法三：SSE 兼容部署

SSE 是旧 MCP 传输方式。新部署优先使用 streamable-http，只有旧客户端必须使用 SSE 时才建议启用。

适合：

- 旧版 MCP 客户端只支持 SSE。
- 迁移期临时兼容。

### 5.1 本机 SSE 启动

.env：

```env
ODOO_URL=http://localhost:8069
ODOO_DB=your_odoo_database
ODOO_USER=admin
ODOO_PASSWORD=admin

ODOO_MCP_TRANSPORT=sse
ODOO_MCP_HOST=localhost
ODOO_MCP_PORT=8000
ODOO_MCP_READONLY=true
ODOO_MCP_STRICT_SECURITY=true
ODOO_YOLO=off
```

启动：

```bash
python -m fast_odoo_mcp --transport sse --host localhost --port 8000
```

### 5.2 远程 SSE 启动

远程 SSE 同样必须配置 token：

```env
ODOO_MCP_TRANSPORT=sse
ODOO_MCP_HOST=0.0.0.0
ODOO_MCP_PORT=8000
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
ODOO_MCP_STRICT_SECURITY=true
```

启动：

```bash
python -m fast_odoo_mcp --transport sse --host 0.0.0.0 --port 8000
```

客户端请求需要带：

```http
Authorization: Bearer replace-with-a-long-random-token
```

或：

```http
X-MCP-Token: replace-with-a-long-random-token
```


## 6. 环境变量完整说明

### 6.1 Odoo 连接变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ODOO_URL | 是 | 无 | Odoo 服务地址，必须以 http:// 或 https:// 开头，例如 http://localhost:8069。 |
| ODOO_DB | 建议 | 无 | Odoo 数据库名。多库环境必须配置；单库也建议显式配置。 |
| ODOO_API_KEY | 二选一 | 无 | Odoo API Key。标准模式可只配置 API Key；YOLO 模式下如果使用 API Key，仍需要 ODOO_USER。 |
| ODOO_USER | 二选一 | 无 | Odoo 用户名或登录邮箱。和 ODOO_PASSWORD 配套使用。 |
| ODOO_PASSWORD | 二选一 | 无 | Odoo 密码。和 ODOO_USER 配套使用。 |
| ODOO_LOCALE | 否 | 无 | 指定语言环境，例如 zh_CN、en_US、fr_FR。 |
| ODOO_YOLO | 否 | off | Odoo 连接模式：off 使用 MCP 插件安全接口；read 直连原生 XML-RPC 只读；true 直连原生 XML-RPC 并允许写操作。 |

ODOO_YOLO 可用值：

| 值 | 含义 |
| --- | --- |
| off / false / 0 / no / 空 | 标准安全模式，使用 /mcp/xmlrpc/*。 |
| read / readonly / read-only | 直连 Odoo 原生 /xmlrpc/2/*，只读。 |
| true / 1 / yes / full | 直连 Odoo 原生 /xmlrpc/2/*，读写都允许。生产环境慎用。 |

### 6.2 MCP 传输变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ODOO_MCP_TRANSPORT | 否 | stdio | MCP 传输方式：stdio、streamable-http、sse。 |
| ODOO_MCP_HOST | HTTP/SSE 必填 | localhost | HTTP/SSE 监听地址。HTTP/SSE 模式下建议显式配置，避免意外暴露。 |
| ODOO_MCP_PORT | HTTP/SSE 必填 | 8000 | HTTP/SSE 监听端口。HTTP/SSE 模式下建议显式配置。 |
| ODOO_MCP_HTTP_TOKEN | 远程 HTTP/SSE 必填 | 无 | HTTP/SSE MCP 业务请求认证 token。绑定非 localhost 或 0.0.0.0 时必须配置。 |
| ODOO_MCP_STRICT_SECURITY | 否 | true | 严格安全模式。开启后，HTTP/SSE 非本机监听必须配置 ODOO_MCP_HTTP_TOKEN。 |

### 6.3 访问控制和安全变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ODOO_MCP_READONLY | 否 | true | 是否只读。默认 true，不会注册创建、更新、删除、批量写入等工具。要开放写操作必须显式设为 false。 |
| ODOO_MCP_MODEL_ALLOWLIST | 否 | 空 | 模型白名单，逗号分隔，例如 res.partner,sale.order。非空时只允许访问列出的模型。 |
| ODOO_MCP_MODEL_BLOCKLIST | 否 | 空 | 模型黑名单，逗号分隔，例如 res.users,ir.config_parameter。黑名单优先级高于白名单。 |
| ODOO_MCP_WRITE_ALLOWLIST | 否 | 空 | 写操作模型白名单，逗号分隔，例如 res.partner,sale.order。需 ODOO_MCP_READONLY=false。留空时所有模型均可写；设置后仅列出的模型允许 create/write/unlink，其余模型只读（read 不受影响）。 |
| ODOO_MCP_DISABLED_TOOLS | 否 | 空 | 禁用指定 MCP 工具，逗号分隔。即使只读关闭，也可以用它单独禁用高风险工具。 |
| ODOO_MCP_MAX_BULK_SIZE | 否 | 100 | 批量创建、更新、删除最大记录数，避免一次请求造成大规模误操作或长时间阻塞。 |

推荐生产安全配置：

```env
ODOO_MCP_READONLY=true
ODOO_MCP_STRICT_SECURITY=true
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
ODOO_MCP_MODEL_BLOCKLIST=res.users,ir.config_parameter
ODOO_MCP_MAX_BULK_SIZE=100
```

如果确实需要写操作：

```env
ODOO_MCP_READONLY=false
ODOO_MCP_MODEL_ALLOWLIST=res.partner,sale.order
ODOO_MCP_MAX_BULK_SIZE=20
```

建议给 MCP 单独创建 Odoo 用户，只授予需要的模型权限，不要直接使用管理员账号。

### 6.4 查询限制和 AI 上下文变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ODOO_MCP_DEFAULT_LIMIT | 否 | 10 | 查询默认返回条数。 |
| ODOO_MCP_MAX_LIMIT | 否 | 100 | 单次查询最大返回条数，防止大结果集撑爆 MCP 客户端上下文。 |
| ODOO_MCP_MAX_SMART_FIELDS | 否 | 15 | 智能字段选择时最多返回多少个字段，减少 AI 上下文占用。 |

### 6.5 并发和日志变量

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ODOO_MCP_MAX_WORKERS | 否 | 20 | 后台线程池最大 worker 数，用于执行同步 Odoo RPC，避免阻塞 async HTTP 事件循环。高并发 HTTP 部署可适当调大。 |
| ODOO_MCP_LOG_LEVEL | 否 | INFO | 日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL。 |

ODOO_MCP_MAX_WORKERS 建议：

| 场景 | 建议值 |
| --- | --- |
| 本地 stdio | 5 到 10 |
| 普通 HTTP 服务 | 20 |
| 多客户端高并发 | 30 到 50 |

不要盲目调太高。Odoo 后端、数据库连接数、CPU 和网络延迟都会影响实际吞吐。

## 7. 高并发稳定性建议

1. 优先使用 streamable-http，不要用 sse 做新部署。
2. HTTP 部署必须配置 ODOO_MCP_HTTP_TOKEN，外部访问必须走 HTTPS。
3. ODOO_MCP_READONLY=true 作为默认生产配置，确认业务需要后再开放写工具。
4. 设置 ODOO_MCP_MODEL_ALLOWLIST，只暴露 AI 真正需要访问的模型。
5. 设置合理的 ODOO_MCP_MAX_WORKERS，通常从 20 开始压测。
6. 设置较小的 ODOO_MCP_DEFAULT_LIMIT 和 ODOO_MCP_MAX_LIMIT，避免大查询阻塞。
7. 使用 /ready 做服务就绪探针，只有 Odoo 已认证时才返回 200。
8. 使用 /health 和 /metrics 观察连接状态、重连次数、最近错误和性能统计。
9. 给 MCP 使用单独的 Odoo 用户，权限最小化。
10. 不要把 ODOO_YOLO=true 用在公网或高权限生产账号上。

## 8. 健康检查和排错

### 8.1 健康检查接口

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

返回中重点看：

- status：整体健康状态。
- connection.authenticated：是否已认证到 Odoo。
- connection.reconnect_count：自动重连次数。
- connection.retry_count：请求级重试次数。
- connection.last_error：最近一次错误。
- connection.last_connect_at：最近一次成功连接时间。
- performance：性能统计信息。

### 8.2 常见问题

#### 启动时报 ODOO_URL is required

没有配置 ODOO_URL，或者 .env 没有被当前工作目录加载。请确认在项目根目录启动，或通过环境变量显式传入。

#### 启动时报 Authentication required

认证信息不完整。请配置：

```env
ODOO_API_KEY=your-api-key
```

或：

```env
ODOO_USER=admin
ODOO_PASSWORD=admin
```

#### HTTP/SSE 启动时报必须配置 ODOO_MCP_HOST 或 ODOO_MCP_PORT

HTTP/SSE 模式要求显式配置 host 和 port，避免默认端口被意外暴露：

```env
ODOO_MCP_HOST=localhost
ODOO_MCP_PORT=8000
```

#### 绑定 0.0.0.0 启动失败

严格安全模式下，对外监听必须配置 token：

```env
ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
```

#### 客户端请求返回 401

HTTP/SSE 业务请求没有带 token，或 token 不一致。请添加：

```http
Authorization: Bearer replace-with-a-long-random-token
```

或：

```http
X-MCP-Token: replace-with-a-long-random-token
```

#### AI 查不到某个模型

检查：

- Odoo 用户是否有该模型权限。
- ODOO_MCP_MODEL_ALLOWLIST 是否没有包含该模型。
- ODOO_MCP_MODEL_BLOCKLIST 是否屏蔽了该模型。
- 标准模式下 Odoo 端 MCP 插件是否授权该模型。

#### 写入工具不可用

默认 ODOO_MCP_READONLY=true，写入、更新、删除和 bulk 工具不会注册。确需写入时配置：

```env
ODOO_MCP_READONLY=false
```

同时建议配合：

```env
ODOO_MCP_MODEL_ALLOWLIST=res.partner,sale.order
ODOO_MCP_MAX_BULK_SIZE=20
```

## 9. 生产部署检查清单

上线前确认：

- [ ] ODOO_URL 指向正确 Odoo 实例。
- [ ] 使用 MCP 专用 Odoo 用户，不使用管理员账号。
- [ ] ODOO_MCP_TRANSPORT=streamable-http。
- [ ] ODOO_MCP_HOST 和 ODOO_MCP_PORT 已显式配置。
- [ ] 非本机访问已配置 ODOO_MCP_HTTP_TOKEN。
- [ ] 外部访问使用 HTTPS 反向代理。
- [ ] ODOO_MCP_READONLY=true，除非明确需要写入。
- [ ] 已配置 ODOO_MCP_MODEL_ALLOWLIST 或 ODOO_MCP_MODEL_BLOCKLIST。
- [ ] ODOO_MCP_MAX_LIMIT 和 ODOO_MCP_MAX_BULK_SIZE 不过大。
- [ ] /ready 返回 200。
- [ ] /health 中 connection.authenticated=true。
- [ ] 已观察 /metrics 中没有持续增长的错误或重连。

## 10. 快速命令汇总

stdio：

```bash
python -m fast_odoo_mcp --transport stdio
```

streamable-http 本机：

```bash
python -m fast_odoo_mcp --transport streamable-http --host localhost --port 8000
```

streamable-http 对外：

```bash
export ODOO_MCP_HTTP_TOKEN=replace-with-a-long-random-token
python -m fast_odoo_mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

SSE：

```bash
python -m fast_odoo_mcp --transport sse --host localhost --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

## Docker 构建慢和国内源配置

如果在服务器上执行 `docker compose up -d --build` 很慢，通常不是 MCP 服务本身的问题，而是 Docker 构建阶段需要访问几个外部源：

1. `python:3.12-slim-bookworm`：基础 Python 镜像，默认从 Docker Hub 拉取。
2. `ghcr.io/astral-sh/uv:latest`：uv 工具镜像，默认从 GitHub Container Registry 拉取。
3. Python 依赖包：`uv pip install` 默认会访问 Python 包索引。

当前 `Dockerfile` 已经支持通过 build args 配置这些来源：

| 构建参数 | 默认值 | 作用 |
| --- | --- | --- |
| `PYTHON_IMAGE` | `python:3.12-slim-bookworm` | 构建阶段和运行阶段使用的 Python 基础镜像。 |
| `UV_IMAGE` | `ghcr.io/astral-sh/uv:latest` | 用来复制 `uv` / `uvx` 命令的镜像。 |
| `UV_INDEX_URL` | `https://pypi.tuna.tsinghua.edu.cn/simple` | `uv pip install` 安装 Python 依赖时使用的包索引。 |

`docker-compose.yml` 已经把这些参数透传给 Dockerfile。你可以在项目目录创建一个给 Compose 读取的 `.env` 文件，专门控制构建源：

```env
PYTHON_IMAGE=python:3.12-slim-bookworm
UV_IMAGE=ghcr.io/astral-sh/uv:latest
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

然后执行：

```bash
docker compose up -d --build
```

如果你的服务器拉 Docker Hub 或 GHCR 很慢，单独配置 `UV_INDEX_URL` 只能加速 Python 依赖安装，不能加速基础镜像下载。基础镜像下载慢需要在服务器 Docker 守护进程层面配置镜像加速，或者把 `PYTHON_IMAGE` / `UV_IMAGE` 改成你内网仓库中已经同步好的镜像，例如：

```env
PYTHON_IMAGE=registry.example.com/library/python:3.12-slim-bookworm
UV_IMAGE=registry.example.com/astral-sh/uv:latest
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

如果没有内网仓库，也可以先在网络较好的机器上拉取并推送到你的私有镜像仓库，再在服务器上通过上述两个变量替换来源。

### 重复构建为什么仍然慢

如果 Dockerfile、依赖文件或源码有变化，`docker compose up -d --build` 会重新执行镜像构建。依赖安装步骤会重新校验和安装 Python 包。当前 Dockerfile 不再使用 `uv pip install --no-cache`，这样 Docker/BuildKit 在可用时可以更好地复用构建缓存。

常见建议：

- 只修改 `.env.client-a` / `.env.client-b` 这类运行环境变量时，通常不用重新 build，执行 `docker compose up -d` 或 `docker compose restart` 即可。
- 修改 Python 代码、`Dockerfile`、`pyproject.toml` 后，再执行 `docker compose up -d --build`。
- 如果旧的手动 `docker run` 容器仍占用 8000 / 8001 端口，Compose 构建可能成功，但启动容器会因为端口占用失败，需要先停止旧容器或改 Compose 端口映射。

## 远程客户端找不到 MCP 工具的排查

如果 `/ready` 可以访问，但在 Claude、Cherry Studio、Dify 或其他 MCP 客户端里看不到工具，优先检查下面几项：

1. streamable-http 地址使用 `/mcp`：

```json
{
  "mcpServers": {
    "odoo-group": {
      "type": "streamable-http",
      "url": "http://192.168.1.100:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    },
    "odoo-client-b": {
      "type": "streamable-http",
      "url": "http://192.168.1.100:8001/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    }
  }
}
```

2. token 要和服务端 `ODOO_MCP_HTTP_TOKEN` 完全一致。服务端支持两种 header，任选一种：

```json
"headers": {
  "Authorization": "Bearer your-secret-token"
}
```

或：

```json
"headers": {
  "X-MCP-Token": "your-secret-token"
}
```

3. 远程访问时要配置 Host 白名单。

FastMCP 默认会做 DNS rebinding 防护。容器里服务绑定 `0.0.0.0` 时，客户端实际访问的 Host 是服务器 IP，例如 `192.168.1.100:8000`。如果没有加入白名单，请求可能被拒绝，客户端就会表现为找不到 MCP 服务或工具。

Docker Compose 示例里已经增加：

```yaml
environment:
  ODOO_MCP_ALLOWED_HOSTS: 192.168.1.100:8000,192.168.1.100:8001
  ODOO_MCP_ALLOWED_ORIGINS: http://192.168.1.100:8000,http://192.168.1.100:8001
```

如果你的服务器 IP、域名或端口不同，要替换成自己的地址。例如使用域名：

```env
ODOO_MCP_ALLOWED_HOSTS=mcp.example.com:8000,mcp.example.com:8001
ODOO_MCP_ALLOWED_ORIGINS=http://mcp.example.com:8000,http://mcp.example.com:8001,https://mcp.example.com
```

修改后重新构建并启动：

```bash
docker compose up -d --build
```

然后查看状态和日志：

```bash
docker compose ps
docker compose logs -f odoo-mcp-server-client-a
docker compose logs -f odoo-mcp-server-client-b
```
