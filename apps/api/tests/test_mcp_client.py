from __future__ import annotations

import asyncio
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from loomi_api.db.models import MCPCapability
from loomi_api.db.session import create_engine, create_sessionmaker


def test_mcp_registry_requires_owner_and_rejects_dangerous_config(
    seeded_client: TestClient,
) -> None:
    assert seeded_client.get("/api/v1/mcp/servers").status_code == 401
    csrf = _login(seeded_client)

    bad_template = seeded_client.post(
        "/api/v1/mcp/servers",
        headers={"x-csrf-token": csrf},
        json={
            "name": "bad stdio",
            "transport": "stdio",
            "template_name": "loomi-test;rm -rf",
        },
    )
    assert bad_template.status_code == 422

    ssrf = seeded_client.post(
        "/api/v1/mcp/servers",
        headers={"x-csrf-token": csrf},
        json={
            "name": "metadata",
            "transport": "streamable_http",
            "url": "http://169.254.169.254/latest/meta-data",
        },
    )
    assert ssrf.status_code == 422


def test_mcp_capabilities_are_default_deny_then_read_only_tool_runs(
    seeded_client: TestClient,
) -> None:
    csrf = _login(seeded_client)
    server = _create_test_server(seeded_client, csrf)
    refreshed = _refresh(seeded_client, csrf, server["id"])
    echo = _capability(refreshed, "tool", "echo")
    forbidden = _capability(refreshed, "tool", "forbidden_shell")
    unsafe_prompt = _capability(refreshed, "prompt", "unsafe_prompt")

    assert echo["enabled"] is False
    assert forbidden["enabled"] is False
    assert unsafe_prompt["enabled"] is False

    blocked = _invoke(seeded_client, csrf, server["id"], echo["id"], {"text": "hello"})
    assert blocked["state"] == "failed"
    assert blocked["status_reason"] == "tool_not_found"

    enabled = _policy(
        seeded_client,
        csrf,
        echo["id"],
        enabled=True,
        risk_class="read-only",
        approval_policy="never",
    )
    assert enabled["enabled"] is True
    assert enabled["risk_class"] == "read-only"

    run = _invoke(seeded_client, csrf, server["id"], echo["id"], {"text": "hello"})
    assert run["state"] == "complete"
    assert run["tool_calls"][0]["status"] == "succeeded"
    serialized = str(run)
    assert "untrusted_mcp_result" in serialized
    assert "hello" in serialized

    audit = seeded_client.get("/api/v1/mcp/audit?limit=20")
    assert audit.status_code == 200
    assert any(item["event_type"] == "mcp.tool_executed" for item in audit.json()["items"])


def test_mcp_risky_tool_requires_approval_and_schema_change_invalidates_it(
    seeded_client: TestClient,
) -> None:
    csrf = _login(seeded_client)
    server = _create_test_server(seeded_client, csrf)
    refreshed = _refresh(seeded_client, csrf, server["id"])
    risky = _capability(refreshed, "tool", "risky_write")
    _policy(
        seeded_client,
        csrf,
        risky["id"],
        enabled=True,
        risk_class="external-mutation",
        approval_policy="risk-based",
    )

    pending = _invoke(
        seeded_client,
        csrf,
        server["id"],
        risky["id"],
        {"target": "synthetic"},
    )
    assert pending["state"] == "request_tool_approval"
    approval = pending["approvals"][0]
    assert approval["risk_class"] == "external-mutation"

    asyncio.run(_change_schema_hash(seeded_client, risky["id"]))
    approved = seeded_client.post(
        f"/api/v1/agent-runs/{pending['id']}/approvals/{approval['id']}/approve",
        headers={"x-csrf-token": csrf},
        json={},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["state"] == "failed"
    assert body["status_reason"] == "approval_arguments_changed"


def test_mcp_output_limits_and_environment_minimization(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    server = _create_test_server(seeded_client, csrf)
    refreshed = _refresh(seeded_client, csrf, server["id"])
    narrowed = seeded_client.patch(
        f"/api/v1/mcp/servers/{server['id']}",
        headers={"x-csrf-token": csrf},
        json={"output_size_limit": 512},
    )
    assert narrowed.status_code == 200
    large = _capability(refreshed, "tool", "large_output")
    env_probe = _capability(refreshed, "tool", "env_probe")
    _policy(
        seeded_client,
        csrf,
        large["id"],
        enabled=True,
        risk_class="read-only",
        approval_policy="never",
    )
    _policy(
        seeded_client,
        csrf,
        env_probe["id"],
        enabled=True,
        risk_class="read-only",
        approval_policy="never",
    )

    large_run = _invoke(seeded_client, csrf, server["id"], large["id"], {})
    assert large_run["state"] == "complete"
    assert "truncated" in str(large_run["tool_calls"][0]["redacted_result"])

    env_run = _invoke(seeded_client, csrf, server["id"], env_probe["id"], {})
    assert env_run["state"] == "complete"
    serialized = str(env_run["tool_calls"][0]["redacted_result"])
    assert "LOOMI_OWNER_PASSWORD" not in serialized
    assert "phase1-owner-password" not in serialized


def test_mcp_secret_refs_are_not_returned_to_browser(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    plaintext = seeded_client.post(
        "/api/v1/mcp/servers",
        headers={"x-csrf-token": csrf},
        json={
            "name": "bad-secret",
            "transport": "stdio",
            "template_name": "loomi-test",
            "secret_ref": "plain-secret-value",
        },
    )
    assert plaintext.status_code == 422

    response = seeded_client.post(
        "/api/v1/mcp/servers",
        headers={"x-csrf-token": csrf},
        json={
            "name": "secret-ref",
            "transport": "stdio",
            "template_name": "loomi-test",
            "secret_ref": "env:LOOMI_MCP_TOKEN",
            "environment_allowlist": ["LOOMI_MCP_TOKEN"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["has_secret_ref"] is True
    assert "secret_ref" not in body
    assert "LOOMI_MCP_TOKEN" not in str(body["capability_cache"])


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _create_test_server(
    client: TestClient,
    csrf: str,
    *,
    output_size_limit: int = 12_000,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/mcp/servers",
        headers={"x-csrf-token": csrf},
        json={
            "name": "Loomi test MCP",
            "transport": "stdio",
            "template_name": "loomi-test",
            "output_size_limit": output_size_limit,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _refresh(client: TestClient, csrf: str, server_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/mcp/servers/{server_id}/refresh-capabilities",
        headers={"x-csrf-token": csrf},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _policy(
    client: TestClient,
    csrf: str,
    capability_id: str,
    *,
    enabled: bool,
    risk_class: str,
    approval_policy: str,
) -> dict[str, Any]:
    response = client.patch(
        f"/api/v1/mcp/capabilities/{capability_id}/policy",
        headers={"x-csrf-token": csrf},
        json={
            "enabled": enabled,
            "risk_class": risk_class,
            "approval_policy": approval_policy,
            "confirm_broadening": True,
            "expected_side_effects": "Synthetic test only.",
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _invoke(
    client: TestClient,
    csrf: str,
    server_id: str,
    capability_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/mcp/servers/{server_id}/capabilities/{capability_id}/invoke",
        headers={"x-csrf-token": csrf},
        json={"arguments": arguments},
    )
    assert response.status_code == 202, response.text
    return cast(dict[str, Any], response.json())


def _capability(payload: dict[str, Any], capability_type: str, name: str) -> dict[str, Any]:
    for item in payload["capabilities"]:
        if item["capability_type"] == capability_type and item["name"] == name:
            return cast(dict[str, Any], item)
    raise AssertionError(f"Missing capability {capability_type}:{name}")


async def _change_schema_hash(client: TestClient, capability_id: str) -> None:
    settings = cast(Any, client.app).state.settings
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as session:
        capability = await session.scalar(
            select(MCPCapability).where(MCPCapability.id == capability_id)
        )
        assert capability is not None
        capability.schema_hash = "changed-schema-hash"
        await session.commit()
    await engine.dispose()
