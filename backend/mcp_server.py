"""StudyPilot's MCP server: the agents' toolbox, served over the Model Context Protocol.

The Coordinator agent (agents/brain.py) does not call Python functions directly. At the start
of every run it connects to this server, discovers the tools (list_tools), hands their schemas
to Gemini, and every decision Gemini makes ("move this session", "find a free slot") becomes an
MCP `tools/call` request to this server. The server then talks to Google Calendar, Classroom,
Drive and Gmail.

Mounted inside the FastAPI app at /mcp/ (Streamable HTTP). It only accepts calls from the app
itself (localhost) or with the MCP_TOKEN bearer token, because these tools can change the
student's calendar.
"""
import functools
import inspect
import os

import anyio
from mcp.server.fastmcp import FastMCP

from agents import brain

MCP_TOKEN = os.getenv("MCP_TOKEN", "")

mcp = FastMCP(
    "studypilot",
    instructions="StudyPilot's study tools: read the student's deadlines and Calendar, plan and "
                 "move study sessions, build prep packs and notes, and message the student.",
    stateless_http=True, json_response=True, streamable_http_path="/")


def _expose(fn):
    """Register a blocking tool as an async MCP tool that runs in a worker thread
    (Google API calls must never freeze the server's event loop)."""
    @functools.wraps(fn)
    async def tool(**kwargs):
        def call():
            brain._ctx.run_id = brain.current_run()  # tool steps report to the run that asked
            try:
                return fn(**kwargs)
            finally:
                brain._ctx.run_id = None
        return await anyio.to_thread.run_sync(call)
    tool.__signature__ = inspect.signature(fn)
    mcp.add_tool(tool, name=fn.__name__, description=inspect.getdoc(fn) or fn.__name__,
                 structured_output=False)


for _fn in brain.TOOLS:
    _expose(_fn)

TOOL_NAMES = [f.__name__ for f in brain.TOOLS]
http_app = mcp.streamable_http_app()


class LocalOnly:
    """ASGI guard: the MCP endpoint is for StudyPilot's own agents (or a token holder)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            host = (scope.get("client") or ("", 0))[0]
            auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            forwarded = any(k in (b"x-forwarded-for", b"x-real-ip") for k, _ in scope.get("headers") or [])
            local = host in ("127.0.0.1", "::1", "localhost") and not forwarded
            if not (local or (MCP_TOKEN and auth == f"Bearer {MCP_TOKEN}")):
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body",
                            "body": b'{"error":"The StudyPilot MCP server only accepts calls from StudyPilot itself."}'})
                return
        await self.app(scope, receive, send)


asgi_app = LocalOnly(http_app)
