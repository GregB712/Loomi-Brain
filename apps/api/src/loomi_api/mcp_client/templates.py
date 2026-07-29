from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from loomi_api.mcp_client.protocol import MCPClientError
from loomi_api.mcp_client.security import validate_template_name


@dataclass(frozen=True)
class StdioTemplate:
    name: str
    command: str
    args: tuple[str, ...]
    description: str


def available_stdio_templates() -> list[dict[str, str]]:
    return [
        {
            "name": template.name,
            "description": template.description,
        }
        for template in _templates().values()
    ]


def resolve_stdio_template(command_template: list[str]) -> StdioTemplate:
    if not command_template:
        raise MCPClientError("invalid_template", "MCP stdio template is required.")
    name = validate_template_name(str(command_template[0]))
    template = _templates().get(name)
    if template is None:
        raise MCPClientError("invalid_template", "MCP stdio template is not allowlisted.")
    if len(command_template) > 1:
        raise MCPClientError(
            "template_arguments_forbidden",
            "This MCP stdio template does not accept browser-provided arguments.",
        )
    return template


def _templates() -> dict[str, StdioTemplate]:
    test_server = Path(__file__).with_name("test_server.py").resolve()
    return {
        "loomi-test": StdioTemplate(
            name="loomi-test",
            command=sys.executable,
            args=(str(test_server),),
            description=(
                "Harmless local MCP test server with echo, add, synthetic notes, and policy probes."
            ),
        )
    }
