"""Test package structure and basic functionality."""

import subprocess
import sys


class TestPackageStructure:
    """Test the package structure and configuration."""

    def test_package_imports(self):
        """Test that the package can be imported with expected exports."""
        import fast_odoo_mcp

        assert hasattr(fast_odoo_mcp, "__version__")
        assert hasattr(fast_odoo_mcp, "OdooMCPServer")

    def test_cli_help(self):
        """Test CLI help output contains expected content."""
        result = subprocess.run(
            [sys.executable, "-m", "fast_odoo_mcp", "--help"], capture_output=True, text=True
        )

        assert result.returncode == 0
        # argparse sends --help to stdout
        assert "Odoo MCP Server" in result.stdout
        assert "ODOO_URL" in result.stdout
