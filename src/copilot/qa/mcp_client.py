"""Connect the agent to our MCP server, as an MCP client.

The server runs as a child process over stdio, one per question. The agent only ever sees
tools through this connection, the same way any other MCP client would.
"""
import os
import sys
from contextlib import asynccontextmanager

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

def server_config(args: list[str] | None = None) -> dict:
    # env passed explicitly: the MCP stdio client otherwise starts the child with only a
    # minimal environment (no DATABASE_URL, no PYTHONPATH)
    return {"copilot": {"transport": "stdio", "command": sys.executable,
                        "args": args or ["-m", "copilot.mcp_server"], "env": dict(os.environ)}}


@asynccontextmanager
async def mcp_tools(servers: dict | None = None):
    client = MultiServerMCPClient(servers or server_config())
    async with client.session("copilot") as session:
        yield await load_mcp_tools(session)
