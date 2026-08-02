from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from loomi_api.api.dependencies import (
    CsrfOwnerContext,
    DbSession,
    OwnerContext,
    get_settings_from_app,
)
from loomi_api.skills.service import SkillService, SkillServiceError

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


class ManifestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: dict[str, Any]


class CreateSkillRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: dict[str, Any]
    tests: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class CloneSkillVersionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    new_version: str = Field(min_length=5, max_length=40)


class SkillDryRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    input: dict[str, Any] | None = None
    mocked_retrieval_results: dict[str, Any] | None = None
    mocked_tool_results: dict[str, Any] | None = None


class SkillExecuteRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    input: dict[str, Any] = Field(default_factory=dict)


class SkillTestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    fixture: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)


class SkillImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = Field(min_length=1, max_length=160_000)
    persist: bool = False


@router.get("/starter-templates")
async def list_starter_skill_templates(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    return await _service(request, session, owner.user.id).starter_templates()


@router.post("/validate")
async def validate_skill_manifest(
    payload: ManifestRequest,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    return await _service(request, session, owner.user.id).validate_manifest_payload(
        payload.manifest
    )


@router.get("")
async def list_skills(
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    state: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return await _service(request, session, owner.user.id).list_skills(
        state=state,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201)
async def create_skill(
    payload: CreateSkillRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).create_skill(
            payload.manifest,
            tests=payload.tests,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/import")
async def import_skill_bundle(
    payload: SkillImportRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).import_bundle(
            payload.content,
            persist=payload.persist,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}")
async def get_skill(
    skill_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).get_skill(skill_id)
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.patch("/{skill_id}/versions/{version_id}")
async def update_draft_skill_version(
    skill_id: str,
    version_id: str,
    payload: ManifestRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).update_draft_version(
            skill_id,
            version_id,
            payload.manifest,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/publish")
async def publish_skill_version(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).publish_version(skill_id, version_id)
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/archive")
async def archive_skill_version(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).set_version_state(
            skill_id,
            version_id,
            state="archived",
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/disable")
async def disable_skill_version(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).set_version_state(
            skill_id,
            version_id,
            state="disabled",
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/clone", status_code=201)
async def clone_skill_version(
    skill_id: str,
    version_id: str,
    payload: CloneSkillVersionRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).clone_version(
            skill_id,
            version_id,
            new_version=payload.new_version,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/dry-run")
async def dry_run_skill_version(
    skill_id: str,
    version_id: str,
    payload: SkillDryRunRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).dry_run_version(
            skill_id,
            version_id,
            input_payload=payload.input,
            mocked_retrieval=payload.mocked_retrieval_results,
            mocked_tools=payload.mocked_tool_results,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/execute", status_code=202)
async def execute_skill_version(
    skill_id: str,
    version_id: str,
    payload: SkillExecuteRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
    idempotency_key: Annotated[str | None, Header(alias="idempotency-key")] = None,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).execute_version(
            skill_id,
            version_id,
            input_payload=payload.input,
            idempotency_key=idempotency_key,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/versions/{version_id}/export")
async def export_skill_version(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
    include_tests: bool = Query(default=False),
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).export_version(
            skill_id,
            version_id,
            include_tests=include_tests,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/versions/{from_version_id}/diff/{to_version_id}")
async def diff_skill_versions(
    skill_id: str,
    from_version_id: str,
    to_version_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).diff_versions(
            skill_id,
            from_version_id,
            to_version_id,
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/versions/{version_id}/tests")
async def list_skill_tests(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: OwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).list_tests(skill_id, version_id)
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/versions/{version_id}/tests", status_code=201)
async def create_skill_test(
    skill_id: str,
    version_id: str,
    payload: SkillTestRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).create_test(
            skill_id,
            version_id,
            payload.model_dump(),
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.put("/{skill_id}/versions/{version_id}/tests/{test_id}")
async def update_skill_test(
    skill_id: str,
    version_id: str,
    test_id: str,
    payload: SkillTestRequest,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).update_test(
            skill_id,
            version_id,
            test_id,
            payload.model_dump(),
        )
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


@router.delete("/{skill_id}/versions/{version_id}/tests/{test_id}", status_code=204)
async def delete_skill_test(
    skill_id: str,
    version_id: str,
    test_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> Response:
    try:
        await _service(request, session, owner.user.id).delete_test(skill_id, version_id, test_id)
    except SkillServiceError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=204)


@router.post("/{skill_id}/versions/{version_id}/tests:run")
async def run_skill_tests(
    skill_id: str,
    version_id: str,
    request: Request,
    session: DbSession,
    owner: CsrfOwnerContext,
) -> dict[str, Any]:
    try:
        return await _service(request, session, owner.user.id).run_tests(skill_id, version_id)
    except SkillServiceError as exc:
        raise _http_error(exc) from exc


def _service(request: Request, session: DbSession, owner_user_id: str) -> SkillService:
    return SkillService(
        session=session,
        settings=get_settings_from_app(request),
        owner_user_id=owner_user_id,
        request_id=str(getattr(request.state, "request_id", "")),
        trace_id=str(getattr(request.state, "trace_id", "")),
    )


def _http_error(exc: SkillServiceError) -> HTTPException:
    if exc.code.endswith("not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "duplicate_skill_version",
        "published_immutable",
        "invalid_lifecycle",
        "skill_not_executable",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == "import_too_large":
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=status_code, detail=exc.detail)
