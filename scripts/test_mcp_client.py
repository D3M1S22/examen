#!/usr/bin/env python3
"""Live MCP Client Verification Script for EXAMEN.

Connects to the running FastMCP server over Streamable HTTP and invokes all 5 core tools:
1. create_planned_task
2. verify_action_status
3. get_daily_actions_recap
4. query_social_contact
5. get_topic_briefing

Usage:
    python scripts/test_mcp_client.py [--url http://127.0.0.1:8042/mcp]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


async def run_mcp_tests(server_url: str):
    print(f"\n{BOLD}{CYAN}Connecting to EXAMEN MCP Server at:{RESET} {server_url}\n")

    try:
        async with streamable_http_client(server_url) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print(f"{GREEN}✓ Connected & Handshake Complete!{RESET}\n")

                # 1. Discover Tools
                print(f"{BOLD}1. Discovering MCP Tools:{RESET}")
                tools_res = await session.list_tools()
                for tool in tools_res.tools:
                    print(f"  • {BOLD}{tool.name}{RESET}: {DIM}{tool.description[:70]}...{RESET}")

                # 2. Test create_planned_task
                print(f"\n{BOLD}2. Invoking 'create_planned_task':{RESET}")
                res1 = await session.call_tool(
                    "create_planned_task",
                    {"title": "controllare chiusura gas", "domain": "safety"},
                )
                for item in res1.content:
                    if hasattr(item, "text"):
                        data = json.loads(item.text)
                        print(f"  {GREEN}✓ Task Created:{RESET} ID: {data.get('task_id')}, Title: \"{data.get('title')}\", Status: {data.get('status')}")

                # 3. Test verify_action_status
                print(f"\n{BOLD}3. Invoking 'verify_action_status':{RESET}")
                res2 = await session.call_tool("verify_action_status", {"action_query": "stove_off"})
                for item in res2.content:
                    if hasattr(item, "text"):
                        data = json.loads(item.text)
                        status_color = GREEN if data.get("verified") else YELLOW
                        print(f"  {status_color}✓ Verified:{RESET} {data.get('verified')} ({data.get('elapsed_time_human')})")
                        print(f"  {DIM}Spoken Alexa output: \"{data.get('spoken_summary')}\"{RESET}")

                # 4. Test get_daily_actions_recap
                print(f"\n{BOLD}4. Invoking 'get_daily_actions_recap':{RESET}")
                res3 = await session.call_tool("get_daily_actions_recap", {"domain": "all"})
                for item in res3.content:
                    if hasattr(item, "text"):
                        data = json.loads(item.text)
                        print(f"  {GREEN}✓ Recap total actions:{RESET} {data.get('total_actions')}")
                        print(f"  {DIM}Spoken Alexa output: \"{data.get('spoken_summary')}\"{RESET}")

                # 5. Test query_social_contact
                print(f"\n{BOLD}5. Invoking 'query_social_contact':{RESET}")
                res4 = await session.call_tool("query_social_contact", {"name_or_query": "Alessandro Rossi"})
                for item in res4.content:
                    if hasattr(item, "text"):
                        data = json.loads(item.text)
                        if data.get("found"):
                            contact = data.get("contact", {})
                            print(f"  {MAGENTA}✓ Found Contact:{RESET} {contact.get('name')} ({contact.get('company_or_role')})")
                            print(f"  {YELLOW}Commitments:{RESET} {contact.get('commitments')}")
                            print(f"  {DIM}Spoken Alexa output: \"{data.get('spoken_summary')}\"{RESET}")
                        else:
                            print(f"  {YELLOW}Contact not found{RESET}")

                # 6. Test get_topic_briefing
                print(f"\n{BOLD}6. Invoking 'get_topic_briefing':{RESET}")
                res5 = await session.call_tool("get_topic_briefing", {"topic_query": "LangGraph"})
                for item in res5.content:
                    if hasattr(item, "text"):
                        data = json.loads(item.text)
                        if data.get("found"):
                            print(f"  {BLUE}✓ Found Briefing:{RESET} \"{data.get('topic_title')}\"")
                            print(f"  {DIM}Web sources: {len(data.get('web_sources', []))} reference(s){RESET}")
                            print(f"  {DIM}Spoken Alexa output: \"{data.get('spoken_summary')}\"{RESET}")
                        else:
                            print(f"  {YELLOW}No topic briefing found{RESET}")

                print(f"\n{GREEN}{BOLD}All MCP tool invocations succeeded!{RESET}\n")

    except Exception as e:
        print(f"\n{BOLD}\033[91mFailed to connect or invoke MCP tools:{RESET} {e}\n", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test EXAMEN MCP server live.")
    parser.add_argument("--url", default="http://127.0.0.1:8042/mcp", help="MCP endpoint URL")
    args = parser.parse_args()
    asyncio.run(run_mcp_tests(args.url))


if __name__ == "__main__":
    main()
