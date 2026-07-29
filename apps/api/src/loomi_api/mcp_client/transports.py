from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from loomi_api.config import Settings
from loomi_api.db.models import MCPServer
from loomi_api.mcp_client.protocol import (
    MCPClientError,
    mcp_headers,
    request_payload,
)
from loomi_api.mcp_client.security import (
    build_minimal_env,
    resolve_bearer_token,
    validate_remote_endpoint,
)
from loomi_api.mcp_client.templates import resolve_stdio_template


@dataclass(frozen=True)
class MCPCallResult:
    result: dict[str, Any]
    stderr_preview: str = ""


class StdioMCPTransport:
    def __init__(self, settings: Settings, server: MCPServer) -> None:
        self.settings = settings
        self.server = server
        self.process: asyncio.subprocess.Process | None = None
        self.stderr_preview = ""
        self._stderr_task: asyncio.Task[None] | None = None
        self._request_id = 0

    async def __aenter__(self) -> StdioMCPTransport:
        template = resolve_stdio_template(self.server.command_template or [])
        env = build_minimal_env(
            list(self.server.environment_allowlist or []),
            self.server.secret_ref,
        )
        self.process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                template.command,
                *template.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.server.working_directory or None,
                env=env,
                limit=max(self.settings.mcp_max_stdio_stdout_bytes, self.server.output_size_limit)
                + 1024,
                start_new_session=True,
            ),
            timeout=max(self.server.connection_timeout_seconds or 5, 1),
        )
        assert self.process.stderr is not None
        self._stderr_task = asyncio.create_task(self._drain_stderr(self.process.stderr))
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        name: str | None = None,
    ) -> MCPCallResult:
        del name
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise MCPClientError("transport_closed", "MCP stdio transport is not open.")
        self._request_id += 1
        payload = request_payload(method, params, self._request_id)
        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        if len(line.encode("utf-8")) > self.server.output_size_limit:
            raise MCPClientError("request_too_large", "MCP request exceeds configured size limit.")
        self.process.stdin.write(line.encode("utf-8") + b"\n")
        await self.process.stdin.drain()
        try:
            response = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=max(self.server.tool_timeout_seconds or 10, 1),
            )
        except TimeoutError as exc:
            await self.close(kill=True)
            raise MCPClientError("mcp_timeout", "MCP stdio request timed out.") from exc
        if not response:
            raise MCPClientError("mcp_no_response", "MCP stdio server closed without a response.")
        return MCPCallResult(result=_parse_response(response), stderr_preview=self.stderr_preview)

    async def close(self, *, kill: bool = False) -> None:
        process = self.process
        if process is None:
            return
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        try:
            if kill and process.returncode is None:
                _terminate_process_group(process)
            await asyncio.wait_for(process.wait(), timeout=0.8)
        except TimeoutError:
            _terminate_process_group(process, force=True)
            await process.wait()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
        self.process = None

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        limit = self.settings.mcp_max_stdio_stderr_bytes
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await stderr.read(1024)
            if not chunk:
                break
            if total < limit:
                remaining = max(limit - total, 0)
                chunks.append(chunk[:remaining])
                total += len(chunk[:remaining])
        self.stderr_preview = b"".join(chunks).decode("utf-8", errors="replace")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class HttpMCPTransport:
    def __init__(self, settings: Settings, server: MCPServer) -> None:
        self.settings = settings
        self.server = server
        self._request_id = 0

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        name: str | None = None,
    ) -> MCPCallResult:
        if not self.server.url:
            raise MCPClientError(
                "remote_endpoint_missing", "Remote MCP endpoint is not configured."
            )
        allow_private = bool((self.server.policy or {}).get("allow_private_networks"))
        endpoint = validate_remote_endpoint(
            self.settings,
            self.server.url,
            allow_private_networks=allow_private,
        )
        self._request_id += 1
        payload = request_payload(method, params, self._request_id)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(body) > self.server.output_size_limit:
            raise MCPClientError("request_too_large", "MCP request exceeds configured size limit.")
        headers = mcp_headers(method, name)
        token = resolve_bearer_token(self.server.secret_ref)
        if token:
            headers["authorization"] = f"Bearer {token}"
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_post_json, endpoint, headers, body, self.server),
                timeout=max(self.server.tool_timeout_seconds or 10, 1),
            )
        except TimeoutError as exc:
            raise MCPClientError("mcp_timeout", "Remote MCP request timed out.") from exc
        return MCPCallResult(result=response)


@asynccontextmanager
async def open_transport(settings: Settings, server: MCPServer) -> AsyncIterator[Any]:
    if server.transport == "stdio":
        async with StdioMCPTransport(settings, server) as transport:
            yield transport
        return
    if server.transport == "streamable_http":
        yield HttpMCPTransport(settings, server)
        return
    raise MCPClientError("unsupported_transport", "MCP transport is not supported.")


def _post_json(
    endpoint: str,
    headers: dict[str, str],
    body: bytes,
    server: MCPServer,
) -> dict[str, Any]:
    opener = build_opener(NoRedirect)
    request = Request(endpoint, data=body, headers=headers, method="POST")  # noqa: S310
    try:
        with opener.open(request, timeout=max(server.connection_timeout_seconds or 5, 1)) as resp:
            content_type = resp.headers.get("content-type", "")
            payload = resp.read(server.output_size_limit + 1)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            raise MCPClientError("redirect_blocked", "Remote MCP redirects are blocked.") from exc
        raise MCPClientError(
            "remote_mcp_http_error", f"Remote MCP returned HTTP {exc.code}."
        ) from exc
    except URLError as exc:
        raise MCPClientError(
            "remote_mcp_unreachable", "Remote MCP endpoint is unreachable."
        ) from exc
    if len(payload) > server.output_size_limit:
        raise MCPClientError("mcp_output_too_large", "Remote MCP response exceeded size limit.")
    if "text/event-stream" in content_type:
        payload = _last_sse_data(payload)
    return _parse_response(payload)


def _last_sse_data(payload: bytes) -> bytes:
    last: bytes | None = None
    for block in payload.split(b"\n\n"):
        data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith(b"data:")]
        if data_lines:
            last = b"\n".join(data_lines)
    if last is None:
        raise MCPClientError("mcp_bad_sse", "Remote MCP SSE response had no data event.")
    return last


def _parse_response(response: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MCPClientError("mcp_invalid_json", "MCP server returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise MCPClientError("mcp_invalid_json", "MCP JSON-RPC response must be an object.")
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "mcp_error")
        message = str(error.get("message") or "MCP server returned an error.")
        raise MCPClientError(code, message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise MCPClientError("mcp_invalid_result", "MCP JSON-RPC result must be an object.")
    return result


def _terminate_process_group(process: asyncio.subprocess.Process, *, force: bool = False) -> None:
    if process.returncode is not None:
        return
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        process.kill() if force else process.terminate()
