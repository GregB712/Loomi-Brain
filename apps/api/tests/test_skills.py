from __future__ import annotations

import json
from typing import Any, cast

from fastapi.testclient import TestClient


def test_skill_manifest_validation_rejects_unsafe_inputs(seeded_client: TestClient) -> None:
    assert seeded_client.get("/api/v1/skills").status_code == 401
    _login(seeded_client)

    bad_structure = _manifest()
    bad_structure["metadata"]["version"] = "latest"
    bad_structure["unexpected"] = True
    structure = seeded_client.post("/api/v1/skills/validate", json={"manifest": bad_structure})
    assert structure.status_code == 200
    structure_codes = {item["code"] for item in structure.json()["errors"]}
    assert "value_error" in structure_codes
    assert "extra_forbidden" in structure_codes

    bad_policy = _manifest()
    bad_policy["spec"]["promptTemplate"] = "Inspect {{ input.__class__ }}"
    bad_policy["spec"]["allowedTools"] = ["shell.exec"]
    policy = seeded_client.post("/api/v1/skills/validate", json={"manifest": bad_policy})
    assert policy.status_code == 200
    policy_codes = {item["code"] for item in policy.json()["errors"]}
    assert "unsafe_template" in policy_codes
    assert "unsupported_tool" in policy_codes


def test_skill_create_test_publish_execute_and_immutability(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    created = _create_skill(seeded_client, csrf)
    skill_id = created["id"]
    version = created["versions"][0]

    dry_run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}/dry-run",
        headers={"x-csrf-token": csrf},
        json={"input": {"expression": "2 + 2"}},
    )
    assert dry_run.status_code == 200, dry_run.text
    dry_body = dry_run.json()
    assert dry_body["rendered_prompt"] == "Calculate 2 + 2."
    assert dry_body["allowed_tools"] == ["calculator"]
    assert dry_body["effective_limits"]["max_steps"] == 12
    assert dry_body["external_calls"] is False

    test_response = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}/tests",
        headers={"x-csrf-token": csrf},
        json={
            "name": "calculator happy path",
            "fixture": {
                "input": {"expression": "2 + 2"},
                "deterministic_model_result": {"answer_text": "Result: 4.", "citations": []},
            },
            "expected": {
                "validation_result": True,
                "output_schema_result": True,
                "policy_allowed_tools": ["calculator"],
            },
        },
    )
    assert test_response.status_code == 201, test_response.text
    test_run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}/tests:run",
        headers={"x-csrf-token": csrf},
    )
    assert test_run.status_code == 200, test_run.text
    assert test_run.json()["status"] == "passed"

    published = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}/publish",
        headers={"x-csrf-token": csrf},
    )
    assert published.status_code == 200, published.text
    published_version = published.json()["versions"][0]
    assert published_version["state"] == "published"

    immutable_manifest = _manifest()
    immutable_manifest["spec"]["promptTemplate"] = "Calculate {{ input.expression }} safely."
    changed = seeded_client.patch(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}",
        headers={"x-csrf-token": csrf},
        json={"manifest": immutable_manifest},
    )
    assert changed.status_code == 409

    run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version['id']}/execute",
        headers={"x-csrf-token": csrf, "idempotency-key": "skill-calc-once"},
        json={"input": {"expression": "2 + 2"}},
    )
    assert run.status_code == 202, run.text
    run_body = run.json()
    assert run_body["run_kind"] == "skill"
    assert run_body["state"] == "complete"
    assert run_body["allowed_tools"] == ["calculator"]
    assert run_body["trace_metadata"]["skill_id"] == skill_id
    assert run_body["trace_metadata"]["skill_version_id"] == version["id"]
    assert run_body["trace_metadata"]["skill_output_validation"]["valid"] is True


def test_skill_intersects_tools_and_global_limits(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    manifest = _manifest(
        name="strict-policy-skill",
        version="1.0.0",
        allowed_tools=["calculator", "mcp::missing::echo"],
    )
    manifest["spec"]["limits"] = {"maxSteps": 64, "maxToolCalls": 12, "timeoutSeconds": 300}
    manifest["spec"]["modelPolicy"] = {
        "capability": "reasoning",
        "maxInputTokens": 50_000,
        "maxOutputTokens": 10_000,
    }
    created = _create_skill(seeded_client, csrf, manifest)
    skill_id = created["id"]
    version_id = created["versions"][0]["id"]

    dry_run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version_id}/dry-run",
        headers={"x-csrf-token": csrf},
        json={"input": {"expression": "1 + 1"}},
    )

    assert dry_run.status_code == 200, dry_run.text
    body = dry_run.json()
    assert body["allowed_tools"] == ["calculator"]
    assert body["missing_tools"] == ["mcp::missing::echo"]
    assert body["effective_limits"]["max_steps"] == 16
    assert body["effective_limits"]["max_tool_calls"] == 3
    assert body["effective_limits"]["token_budget"] == 6000


def test_skill_import_export_never_auto_publishes_or_leaks_secrets(
    seeded_client: TestClient,
) -> None:
    csrf = _login(seeded_client)
    bundle = {
        "format": "loomi.skill.bundle.v1",
        "manifest": _manifest(name="imported-summary", version="1.0.0"),
        "tests": [
            {
                "name": "secret redaction fixture",
                "fixture": {
                    "input": {"expression": "3 + 5"},
                    "deterministic_model_result": {
                        "answer_text": "api_key=SHOULD_NOT_LEAK",
                        "citations": [],
                    },
                },
                "expected": {"output_schema_result": True},
            }
        ],
    }
    preview = seeded_client.post(
        "/api/v1/skills/import",
        headers={"x-csrf-token": csrf},
        json={"content": json.dumps(bundle), "persist": False},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["persisted"] is False
    assert preview.json()["diff"]["auto_publish"] is False
    assert preview.json()["diff"]["auto_enable_tools"] is False

    persisted = seeded_client.post(
        "/api/v1/skills/import",
        headers={"x-csrf-token": csrf},
        json={"content": json.dumps(bundle), "persist": True},
    )
    assert persisted.status_code == 200, persisted.text
    skill = persisted.json()["skill"]
    version = skill["versions"][0]
    assert skill["state"] == "draft"
    assert version["state"] == "draft"

    exported = seeded_client.get(
        f"/api/v1/skills/{skill['id']}/versions/{version['id']}/export?include_tests=false"
    )
    assert exported.status_code == 200, exported.text
    serialized = json.dumps(exported.json(), sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert exported.json()["tests"] == []

    malformed = seeded_client.post(
        "/api/v1/skills/import",
        headers={"x-csrf-token": csrf},
        json={"content": "!!python/object/apply:os.system []", "persist": True},
    )
    assert malformed.status_code == 422


def test_skill_output_schema_failure_marks_run_failed(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    manifest = _manifest(name="strict-output", version="1.0.0")
    manifest["spec"]["outputSchema"] = {
        "type": "object",
        "properties": {"required_field": {"type": "string"}},
        "required": ["required_field"],
        "additionalProperties": True,
    }
    created = _create_skill(seeded_client, csrf, manifest)
    skill_id = created["id"]
    version_id = created["versions"][0]["id"]
    published = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version_id}/publish",
        headers={"x-csrf-token": csrf},
    )
    assert published.status_code == 200, published.text

    run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version_id}/execute",
        headers={"x-csrf-token": csrf, "idempotency-key": "skill-output-fails"},
        json={"input": {"expression": "2 + 3"}},
    )

    assert run.status_code == 202, run.text
    body = run.json()
    assert body["state"] == "failed"
    assert body["status_reason"] == "skill_output_schema_failed"
    assert body["trace_metadata"]["skill_output_validation"]["valid"] is False


def test_disabled_skill_version_cannot_execute(seeded_client: TestClient) -> None:
    csrf = _login(seeded_client)
    created = _create_skill(seeded_client, csrf, _manifest(name="disable-me", version="1.0.0"))
    skill_id = created["id"]
    version_id = created["versions"][0]["id"]
    assert (
        seeded_client.post(
            f"/api/v1/skills/{skill_id}/versions/{version_id}/publish",
            headers={"x-csrf-token": csrf},
        ).status_code
        == 200
    )
    assert (
        seeded_client.post(
            f"/api/v1/skills/{skill_id}/versions/{version_id}/disable",
            headers={"x-csrf-token": csrf},
        ).status_code
        == 200
    )

    run = seeded_client.post(
        f"/api/v1/skills/{skill_id}/versions/{version_id}/execute",
        headers={"x-csrf-token": csrf},
        json={"input": {"expression": "1 + 1"}},
    )
    assert run.status_code == 409


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.test", "password": "phase1-owner-password"},
    )
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def _create_skill(
    client: TestClient,
    csrf: str,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/skills",
        headers={"x-csrf-token": csrf},
        json={"manifest": manifest or _manifest()},
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _manifest(
    *,
    name: str = "calculator-skill",
    version: str = "1.0.0",
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "apiVersion": "loomi.dev/v1",
        "kind": "Skill",
        "metadata": {
            "name": name,
            "version": version,
            "description": "Calculate a synthetic expression.",
        },
        "spec": {
            "inputSchema": {
                "type": "object",
                "properties": {"expression": {"type": "string", "minLength": 1, "maxLength": 120}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "answer_text": {"type": "string", "maxLength": 2000},
                    "citations": {"type": "array", "maxItems": 10},
                },
                "required": ["answer_text"],
                "additionalProperties": True,
            },
            "promptTemplate": "Calculate {{ input.expression }}.",
            "retrievalPolicy": {"mode": "none", "topK": 0},
            "allowedTools": allowed_tools if allowed_tools is not None else ["calculator"],
            "approvalPolicy": {"mode": "runtime"},
            "modelPolicy": {
                "capability": "reasoning",
                "maxInputTokens": 12000,
                "maxOutputTokens": 2000,
            },
            "limits": {"maxSteps": 6, "maxToolCalls": 3, "timeoutSeconds": 120},
        },
    }
