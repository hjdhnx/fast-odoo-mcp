# MCP Server for Odoo

[![CI](https://github.com/hjdhnx/fast-odoo-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/hjdhnx/fast-odoo-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hjdhnx/fast-odoo-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/hjdhnx/fast-odoo-mcp)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with ty](https://img.shields.io/badge/checked%20with-ty-blue?labelColor=orange)](https://github.com/astral-sh/ty)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

An MCP server that enables AI assistants like Claude to interact with Odoo ERP systems. Access business data, search records, create new entries, update existing data, and manage your Odoo instance through natural language.

**Works with any Odoo instance!** This modified version uses Odoo's native XML-RPC and JSON/2 APIs, meaning **NO Odoo module installation is required**. It works out-of-the-box with any standard Odoo installation (v14.0 to v19.0+).

## Features

- 🔍 **Search and retrieve** any Odoo record (customers, products, invoices, etc.)
- ✨ **Create new records** with field validation and permission checks
- ✏️ **Update existing data** with smart field handling
- 🗑️ **Delete records** respecting model-level permissions
- 🔢 **Count records** matching specific criteria
- 📋 **Inspect model fields** to understand data structure
- 🔐 **Secure access** with API key or username/password authentication
- 🎯 **Smart pagination** for large datasets
- 🧠 **Smart field selection** — automatically picks the most relevant fields per model
- 💬 **LLM-optimized output** with hierarchical text formatting
- 🌍 **Multi-language support** — get responses in your preferred language
- 🚀 **YOLO Mode** for quick access with any Odoo instance (no module required)

## Installation

### Prerequisites

- Python 3.10 or higher
- Access to an Odoo instance:
  - Any Odoo version from 14.0 to 19.0+ with XML-RPC or JSON/2 enabled
  - **NO Odoo module installation required**
  - Works entirely through native Odoo APIs

### Install UV First

The MCP server runs on your **local computer** (where Claude Desktop is installed), not on your Odoo server. You need to install UV on your local machine:

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

After installation, restart your terminal to ensure UV is in your PATH.

### Installing via MCP Settings (Recommended)

Add this configuration to your MCP settings:

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

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Add to `.mcp.json` in your project root:

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

Or use the CLI:

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

Add to `~/.cursor/mcp.json`:

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
<summary>VS Code (with GitHub Copilot)</summary>

Add to `.vscode/mcp.json` in your workspace:

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

> **Note:** VS Code uses `"servers"` as the root key, not `"mcpServers"`.
</details>

<details>
<summary>Windsurf</summary>

Add to `~/.codeium/windsurf/mcp_config.json`:

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

Add to `~/.config/zed/settings.json`:

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

### Alternative Installation Methods

<details>
<summary>Using Docker</summary>

Run with Docker — no Python installation required:

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

> **Note:** Use `host.docker.internal` instead of `localhost` to connect to Odoo running on the host machine.

For HTTP transport:

```bash
docker run --rm -p 8000:8000 \
  -e ODOO_URL=http://host.docker.internal:8069 \
  -e ODOO_API_KEY=your-api-key-here \
  hjdhnx/fast-odoo-mcp --transport streamable-http --host 0.0.0.0
```

The image is also available on GHCR: `ghcr.io/hjdhnx/fast-odoo-mcp`
</details>

<details>
<summary>Using pip</summary>

```bash
# Install globally
pip install fast-odoo-mcp

# Or use pipx for isolated environment
pipx install fast-odoo-mcp
```

Then use `fast-odoo-mcp` as the command in your MCP configuration.
</details>

<details>
<summary>From source</summary>

```bash
git clone https://github.com/hjdhnx/fast-odoo-mcp.git
cd fast-odoo-mcp
pip install -e .
```

Then use the full path to the package in your MCP configuration.
</details>

## Configuration

### Environment Variables

The server requires the following environment variables:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ODOO_URL` | Yes | Your Odoo instance URL | `https://mycompany.odoo.com` |
| `ODOO_API_KEY` | Yes* | API key for authentication | `0ef5b399e9ee9c11b053dfb6eeba8de473c29fcd` |
| `ODOO_USER` | Yes* | Username (if not using API key) | `admin` |
| `ODOO_PASSWORD` | Yes* | Password (if not using API key) | `admin` |
| `ODOO_DB` | No | Database name (auto-detected if not set) | `mycompany` |
| `ODOO_LOCALE` | No | Language/locale for Odoo responses | `es_ES`, `fr_FR`, `de_DE` |
| `ODOO_YOLO` | No | YOLO mode - bypasses MCP security (⚠️ DEV ONLY) | `off`, `read`, `true` |

*Either `ODOO_API_KEY` or both `ODOO_USER` and `ODOO_PASSWORD` are required.

**Notes:**
- If database listing is restricted on your server, you must specify `ODOO_DB`
- API key authentication is recommended for better security
- The server also loads environment variables from a `.env` file in the working directory

#### Advanced Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ODOO_MCP_DEFAULT_LIMIT` | `10` | Default number of records returned per search |
| `ODOO_MCP_MAX_LIMIT` | `100` | Maximum allowed record limit per request |
| `ODOO_MCP_MAX_SMART_FIELDS` | `15` | Maximum fields returned by smart field selection |
| `ODOO_MCP_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `ODOO_MCP_LOG_JSON` | `false` | Enable structured JSON log output |
| `ODOO_MCP_LOG_FILE` | — | Path for rotating log file (10 MB, 5 backups) |
| `ODOO_MCP_TRANSPORT` | `stdio` | Transport type (`stdio`, `sse`, `streamable-http`) |
| `ODOO_MCP_HOST` | `localhost` | Host to bind for HTTP transport |
| `ODOO_MCP_PORT` | `8000` | Port to bind for HTTP transport |
| `ODOO_MCP_DISABLED_TOOLS` | — | Comma-separated list of tools to disable (e.g. `create_record,delete_record`) |
| `ODOO_MCP_READONLY` | `true` | Read-only mode (prevents all write operations) |
| `ODOO_MCP_HTTP_TOKEN` | — | Bearer token for HTTP transport authentication |
| `ODOO_MCP_STRICT_SECURITY` | `true` | Enforce strict security checks (require token for non-local HTTP) |
| `ODOO_MCP_MAX_WORKERS` | `20` | Maximum thread pool workers for concurrent requests |
| `ODOO_MCP_MAX_BULK_SIZE` | `100` | Maximum records per bulk operation (create/update/delete) |
| `ODOO_MCP_MODEL_ALLOWLIST` | — | Comma-separated model names to allow (empty = all allowed) |
| `ODOO_MCP_MODEL_BLOCKLIST` | — | Comma-separated model names to block |
| `ODOO_MCP_WRITE_ALLOWLIST` | — | Comma-separated model names allowed for write operations |
| `ODOO_MCP_ALLOWED_HOSTS` | — | Comma-separated allowed hosts for DNS rebinding protection |
| `ODOO_MCP_ALLOWED_ORIGINS` | — | Comma-separated allowed origins for CORS |
| `ODOO_MCP_STATELESS_HTTP` | `true` | Enable stateless HTTP mode (no session persistence) |

### Transport Options

The server supports multiple transport protocols for different use cases:

#### 1. **stdio** (Default)
Standard input/output transport - used by desktop AI applications like Claude Desktop.

```bash
# Default transport - no additional configuration needed
uvx fast-odoo-mcp
```

#### 2. **streamable-http**
Standard HTTP transport for REST API-style access and remote connectivity.

```bash
# Run with HTTP transport
uvx fast-odoo-mcp --transport streamable-http --host 0.0.0.0 --port 8000

# Or use environment variables
export ODOO_MCP_TRANSPORT=streamable-http
export ODOO_MCP_HOST=0.0.0.0
export ODOO_MCP_PORT=8000
uvx fast-odoo-mcp
```

The HTTP endpoint will be available at: `http://localhost:8000/mcp/`

> **Note**: SSE (Server-Sent Events) transport has been deprecated in MCP protocol version 2025-03-26. Use streamable-http transport instead for HTTP-based communication. Requires MCP library v1.9.4 or higher for proper session management.

<details>
<summary>Running streamable-http transport for remote access</summary>

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

### Authentication & Access Control

Unlike the original `fast-odoo-mcp`, this customized version **does not require installing any custom Odoo modules**. It leverages Odoo's native XML-RPC or JSON/2 endpoints.

Your access is governed entirely by the standard Odoo user credentials you provide (`ODOO_USER` and `ODOO_PASSWORD`). The MCP server will automatically inherit the access rights, record rules, and model permissions of that user.

- **Recommendation:** Create a dedicated "MCP API User" in your Odoo instance and assign it only the specific Access Rights (Groups) necessary for the tasks you want the AI to perform.

> **Note:** The original documentation referenced a YOLO mode and an `ODOO_YOLO` environment variable. In this unified version, the connection class has been updated to provide universal access through standard APIs without needing special bypass flags. The `ODOO_YOLO` variable can still be used for testing, but standard authentication works perfectly out of the box.

## Usage Examples

Once configured, you can ask Claude:

**Search & Retrieve:**
- "Show me all customers from Spain"
- "Find products with stock below 10 units"
- "List today's sales orders over $1000"
- "Search for unpaid invoices from last month"
- "Count how many active employees we have"
- "Show me the contact information for Microsoft"

**Create & Manage:**
- "Create a new customer contact for Acme Corporation"
- "Add a new product called 'Premium Widget' with price $99.99"
- "Create a calendar event for tomorrow at 2 PM"
- "Update the phone number for customer John Doe to +1-555-0123"
- "Change the status of order SO/2024/001 to confirmed"
- "Delete the test contact we created earlier"

## Available Tools

### `search_records`
Search for records in any Odoo model with filters.

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true], ["country_id.code", "=", "ES"]],
  "fields": ["name", "email", "phone"],
  "limit": 10
}
```

**Field Selection Options:**
- Omit `fields` or set to `null`: Returns smart selection of common fields
- Specify field list: Returns only those specific fields
- Use `["__all__"]`: Returns all fields (use with caution)

### `get_record`
Retrieve a specific record by ID.

```json
{
  "model": "res.partner",
  "record_id": 42,
  "fields": ["name", "email", "street", "city"]
}
```

**Field Selection Options:**
- Omit `fields` or set to `null`: Returns smart selection of common fields with metadata
- Specify field list: Returns only those specific fields
- Use `["__all__"]`: Returns all fields without metadata

### `list_models`
List all models enabled for MCP access.

```json
{}
```

### `list_resource_templates`
List available resource URI templates and their patterns.

```json
{}
```

### `create_record`
Create a new record in Odoo.

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
Update an existing record.

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
Delete a record from Odoo.

```json
{
  "model": "res.partner",
  "record_id": 42
}
```

### `create_records`
Bulk create multiple records in a single call.

```json
{
  "model": "res.partner",
  "records": [
    {"name": "Customer A", "email": "a@example.com"},
    {"name": "Customer B", "email": "b@example.com"}
  ]
}
```

### `update_records`
Bulk update multiple records by ID.

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
Bulk delete multiple records by ID.

```json
{
  "model": "res.partner",
  "ids": [42, 43, 44]
}
```

### `execute_method`
Execute an arbitrary method on an Odoo model.

```json
{
  "model": "sale.order",
  "method": "action_confirm",
  "args": [42]
}
```

### `simulate_onchange`
Simulate onchange behavior for a model's field values.

```json
{
  "model": "sale.order",
  "values": {"partner_id": 1},
  "field_name": "partner_id"
}
```

### `get_model_methods`
List available methods on an Odoo model.

```json
{
  "model": "sale.order"
}
```

### `validate_domain`
Validate an Odoo search domain expression.

```json
{
  "model": "res.partner",
  "domain": [["is_company", "=", true], ["country_id.code", "=", "US"]]
}
```

### `server_info`
Get server version and configuration information.

```json
{}
```

### `get_public_config`
Get the public (non-sensitive) server configuration.

```json
{}
```

### Smart Field Selection

When you omit the `fields` parameter (or set it to `null`), the server automatically selects the most relevant fields for each model using a scoring algorithm:

- **Essential fields** like `id`, `name`, `display_name`, and `active` are always included
- **Business-relevant fields** (state, amount, email, phone, partner, etc.) are prioritized
- **Technical fields** (message threads, activity tracking, website metadata) are excluded
- **Expensive fields** (binary, HTML, large text, computed non-stored) are skipped

The default limit is 15 fields per request. Responses include metadata showing which fields were returned and how many total fields are available. You can adjust the limit with `ODOO_MCP_MAX_SMART_FIELDS` or bypass it entirely with `fields: ["__all__"]`.

## Resources

The server also provides direct access to Odoo data through resource URIs:

| URI Pattern | Description |
|------------|-------------|
| `odoo://{model}/record/{id}` | Retrieve a specific record by ID |
| `odoo://{model}/search` | Search records with default settings (first 10 records) |
| `odoo://{model}/count` | Count all records in a model |
| `odoo://{model}/fields` | Get field definitions and metadata for a model |

**Examples:**
- `odoo://res.partner/record/1` — Get partner with ID 1
- `odoo://product.product/search` — List first 10 products
- `odoo://res.partner/count` — Count all partners
- `odoo://product.product/fields` — Show all fields for products

> **Note:** Resource URIs don't support query parameters (like `?domain=...`). For filtering, pagination, and field selection, use the `search_records` tool instead.

## How It Works

```
AI Assistant (Claude, Copilot, etc.)
        ↓ MCP Protocol (stdio or HTTP)
   fast-odoo-mcp
        ↓ XML-RPC
   Odoo Instance
```

The server translates MCP tool calls into Odoo XML-RPC requests. It handles authentication, access control, field selection, data formatting, and error handling — presenting Odoo data in an LLM-friendly hierarchical text format.

## Security

- Always use HTTPS in production environments
- Keep your API keys secure and rotate them regularly
- Configure model access carefully - only enable necessary models
- The MCP module (if you choose to use it) respects Odoo's built-in access rights and record rules, but **using native XML-RPC without the module** respects the same rules securely.
- Each API key is linked to a specific user with their permissions

## Troubleshooting

<details>
<summary>Connection Issues</summary>

If you're getting connection errors:
1. Verify your Odoo URL is correct and accessible
2. Check that the Odoo server allows XML-RPC or JSON/2 connections
3. Ensure your firewall allows connections to Odoo
</details>

<details>
<summary>Authentication Errors</summary>

If authentication fails:
1. Verify your API key is active in Odoo
2. Check that the user has appropriate permissions
3. Try regenerating the API key
4. For username/password auth, ensure 2FA is not enabled
</details>

<details>
<summary>Model Access Errors</summary>

If you can't access certain models:
1. Ensure the model exists and your `ODOO_USER` has the correct Access Rights and Record Rules in Odoo.
2. In Odoo, go to Settings > Users & Companies > Users to modify access.
</details>

<details>
<summary>"spawn uvx ENOENT" Error</summary>

This error means UV is not installed or not in your PATH:

**Solution 1: Install UV** (see Installation section above)

**Solution 2: macOS PATH Issue**
Claude Desktop on macOS doesn't inherit your shell's PATH. Try:
1. Quit Claude Desktop completely (Cmd+Q)
2. Open Terminal
3. Launch Claude from Terminal:
   ```bash
   open -a "Claude"
   ```

**Solution 3: Use Full Path**
Find UV location and use full path:
```bash
which uvx
# Example output: /Users/yourname/.local/bin/uvx
```

Then update your config:
```json
{
  "command": "/Users/yourname/.local/bin/uvx",
  "args": ["fast-odoo-mcp"]
}
```
</details>

<details>
<summary>Database Configuration Issues</summary>

If you see "Access Denied" when listing databases:
- This is normal - some Odoo instances restrict database listing for security
- Make sure to specify `ODOO_DB` in your configuration
- The server will use your specified database without validation

Example configuration:
```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "ODOO_DB": "your-database-name"
  }
}
```
Note: `ODOO_DB` is required if database listing is restricted on your server.
</details>

<details>
<summary>"SSL: CERTIFICATE_VERIFY_FAILED" Error</summary>

This error occurs when Python cannot verify SSL certificates, often on macOS or corporate networks.

**Solution**: Add SSL certificate path to your environment configuration:

```json
{
  "env": {
    "ODOO_URL": "https://your-odoo.com",
    "ODOO_API_KEY": "your-key",
    "SSL_CERT_FILE": "/etc/ssl/cert.pem"
  }
}
```

This tells Python where to find the system's SSL certificate bundle for HTTPS connections. The path `/etc/ssl/cert.pem` is the standard location on most systems.
</details>

<details>
<summary>Debug Mode</summary>

Enable debug logging for more information:

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

## Development

<details>
<summary>Running from source</summary>

```bash
# Clone the repository
git clone https://github.com/hjdhnx/fast-odoo-mcp.git
cd fast-odoo-mcp

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest --cov

# Run the server
python -m fast_odoo_mcp

# Check version
python -m fast_odoo_mcp --version
```
</details>

<details>
<summary>Testing with MCP Inspector</summary>

```bash
# Using uvx
npx @modelcontextprotocol/inspector uvx fast-odoo-mcp

# Using local installation
npx @modelcontextprotocol/inspector python -m fast_odoo_mcp
```
</details>

## Testing

### Running Tests

```bash
# Unit tests (no Odoo needed)
uv run pytest -m "not yolo and not mcp" --cov

# YOLO integration tests (vanilla Odoo, no MCP module)
uv run pytest -m "yolo" -v

# MCP integration tests (Odoo + MCP module installed)
uv run pytest -m "mcp" -v

# All tests
uv run pytest --cov

# Run specific test categories
uv run pytest tests/test_tools.py -v
uv run pytest tests/test_server_foundation.py -v
```

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0) - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are very welcome! Please see the [CONTRIBUTING](CONTRIBUTING.md) guide for details.

## Support

If you like this project, do not forget to give it a star! :star: