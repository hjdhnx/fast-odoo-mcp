import asyncio  # noqa: F401
from pathlib import Path

from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env.group-test-local")

from fast_odoo_mcp.config import get_config, reset_config  # noqa: E402

reset_config()
config = get_config()
print(f"Locale: {config.locale}")

from fast_odoo_mcp.server import OdooMCPServer  # noqa: E402


async def test():
    server = OdooMCPServer(config)
    async with server._odoo_lifespan(server.app):
        handler = server.tool_handler

        r1 = await handler._handle_execute_method_tool(
            "uom.uom", "name_search", None, ["Unit"], {"limit": 5}
        )
        print(f'Test 1 uom name_search "Unit": {r1["result"]}')

        r2 = await handler._handle_execute_method_tool(
            "res.partner", "default_get", None, [["is_company"]], {}
        )
        print(f"Test 2 default_get: {r2['result']}")

        r3 = await handler._handle_execute_method_tool(
            "crm.stage", "name_search", None, [], {"limit": 10}
        )
        print(f"Test 3 CRM stages: {r3['result']}")

        r4 = await handler._handle_execute_method_tool(
            "res.partner.title", "name_search", None, [], {"limit": 10}
        )
        print(f"Test 4 partner titles: {r4['result']}")

        r5 = await handler._handle_execute_method_tool(
            "res.country", "name_search", None, ["China"], {"limit": 5}
        )
        print(f"Test 5 country name_search: {r5['result']}")


asyncio.run(test())
print("\nLocale tests done!")
