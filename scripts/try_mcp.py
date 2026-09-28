"""Talk to the MCP server the way the Q&A agent will: separate process, stdio, JSON-RPC.

    uv run python scripts/try_mcp.py demo-ravi-kumar
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PID = sys.argv[1] if len(sys.argv) > 1 else "demo-ravi-kumar"
SERVER = StdioServerParameters(command=sys.executable, args=["-m", "copilot.mcp_server"])


async def main():
    async with stdio_client(SERVER) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = (await session.list_tools()).tools
        print("tools the agent will see:")
        for t in tools:
            print(f"  - {t.name}({', '.join(t.inputSchema['properties'])})")
            print(f"      {t.description.split('.')[0]}.")

        for name, args in [("get_changes_since_last_visit", {"patient_id": PID}),
                           ("get_lab_series", {"patient_id": PID, "lab": "potassium"}),
                           ("get_lab_series", {"patient_id": PID, "lab": "cholesterol"}),
                           ("get_patient_summary", {"patient_id": "no-such-patient"})]:
            r = await session.call_tool(name, args)
            text = r.content[0].text
            print(f"\n=== {name}({args}) {'ERROR' if r.isError else ''}")
            try:
                print(json.dumps(json.loads(text), indent=1)[:1200])
            except json.JSONDecodeError:
                print(text)

asyncio.run(main())
