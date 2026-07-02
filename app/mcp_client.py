"""
MCP Client Helper — Wildlife Knowledge Base

Provides a synchronous wrapper around the FastMCP async client so that
deterministic Workflow nodes can call the MCP server without async plumbing.

Usage in workflow nodes:
    from app.mcp_client import query_wildlife_advice
    advice = query_wildlife_advice("Elephant behavior near farmland")
    # advice -> {"animal": "elephant", "avoid": [...], "action": "...", ...}
"""

import asyncio
import json
import os
import sys
import logging

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

logger = logging.getLogger(__name__)

# Path to the MCP server module
_SERVER_MODULE = "app.mcp_server"

# Fallback advice returned when the MCP server is unreachable or errors out
_FALLBACK_ADVICE: dict = {
    "animal": "unknown",
    "avoid": ["approaching unfamiliar wildlife"],
    "action": "keep a safe distance and contact a wildlife officer",
    "emergency_tips": ["Contact local wildlife rescue immediately"],
}


def _get_python_executable() -> str:
    """Return the Python executable for the current environment."""
    return sys.executable


async def _query_async(query: str) -> dict:
    """Connect to the MCP server via stdio, call get_wildlife_advice, and
    return the parsed JSON response."""
    python_exe = _get_python_executable()

    transport = StdioTransport(
        command=python_exe,
        args=["-m", _SERVER_MODULE],
        # Ensure the working directory is the project root so that
        # `python -m app.mcp_server` resolves correctly.
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    client = Client(transport=transport)

    async with client:
        result = await client.call_tool("get_wildlife_advice", {"animal": query})

        # FastMCP 2.x returns a CallToolResult with:
        #   .data  — the raw result string (most direct)
        #   .content — list of TextContent objects with .text
        if hasattr(result, "data") and result.data:
            return json.loads(result.data)

        # Fallback: iterate over .content list
        if hasattr(result, "content") and result.content:
            for item in result.content:
                text = getattr(item, "text", None)
                if text:
                    return json.loads(text)

        # If result is a plain string (older SDK versions)
        if isinstance(result, str):
            return json.loads(result)

    return dict(_FALLBACK_ADVICE)


def query_wildlife_advice(query: str) -> dict:
    """Synchronous entry-point for Workflow nodes.

    Spawns the MCP server as a subprocess, sends the query, and returns
    the structured advice dict.  On any failure, returns safe fallback advice
    so the calling workflow never crashes.

    Args:
        query: Natural-language description such as
               'Tiger behavior near village boundary'.

    Returns:
        A dict with keys: animal, avoid, action, emergency_tips.
    """
    try:
        # Handle the case where an event loop is already running
        # (e.g. inside an async ADK runtime).
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop — use nest_asyncio or
            # run in a separate thread to avoid blocking.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _query_async(query))
                return future.result(timeout=30)
        else:
            return asyncio.run(_query_async(query))

    except Exception:
        logger.exception("MCP Wildlife Knowledge Base query failed — using fallback")
        return dict(_FALLBACK_ADVICE)
