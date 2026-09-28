import asyncio
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from copilot.mcp_server import build_server
from tests.test_tools import RECORDS

SERVER = build_server(lambda pid: RECORDS if pid == "p1" else None)


def call(name, args):
    content = asyncio.run(SERVER.call_tool(name, args))
    content = content[0] if isinstance(content, tuple) else content
    return json.loads(content[0].text)


def test_three_tools_with_patient_id_required():
    tools = {t.name: t for t in asyncio.run(SERVER.list_tools())}
    assert set(tools) == {"get_patient_summary", "get_changes_since_last_visit", "get_lab_series"}
    assert all("patient_id" in t.inputSchema["required"] for t in tools.values())
    assert tools["get_lab_series"].inputSchema["required"] == ["patient_id", "lab"]


def test_lab_series_over_mcp_keeps_sources():
    out = call("get_lab_series", {"patient_id": "p1", "lab": "creatinine"})
    assert [p["source"] for p in out["points"]] == ["c1", "c3", "c4"]


def test_unknown_patient_is_a_tool_error_not_a_crash():
    with pytest.raises(ToolError, match="No patient"):
        asyncio.run(SERVER.call_tool("get_lab_series", {"patient_id": "x", "lab": "egfr"}))
