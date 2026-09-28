"""A real MCP server process over stdio, backed by test records instead of Supabase."""
from copilot.mcp_server import build_server
from tests.test_tools import RECORDS

if __name__ == "__main__":
    build_server(lambda pid: RECORDS if pid == "p1" else None).run("stdio")
