from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loomi_api.agent_runtime.contracts import AgentRunLimits, AgentRunRequest
from loomi_api.agent_runtime.policy import sanitize_value
from loomi_api.agent_runtime.runtime import AgentRuntimeService
from loomi_api.agent_runtime.tools import default_tool_registry
from loomi_api.config import Settings
from loomi_api.db.base import utc_now
from loomi_api.db.models import (
    AgentEvent,
    AgentRun,
    AuditEvent,
    MCPCapability,
    MCPServer,
    Skill,
    SkillTest,
    SkillTestRun,
    SkillVersion,
)
from loomi_api.mcp_client.protocol import canonical_mcp_tool_id
from loomi_api.skills.builtins import starter_skill_manifests
from loomi_api.skills.manifest import (
    ManifestValidationResult,
    SkillManifest,
    synthetic_input_for_schema,
    validate_json_data,
    validate_manifest,
)
from loomi_api.skills.renderer import TemplateSecurityError, render_template

IMPORT_FORMAT = "loomi.skill.bundle.v1"
MAX_IMPORT_BYTES = 160_000


class SkillServiceError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class SkillService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        owner_user_id: str,
        request_id: str,
        trace_id: str,
    ) -> None:
        self.session = session
        self.settings = settings
        self.owner_user_id = owner_user_id
        self.request_id = request_id
        self.trace_id = trace_id

    async def starter_templates(self) -> dict[str, Any]:
        validation = [
            validate_manifest(manifest, runtime_tool_ids=await self.runtime_tool_ids()).as_dict()
            for manifest in starter_skill_manifests()
        ]
        return {
            "items": [
                {
                    "manifest": manifest,
                    "validation": validation[index],
                }
                for index, manifest in enumerate(starter_skill_manifests())
            ]
        }

    async def validate_manifest_payload(self, manifest: dict[str, Any]) -> dict[str, Any]:
        result = validate_manifest(manifest, runtime_tool_ids=await self.runtime_tool_ids())
        return result.as_dict()

    async def list_skills(
        self,
        *,
        state: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        filters = [Skill.owner_user_id == self.owner_user_id]
        if state:
            filters.append(Skill.state == state)
        total = int(await self.session.scalar(select(func.count(Skill.id)).where(*filters)) or 0)
        rows = list(
            await self.session.scalars(
                select(Skill)
                .where(*filters)
                .order_by(desc(Skill.updated_at))
                .offset(offset)
                .limit(limit)
            )
        )
        return {
            "items": [await self.serialize_skill_summary(skill) for skill in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_skill(self, skill_id: str) -> dict[str, Any]:
        skill = await self._load_skill(skill_id)
        versions = list(
            await self.session.scalars(
                select(SkillVersion)
                .where(
                    SkillVersion.skill_id == skill.id,
                    SkillVersion.owner_user_id == self.owner_user_id,
                )
                .order_by(desc(SkillVersion.created_at))
            )
        )
        return {
            **await self.serialize_skill_summary(skill),
            "versions": [await self.serialize_version(version) for version in versions],
        }

    async def create_skill(
        self,
        manifest: dict[str, Any],
        *,
        provenance: dict[str, Any] | None = None,
        tests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        validation = await self._validate_or_raise(manifest)
        parsed = SkillManifest.model_validate(validation.canonical_manifest)
        existing = await self._find_skill(parsed.metadata.name)
        if existing is None:
            skill = Skill(
                owner_user_id=self.owner_user_id,
                name=parsed.metadata.name,
                normalized_name=parsed.metadata.name,
                description=parsed.metadata.description,
                state="draft",
                provenance=provenance or {"source": "editor"},
            )
            self.session.add(skill)
            await self.session.flush()
        else:
            skill = existing
            duplicate = await self._find_version(skill.id, parsed.metadata.version)
            if duplicate is not None:
                raise SkillServiceError(
                    "duplicate_skill_version",
                    "A skill version with this name and SemVer already exists.",
                )
        version = SkillVersion(
            skill_id=skill.id,
            owner_user_id=self.owner_user_id,
            version=parsed.metadata.version,
            manifest=validation.canonical_manifest or manifest,
            canonical_manifest=validation.canonical_manifest or manifest,
            manifest_checksum=validation.checksum or "",
            state="draft",
            validation_results=validation.as_dict(),
            provenance=provenance or {"source": "editor"},
        )
        self.session.add(version)
        await self.session.flush()
        skill.current_version_id = version.id
        skill.state = "draft"
        if tests:
            for item in tests[:50]:
                self.session.add(
                    SkillTest(
                        skill_id=skill.id,
                        skill_version_id=version.id,
                        owner_user_id=self.owner_user_id,
                        name=str(item.get("name") or "Imported test")[:120],
                        fixture=cast(dict[str, Any], item.get("fixture") or {}),
                        expected=cast(dict[str, Any], item.get("expected") or {}),
                        test_metadata={"source": "import"},
                    )
                )
        await self._audit(
            "skill.version_created",
            {"skill_id": skill.id, "version_id": version.id, "version": version.version},
        )
        await self.session.commit()
        return await self.get_skill(skill.id)

    async def update_draft_version(
        self,
        skill_id: str,
        version_id: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        if version.state != "draft" or version.published_at is not None:
            raise SkillServiceError(
                "published_immutable", "Published skill versions are immutable."
            )
        validation = await self._validate_or_raise(manifest)
        parsed = SkillManifest.model_validate(validation.canonical_manifest)
        if parsed.metadata.name != skill.normalized_name:
            raise SkillServiceError("skill_name_mismatch", "Draft updates cannot rename a skill.")
        existing = await self._find_version(skill.id, parsed.metadata.version)
        if existing is not None and existing.id != version.id:
            raise SkillServiceError(
                "duplicate_skill_version",
                "A skill version with this SemVer already exists.",
            )
        version.version = parsed.metadata.version
        version.manifest = validation.canonical_manifest or manifest
        version.canonical_manifest = validation.canonical_manifest or manifest
        version.manifest_checksum = validation.checksum or ""
        version.validation_results = validation.as_dict()
        skill.description = parsed.metadata.description
        await self._audit(
            "skill.version_updated",
            {"skill_id": skill.id, "version_id": version.id, "version": version.version},
        )
        await self.session.commit()
        return await self.get_skill(skill.id)

    async def publish_version(self, skill_id: str, version_id: str) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        if version.state != "draft":
            raise SkillServiceError("invalid_lifecycle", "Only draft skill versions can publish.")
        validation = await self._validate_or_raise(version.canonical_manifest or version.manifest)
        version.state = "published"
        version.published_at = utc_now()
        version.publication_metadata = {
            "published_by_user_id": self.owner_user_id,
            "checksum": validation.checksum,
        }
        version.validation_results = validation.as_dict()
        skill.state = "published"
        skill.current_version_id = version.id
        await self._audit(
            "skill.version_published",
            {"skill_id": skill.id, "version_id": version.id, "checksum": version.manifest_checksum},
        )
        await self.session.commit()
        return await self.get_skill(skill.id)

    async def set_version_state(
        self,
        skill_id: str,
        version_id: str,
        *,
        state: str,
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        if state not in {"archived", "disabled"}:
            raise SkillServiceError("invalid_lifecycle", "Unsupported lifecycle transition.")
        version.state = state
        if state == "archived":
            version.archived_at = utc_now()
        else:
            version.disabled_at = utc_now()
        if skill.current_version_id == version.id:
            skill.state = state
        await self._audit(
            f"skill.version_{state}",
            {"skill_id": skill.id, "version_id": version.id},
        )
        await self.session.commit()
        return await self.get_skill(skill.id)

    async def clone_version(
        self,
        skill_id: str,
        version_id: str,
        *,
        new_version: str,
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        manifest = dict(version.canonical_manifest or version.manifest)
        metadata = dict(cast(dict[str, Any], manifest["metadata"]))
        metadata["version"] = new_version
        manifest["metadata"] = metadata
        validation = await self._validate_or_raise(manifest)
        if await self._find_version(skill.id, new_version) is not None:
            raise SkillServiceError("duplicate_skill_version", "The target version already exists.")
        clone = SkillVersion(
            skill_id=skill.id,
            owner_user_id=self.owner_user_id,
            version=new_version,
            manifest=validation.canonical_manifest or manifest,
            canonical_manifest=validation.canonical_manifest or manifest,
            manifest_checksum=validation.checksum or "",
            state="draft",
            parent_version_id=version.id,
            validation_results=validation.as_dict(),
            provenance={"source": "clone", "parent_version_id": version.id},
        )
        self.session.add(clone)
        await self.session.flush()
        skill.current_version_id = clone.id
        skill.state = "draft"
        await self._audit(
            "skill.version_cloned",
            {"skill_id": skill.id, "source_version_id": version.id, "version_id": clone.id},
        )
        await self.session.commit()
        return await self.get_skill(skill.id)

    async def dry_run_version(
        self,
        skill_id: str,
        version_id: str,
        *,
        input_payload: dict[str, Any] | None,
        mocked_retrieval: dict[str, Any] | None = None,
        mocked_tools: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        manifest = SkillManifest.model_validate(version.canonical_manifest or version.manifest)
        input_data = input_payload or synthetic_input_for_schema(manifest.spec.inputSchema)
        input_errors = validate_json_data(input_data, manifest.spec.inputSchema, path="$.input")
        if input_errors:
            raise SkillServiceError(
                "invalid_skill_input",
                f"Skill input failed validation: {[issue.as_dict() for issue in input_errors]}",
            )
        rendered = self._render(manifest, input_data, mocked_retrieval, mocked_tools)
        effective = await self.effective_policy(manifest)
        preview = {
            "skill_id": skill.id,
            "version_id": version.id,
            "version": version.version,
            "checksum": version.manifest_checksum,
            "rendered_prompt": rendered,
            "input": input_data,
            "retrieval_policy": manifest.spec.retrievalPolicy.model_dump(mode="json"),
            "requested_tools": list(manifest.spec.allowedTools),
            "allowed_tools": effective["allowed_tools"],
            "missing_tools": effective["missing_tools"],
            "effective_limits": effective["limits"],
            "model_policy": effective["model_policy"],
            "approval_requirements": effective["approval_requirements"],
            "external_calls": False,
        }
        await self._audit(
            "skill.dry_run",
            {
                "skill_id": skill.id,
                "version_id": version.id,
                "missing_tools": effective["missing_tools"],
            },
        )
        await self.session.commit()
        return preview

    async def execute_version(
        self,
        skill_id: str,
        version_id: str,
        *,
        input_payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        if version.state != "published" or version.published_at is None:
            raise SkillServiceError(
                "skill_not_executable",
                "Only published skill versions can execute.",
            )
        manifest = SkillManifest.model_validate(version.canonical_manifest or version.manifest)
        input_errors = validate_json_data(input_payload, manifest.spec.inputSchema, path="$.input")
        if input_errors:
            raise SkillServiceError(
                "invalid_skill_input",
                f"Skill input failed validation: {[issue.as_dict() for issue in input_errors]}",
            )
        rendered = self._render(manifest, input_payload, None, None)
        effective = await self.effective_policy(manifest)
        runtime = AgentRuntimeService(session=self.session, settings=self.settings)
        run = await runtime.start(
            AgentRunRequest(
                owner_user_id=self.owner_user_id,
                owner_request=rendered,
                request_id=self.request_id,
                trace_id=self.trace_id,
                idempotency_key=idempotency_key,
                allowed_tools=tuple(effective["allowed_tools"]),
                limits=AgentRunLimits.from_mapping(effective["limits"]),
                run_kind="skill",
                trace_metadata={
                    "skill_id": skill.id,
                    "skill_version_id": version.id,
                    "skill_version": version.version,
                    "skill_checksum": version.manifest_checksum,
                },
            )
        )
        await self._validate_runtime_output(version, manifest, str(run["id"]))
        await self._audit(
            "skill.executed",
            {
                "skill_id": skill.id,
                "version_id": version.id,
                "run_id": run["id"],
                "allowed_tools": effective["allowed_tools"],
            },
        )
        await self.session.commit()
        return await runtime.detail(self.owner_user_id, str(run["id"]))

    async def list_tests(self, skill_id: str, version_id: str) -> dict[str, Any]:
        await self._load_pair(skill_id, version_id)
        tests = list(
            await self.session.scalars(
                select(SkillTest)
                .where(
                    SkillTest.skill_version_id == version_id,
                    SkillTest.owner_user_id == self.owner_user_id,
                )
                .order_by(SkillTest.created_at)
            )
        )
        return {"items": [self.serialize_test(test) for test in tests]}

    async def create_test(
        self,
        skill_id: str,
        version_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self._load_pair(skill_id, version_id)
        test = SkillTest(
            skill_id=skill_id,
            skill_version_id=version_id,
            owner_user_id=self.owner_user_id,
            name=str(payload.get("name") or "Skill test")[:120],
            fixture=cast(dict[str, Any], payload.get("fixture") or {}),
            expected=cast(dict[str, Any], payload.get("expected") or {}),
            test_metadata={"source": "editor"},
        )
        self.session.add(test)
        await self._audit("skill.test_created", {"skill_id": skill_id, "version_id": version_id})
        await self.session.commit()
        return self.serialize_test(test)

    async def update_test(
        self,
        skill_id: str,
        version_id: str,
        test_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        test = await self._load_test(skill_id, version_id, test_id)
        if "name" in payload:
            test.name = str(payload["name"])[:120]
        if "fixture" in payload:
            test.fixture = cast(dict[str, Any], payload["fixture"])
        if "expected" in payload:
            test.expected = cast(dict[str, Any], payload["expected"])
        await self._audit("skill.test_updated", {"skill_id": skill_id, "version_id": version_id})
        await self.session.commit()
        return self.serialize_test(test)

    async def delete_test(self, skill_id: str, version_id: str, test_id: str) -> None:
        test = await self._load_test(skill_id, version_id, test_id)
        await self.session.delete(test)
        await self._audit("skill.test_deleted", {"skill_id": skill_id, "version_id": version_id})
        await self.session.commit()

    async def run_tests(self, skill_id: str, version_id: str) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        manifest = SkillManifest.model_validate(version.canonical_manifest or version.manifest)
        tests = list(
            await self.session.scalars(
                select(SkillTest).where(
                    SkillTest.skill_version_id == version.id,
                    SkillTest.owner_user_id == self.owner_user_id,
                )
            )
        )
        results = []
        for test in tests:
            results.append(await self._run_one_test(manifest, test))
        status = "passed" if all(item["passed"] for item in results) else "failed"
        run = SkillTestRun(
            skill_id=skill.id,
            skill_version_id=version.id,
            owner_user_id=self.owner_user_id,
            status=status,
            results={"items": results, "deterministic": True},
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        self.session.add(run)
        await self._audit(
            "skill.tests_run",
            {"skill_id": skill.id, "version_id": version.id, "status": status},
        )
        await self.session.commit()
        return self.serialize_test_run(run)

    async def import_bundle(self, content: str, *, persist: bool) -> dict[str, Any]:
        if len(content.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise SkillServiceError("import_too_large", "Skill import exceeds the size limit.")
        try:
            bundle = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SkillServiceError("malformed_import", "Skill import must be valid JSON.") from exc
        if not isinstance(bundle, dict):
            raise SkillServiceError("malformed_import", "Skill import root must be an object.")
        if bundle.get("format") != IMPORT_FORMAT:
            raise SkillServiceError("unsupported_import_format", "Unsupported skill import format.")
        manifest = bundle.get("manifest")
        if not isinstance(manifest, dict):
            raise SkillServiceError("malformed_import", "Skill import manifest must be an object.")
        tests = bundle.get("tests", [])
        if tests is None:
            tests = []
        if not isinstance(tests, list):
            raise SkillServiceError("malformed_import", "Skill import tests must be an array.")
        validation = validate_manifest(manifest, runtime_tool_ids=await self.runtime_tool_ids())
        existing = None
        if validation.normalized_name:
            existing = await self._find_skill(validation.normalized_name)
        diff = await self._import_diff(validation, existing)
        response = {
            "persisted": False,
            "validation": validation.as_dict(),
            "diff": diff,
            "requested_permissions": validation.permissions_summary,
        }
        if persist:
            created = await self.create_skill(
                manifest,
                provenance={"source": "import", "format": IMPORT_FORMAT},
                tests=[cast(dict[str, Any], item) for item in tests if isinstance(item, dict)],
            )
            response["persisted"] = True
            response["skill"] = created
        return response

    async def export_version(
        self,
        skill_id: str,
        version_id: str,
        *,
        include_tests: bool,
    ) -> dict[str, Any]:
        skill, version = await self._load_pair(skill_id, version_id)
        tests: list[dict[str, Any]] = []
        if include_tests:
            rows = list(
                await self.session.scalars(
                    select(SkillTest).where(
                        SkillTest.skill_version_id == version.id,
                        SkillTest.owner_user_id == self.owner_user_id,
                    )
                )
            )
            tests = [
                {
                    "name": test.name,
                    "fixture": sanitize_value(test.fixture),
                    "expected": sanitize_value(test.expected),
                }
                for test in rows
            ]
        await self._audit(
            "skill.version_exported",
            {"skill_id": skill.id, "version_id": version.id, "include_tests": include_tests},
        )
        await self.session.commit()
        return {
            "format": IMPORT_FORMAT,
            "manifest": version.canonical_manifest or version.manifest,
            "checksum": version.manifest_checksum,
            "provenance": {
                "exported_at": utc_now().isoformat(),
                "skill_id": skill.id,
                "version_id": version.id,
                "include_tests": include_tests,
            },
            "tests": tests,
        }

    async def diff_versions(
        self,
        skill_id: str,
        from_version_id: str,
        to_version_id: str,
    ) -> dict[str, Any]:
        _, from_version = await self._load_pair(skill_id, from_version_id)
        _, to_version = await self._load_pair(skill_id, to_version_id)
        left = from_version.canonical_manifest or from_version.manifest
        right = to_version.canonical_manifest or to_version.manifest
        keys = sorted(set(left) | set(right))
        changes = [
            {"path": key, "before": left.get(key), "after": right.get(key)}
            for key in keys
            if left.get(key) != right.get(key)
        ]
        return {
            "from_version_id": from_version.id,
            "to_version_id": to_version.id,
            "changes": changes,
        }

    async def effective_policy(self, manifest: SkillManifest) -> dict[str, Any]:
        runtime_tools = await self.runtime_tool_details()
        requested = list(dict.fromkeys(manifest.spec.allowedTools))
        allowed = [tool_id for tool_id in requested if tool_id in runtime_tools]
        missing = [tool_id for tool_id in requested if tool_id not in runtime_tools]
        return {
            "allowed_tools": allowed,
            "missing_tools": missing,
            "approval_requirements": [
                runtime_tools[tool_id] for tool_id in allowed if tool_id in runtime_tools
            ],
            "limits": self._effective_limits(manifest),
            "model_policy": self._effective_model_policy(manifest),
        }

    async def runtime_tool_ids(self) -> set[str]:
        return set((await self.runtime_tool_details()).keys())

    async def runtime_tool_details(self) -> dict[str, dict[str, Any]]:
        registry = default_tool_registry()
        details: dict[str, dict[str, Any]] = {}
        for tool_id in registry.ids():
            tool = registry.get(tool_id)
            if tool is None:
                continue
            details[tool_id] = {
                "tool_id": tool_id,
                "risk_class": tool.risk_class,
                "approval_policy": tool.approval_policy,
                "requires_approval": tool.approval_policy == "always"
                or tool.risk_class != "read-only",
                "source": "builtin",
            }
        rows = await self.session.execute(
            select(MCPCapability, MCPServer)
            .join(MCPServer, MCPServer.id == MCPCapability.server_id)
            .where(
                MCPCapability.owner_user_id == self.owner_user_id,
                MCPCapability.capability_type == "tool",
                MCPCapability.enabled.is_(True),
                MCPServer.disabled_at.is_(None),
            )
        )
        for capability, _server in rows:
            cap = cast(MCPCapability, capability)
            tool_id = canonical_mcp_tool_id(cap.server_id, cap.name)
            details[tool_id] = {
                "tool_id": tool_id,
                "risk_class": cap.risk_class,
                "approval_policy": cap.approval_policy,
                "requires_approval": cap.approval_policy == "always"
                or cap.risk_class != "read-only",
                "source": "mcp",
                "schema_hash": cap.schema_hash,
            }
        return details

    async def serialize_skill_summary(self, skill: Skill) -> dict[str, Any]:
        current = None
        if skill.current_version_id:
            current = await self.session.scalar(
                select(SkillVersion).where(
                    SkillVersion.id == skill.current_version_id,
                    SkillVersion.owner_user_id == self.owner_user_id,
                )
            )
        return {
            "id": skill.id,
            "name": skill.name,
            "normalized_name": skill.normalized_name,
            "description": skill.description,
            "state": skill.state,
            "current_version_id": skill.current_version_id,
            "current_version": current.version if current else None,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
            "provenance": skill.provenance,
        }

    async def serialize_version(self, version: SkillVersion) -> dict[str, Any]:
        test_count = int(
            await self.session.scalar(
                select(func.count(SkillTest.id)).where(SkillTest.skill_version_id == version.id)
            )
            or 0
        )
        return {
            "id": version.id,
            "skill_id": version.skill_id,
            "version": version.version,
            "state": version.state,
            "manifest": version.canonical_manifest or version.manifest,
            "checksum": version.manifest_checksum,
            "parent_version_id": version.parent_version_id,
            "validation_results": version.validation_results,
            "publication_metadata": version.publication_metadata,
            "provenance": version.provenance,
            "test_count": test_count,
            "created_at": version.created_at.isoformat(),
            "updated_at": version.updated_at.isoformat(),
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "archived_at": version.archived_at.isoformat() if version.archived_at else None,
            "disabled_at": version.disabled_at.isoformat() if version.disabled_at else None,
        }

    def serialize_test(self, test: SkillTest) -> dict[str, Any]:
        return {
            "id": test.id,
            "skill_id": test.skill_id,
            "skill_version_id": test.skill_version_id,
            "name": test.name,
            "fixture": test.fixture,
            "expected": test.expected,
            "metadata": test.test_metadata,
            "created_at": test.created_at.isoformat(),
            "updated_at": test.updated_at.isoformat(),
        }

    def serialize_test_run(self, run: SkillTestRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "skill_id": run.skill_id,
            "skill_version_id": run.skill_version_id,
            "status": run.status,
            "results": run.results,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        }

    async def _validate_or_raise(self, manifest: dict[str, Any]) -> ManifestValidationResult:
        validation = validate_manifest(manifest, runtime_tool_ids=await self.runtime_tool_ids())
        if not validation.valid:
            error_payload = [issue.as_dict() for issue in validation.errors]
            raise SkillServiceError(
                "invalid_skill_manifest",
                f"Skill manifest failed validation: {error_payload}",
            )
        return validation

    async def _load_skill(self, skill_id: str) -> Skill:
        skill = await self.session.scalar(
            select(Skill).where(Skill.id == skill_id, Skill.owner_user_id == self.owner_user_id)
        )
        if skill is None:
            raise SkillServiceError("skill_not_found", "Skill not found.")
        return skill

    async def _load_pair(self, skill_id: str, version_id: str) -> tuple[Skill, SkillVersion]:
        row = (
            await self.session.execute(
                select(Skill, SkillVersion)
                .join(SkillVersion, SkillVersion.skill_id == Skill.id)
                .where(
                    Skill.id == skill_id,
                    Skill.owner_user_id == self.owner_user_id,
                    SkillVersion.id == version_id,
                    SkillVersion.owner_user_id == self.owner_user_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise SkillServiceError("skill_version_not_found", "Skill version not found.")
        return cast(tuple[Skill, SkillVersion], row)

    async def _load_test(self, skill_id: str, version_id: str, test_id: str) -> SkillTest:
        await self._load_pair(skill_id, version_id)
        test = await self.session.scalar(
            select(SkillTest).where(
                SkillTest.id == test_id,
                SkillTest.skill_id == skill_id,
                SkillTest.skill_version_id == version_id,
                SkillTest.owner_user_id == self.owner_user_id,
            )
        )
        if test is None:
            raise SkillServiceError("skill_test_not_found", "Skill test not found.")
        return test

    async def _find_skill(self, normalized_name: str) -> Skill | None:
        return cast(
            Skill | None,
            await self.session.scalar(
                select(Skill).where(
                    Skill.owner_user_id == self.owner_user_id,
                    Skill.normalized_name == normalized_name,
                )
            ),
        )

    async def _find_version(self, skill_id: str, version: str) -> SkillVersion | None:
        return cast(
            SkillVersion | None,
            await self.session.scalar(
                select(SkillVersion).where(
                    SkillVersion.skill_id == skill_id,
                    SkillVersion.owner_user_id == self.owner_user_id,
                    SkillVersion.version == version,
                )
            ),
        )

    def _render(
        self,
        manifest: SkillManifest,
        input_payload: dict[str, Any],
        mocked_retrieval: dict[str, Any] | None,
        mocked_tools: dict[str, Any] | None,
    ) -> str:
        context = {
            "input": input_payload,
            "retrieval": mocked_retrieval or {"results": [], "summary": "dry-run"},
            "tools": mocked_tools or {"results": {}},
            "skill": manifest.metadata.model_dump(mode="json"),
        }
        try:
            return render_template(manifest.spec.promptTemplate, context)
        except TemplateSecurityError as exc:
            raise SkillServiceError("unsafe_template", str(exc)) from exc

    async def _validate_runtime_output(
        self,
        version: SkillVersion,
        manifest: SkillManifest,
        run_id: str,
    ) -> None:
        run = await self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.owner_user_id == self.owner_user_id,
            )
        )
        if run is None or run.state != "complete":
            return
        output = run.sanitized_output or {}
        issues = validate_json_data(output, manifest.spec.outputSchema, path="$.output")
        result = {"valid": not issues, "errors": [issue.as_dict() for issue in issues]}
        run.trace_metadata = {
            **(run.trace_metadata or {}),
            "skill_output_validation": result,
        }
        if issues:
            run.state = "failed"
            run.status_reason = "skill_output_schema_failed"
            run.last_error = {"code": "skill_output_schema_failed", "errors": result["errors"]}
        await self._append_agent_event(
            run,
            "skill_output_validation",
            {"version_id": version.id, **result},
        )

    async def _append_agent_event(
        self,
        run: AgentRun,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        last_sequence = int(
            await self.session.scalar(
                select(func.max(AgentEvent.sequence_number)).where(AgentEvent.run_id == run.id)
            )
            or 0
        )
        self.session.add(
            AgentEvent(
                run_id=run.id,
                event_type=event_type,
                sequence_number=last_sequence + 1,
                payload=cast(dict[str, Any], sanitize_value(payload)),
            )
        )

    async def _run_one_test(
        self,
        manifest: SkillManifest,
        test: SkillTest,
    ) -> dict[str, Any]:
        fixture = test.fixture or {}
        expected = test.expected or {}
        input_payload = cast(dict[str, Any], fixture.get("input") or {})
        input_errors = validate_json_data(input_payload, manifest.spec.inputSchema, path="$.input")
        expected_input_valid = bool(expected.get("validation_result", True))
        rendered_prompt = None
        render_error = None
        if not input_errors:
            try:
                rendered_prompt = self._render(
                    manifest,
                    input_payload,
                    cast(dict[str, Any] | None, fixture.get("mocked_retrieval_results")),
                    cast(dict[str, Any] | None, fixture.get("mocked_tool_results")),
                )
            except SkillServiceError as exc:
                render_error = {"code": exc.code, "detail": exc.detail}
        model_result = fixture.get("deterministic_model_result") or {"answer_text": ""}
        output_payload = (
            model_result if isinstance(model_result, dict) else {"answer_text": str(model_result)}
        )
        output_errors = validate_json_data(
            output_payload, manifest.spec.outputSchema, path="$.output"
        )
        expected_output_valid = bool(expected.get("output_schema_result", True))
        effective = await self.effective_policy(manifest)
        expected_tools = expected.get("policy_allowed_tools")
        checks = {
            "input_validation": (not input_errors) is expected_input_valid,
            "render": render_error is None,
            "output_validation": (not output_errors) is expected_output_valid,
            "policy": True,
        }
        if isinstance(expected_tools, list):
            checks["policy"] = sorted(expected_tools) == sorted(effective["allowed_tools"])
        expected_citations = expected.get("citations")
        if isinstance(expected_citations, list):
            actual_citations = (
                output_payload.get("citations") if isinstance(output_payload, dict) else []
            )
            checks["citations"] = sorted(expected_citations) == sorted(actual_citations or [])
        passed = all(checks.values())
        return {
            "test_id": test.id,
            "name": test.name,
            "passed": passed,
            "checks": checks,
            "input_errors": [issue.as_dict() for issue in input_errors],
            "output_errors": [issue.as_dict() for issue in output_errors],
            "render_error": render_error,
            "rendered_prompt": rendered_prompt,
            "effective_policy": effective,
        }

    async def _import_diff(
        self,
        validation: ManifestValidationResult,
        existing: Skill | None,
    ) -> dict[str, Any]:
        duplicate_version = False
        if existing is not None and validation.version:
            duplicate_version = (
                await self._find_version(existing.id, validation.version) is not None
            )
        return {
            "existing_skill": existing.id if existing else None,
            "duplicate_version": duplicate_version,
            "import_state": "draft",
            "auto_publish": False,
            "auto_enable_tools": False,
        }

    def _effective_limits(self, manifest: SkillManifest) -> dict[str, Any]:
        limits = manifest.spec.limits
        runtime_step_budget = min(16, max(12, limits.maxSteps * 2))
        return {
            "max_steps": runtime_step_budget,
            "max_tool_calls": min(limits.maxToolCalls, 3),
            "request_timeout_seconds": min(limits.timeoutSeconds, 45),
            "per_step_timeout_seconds": min(max(1, limits.timeoutSeconds // 4), 10),
            "token_budget": min(
                manifest.spec.modelPolicy.maxInputTokens, self.settings.model_max_input_tokens
            ),
            "cost_budget_usd": self.settings.model_max_estimated_cost_usd,
            "max_retries": 0,
        }

    def _effective_model_policy(self, manifest: SkillManifest) -> dict[str, Any]:
        return {
            "capability": manifest.spec.modelPolicy.capability,
            "provider": self.settings.chat_provider,
            "model": self.settings.chat_model,
            "max_input_tokens": min(
                manifest.spec.modelPolicy.maxInputTokens,
                self.settings.model_max_input_tokens,
            ),
            "max_output_tokens": min(
                manifest.spec.modelPolicy.maxOutputTokens,
                self.settings.model_max_output_tokens,
            ),
        }

    async def _audit(self, event_type: str, metadata: dict[str, Any]) -> None:
        self.session.add(
            AuditEvent(
                owner_user_id=self.owner_user_id,
                event_type=event_type,
                request_id=self.request_id,
                trace_id=self.trace_id,
                event_metadata=cast(dict[str, Any], sanitize_value(metadata)),
            )
        )
