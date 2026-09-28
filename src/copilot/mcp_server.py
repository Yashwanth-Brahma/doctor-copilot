"""MCP server: the three patient tools, over the Model Context Protocol.

The Q&A agent (Session 3) connects to this as an MCP client, and the UI shows each tool call.
Any other MCP client can use the same server, which is how we test it from outside:

    npx @modelcontextprotocol/inspector uv run python -m copilot.mcp_server

The tools themselves live in tools.py (pure functions). This file only adds the database and
the descriptions the agent reads to decide which tool to call.
"""
from datetime import date
from typing import Callable

from mcp.server.fastmcp import FastMCP

from . import tools


def build_server(load_records: Callable[[str], dict | None],
                 today: Callable[[], date] = date.today) -> FastMCP:
    mcp = FastMCP("doctor-copilot")

    def records(patient_id: str) -> dict:
        r = load_records(patient_id)
        if r is None:
            raise ValueError(f"No patient with id '{patient_id}'")
        return r

    @mcp.tool()
    def get_patient_summary(patient_id: str) -> dict:
        """The patient's current picture: age, sex, known problems, active medications and the
        latest value of each tracked lab (HbA1c, eGFR, creatinine, glucose, potassium).
        Use for questions about what the patient has or takes now."""
        return tools.get_patient_summary(records(patient_id), today())

    @mcp.tool()
    def get_changes_since_last_visit(patient_id: str) -> dict:
        """What changed since the last clinic visit: labs with new results (previous and latest
        value, each with its date), newly started medications, new conditions, and emergency or
        hospital visits. Use for 'what's new' or 'since last time' questions."""
        return tools.get_changes_since_last_visit(records(patient_id), today())

    @mcp.tool()
    def get_lab_series(patient_id: str, lab: str, since: str | None = None) -> dict:
        """Every result for one lab, oldest first, each with date, value, out-of-range flag and
        source record id. lab: HbA1c, eGFR, creatinine, glucose or potassium.
        since: optional start date, YYYY-MM-DD. Use for trend questions."""
        return tools.get_lab_series(records(patient_id), lab, since)

    return mcp


def main():
    import sys

    from .db import records_loader
    server = build_server(records_loader())
    # stdio for local clients (the agent, MCP Inspector); --http to serve over the network
    server.run(transport="streamable-http" if "--http" in sys.argv else "stdio")


if __name__ == "__main__":
    main()
