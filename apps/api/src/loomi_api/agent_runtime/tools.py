from __future__ import annotations

import ast
import hashlib
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select

from loomi_api.agent_runtime.contracts import Tool, ToolContext, ToolExecutionError, ToolResult
from loomi_api.db.models import Chunk, Document, DocumentVersion
from loomi_api.retrieval.contracts import RetrievalQuery, SearchFilters
from loomi_api.retrieval.service import RetrievalService


@dataclass(frozen=True)
class ToolRegistry:
    tools: dict[str, Tool]

    def get(self, tool_id: str) -> Tool | None:
        return self.tools.get(tool_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(self.tools)


def default_tool_registry() -> ToolRegistry:
    tools: tuple[Tool, ...] = (
        cast(Tool, KnowledgeSearchTool()),
        cast(Tool, KnowledgeDocumentMetadataTool()),
        cast(Tool, KnowledgeSourceExcerptTool()),
        cast(Tool, CalculatorTool()),
        cast(Tool, NotesCreateDraftTool()),
    )
    return ToolRegistry({tool.id: tool for tool in tools})


class KnowledgeSearchTool:
    id = "knowledge.search"
    description = "Search owner-scoped knowledge using bounded hybrid retrieval."
    risk_class = "read-only"
    timeout_seconds = 8
    output_size_limit = 12_000
    idempotent = True
    approval_policy = "never"
    input_schema = {
        "type": "object",
        "required": ["query"],
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": 500},
            "mode": {"type": "string", "enum": ["lexical", "semantic", "hybrid"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            "min_score": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "items": {"type": "array"},
            "selected_context": {"type": "array"},
            "warnings": {"type": "array"},
        },
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        mode = cast(str, args.get("mode", "hybrid"))
        limit = cast(int, args.get("limit", 5))
        min_score = float(args.get("min_score", 0.0))
        result = await RetrievalService(context.settings).search(
            context.session,
            RetrievalQuery(
                owner_user_id=context.owner_user_id,
                query=cast(str, args["query"]),
                mode=cast(Any, mode),
                filters=SearchFilters(),
                limit=limit,
                min_score=min_score,
                debug=True,
            ),
        )
        return ToolResult(
            output={
                "mode": result.mode,
                "query": result.query,
                "items": [
                    {
                        "chunk_id": candidate.chunk_id,
                        "document_id": candidate.document_id,
                        "document_title": candidate.document_title,
                        "score": round(candidate.score, 4),
                        "excerpt": _excerpt(candidate.text),
                    }
                    for candidate in result.candidates
                ],
                "selected_context": [
                    {
                        "allowed_citation_id": item.allowed_citation_id,
                        "chunk_id": item.candidate.chunk_id,
                        "document_title": item.candidate.document_title,
                        "excerpt": item.excerpt,
                    }
                    for item in result.selected_context
                ],
                "warnings": list(result.warnings),
            },
            citations=result.selected_context,
            usage={"retrieved_candidates": len(result.candidates)},
        )


class KnowledgeDocumentMetadataTool:
    id = "knowledge.get_document_metadata"
    description = "Fetch sanitized metadata for one owner-scoped document."
    risk_class = "read-only"
    timeout_seconds = 6
    output_size_limit = 8_000
    idempotent = True
    approval_policy = "never"
    input_schema = {
        "type": "object",
        "required": ["document_id"],
        "additionalProperties": False,
        "properties": {"document_id": {"type": "string", "minLength": 1, "maxLength": 80}},
    }
    output_schema = {"type": "object", "properties": {"document": {"type": "object"}}}

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        document_id = cast(str, args["document_id"])
        row = (
            await context.session.execute(
                select(Document, DocumentVersion)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(
                    Document.id == document_id,
                    Document.owner_user_id == context.owner_user_id,
                    Document.deleted_at.is_(None),
                )
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            raise ToolExecutionError("document_not_found", "Document metadata was not found.")
        document = cast(Document, row[0])
        version = cast(DocumentVersion, row[1])
        chunk_count = await context.session.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.document_id == document.id,
                Chunk.owner_user_id == context.owner_user_id,
            )
        )
        return ToolResult(
            output={
                "document": {
                    "id": document.id,
                    "title": document.title,
                    "status": document.status,
                    "source_kind": document.source_kind,
                    "version": version.version_number,
                    "media_type": version.media_type,
                    "chunk_count": int(chunk_count or 0),
                    "created_at": document.created_at.isoformat(),
                    "updated_at": document.updated_at.isoformat(),
                }
            }
        )


class KnowledgeSourceExcerptTool:
    id = "knowledge.get_source_excerpt"
    description = "Fetch a bounded excerpt for one owner-scoped stored chunk."
    risk_class = "read-only"
    timeout_seconds = 6
    output_size_limit = 8_000
    idempotent = True
    approval_policy = "never"
    input_schema = {
        "type": "object",
        "required": ["chunk_id"],
        "additionalProperties": False,
        "properties": {"chunk_id": {"type": "string", "minLength": 1, "maxLength": 80}},
    }
    output_schema = {"type": "object", "properties": {"excerpt": {"type": "string"}}}

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        chunk_id = cast(str, args["chunk_id"])
        row = (
            await context.session.execute(
                select(Chunk, Document, DocumentVersion)
                .join(Document, Document.id == Chunk.document_id)
                .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
                .where(
                    Chunk.id == chunk_id,
                    Chunk.owner_user_id == context.owner_user_id,
                    Document.owner_user_id == context.owner_user_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise ToolExecutionError("source_not_found", "Source excerpt was not found.")
        chunk = cast(Chunk, row[0])
        document = cast(Document, row[1])
        version = cast(DocumentVersion, row[2])
        return ToolResult(
            output={
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_title": document.title,
                "document_version": version.version_number,
                "excerpt": _excerpt(chunk.text, limit=1000),
                "provenance": chunk.provenance,
            }
        )


class CalculatorTool:
    id = "calculator"
    description = "Evaluate a small arithmetic expression with a safe AST evaluator."
    risk_class = "read-only"
    timeout_seconds = 2
    output_size_limit = 2_000
    idempotent = True
    approval_policy = "never"
    input_schema = {
        "type": "object",
        "required": ["expression"],
        "additionalProperties": False,
        "properties": {"expression": {"type": "string", "minLength": 1, "maxLength": 160}},
    }
    output_schema = {"type": "object", "properties": {"result": {"type": "number"}}}

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        expression = cast(str, args["expression"])
        try:
            result = _safe_calculate(expression)
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            raise ToolExecutionError(
                "calculator_error",
                "Expression could not be evaluated.",
            ) from exc
        return ToolResult(output={"expression": expression, "result": result})


class NotesCreateDraftTool:
    id = "notes.create_draft"
    description = "Stage a local draft note from owner-provided text after explicit approval."
    risk_class = "local-mutation"
    timeout_seconds = 5
    output_size_limit = 4_000
    idempotent = False
    approval_policy = "always"
    input_schema = {
        "type": "object",
        "required": ["title", "content"],
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 120},
            "content": {"type": "string", "minLength": 1, "maxLength": 2000},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "draft_note_id": {"type": "string"},
            "title": {"type": "string"},
            "content_preview": {"type": "string"},
        },
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolResult:
        title = cast(str, args["title"]).strip()
        content = cast(str, args["content"]).strip()
        digest = hashlib.sha256(f"{context.owner_user_id}:{title}:{content}".encode()).hexdigest()
        draft_note_id = f"draft_{digest[:12]}"
        return ToolResult(
            output={
                "draft_note_id": draft_note_id,
                "title": title,
                "content_preview": _excerpt(content, limit=420),
                "storage": "tool_call_result",
            }
        )


def _safe_calculate(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body)
    if abs(result) > 1_000_000_000:
        raise ValueError("result too large")
    return result


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value = _eval_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("operator not allowed")
        if isinstance(node.op, ast.Pow) and abs(right) > 8:
            raise ValueError("exponent too large")
        return float(operation(left, right))
    raise ValueError("expression not allowed")


def _excerpt(value: str, *, limit: int = 700) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1].rstrip()}..."
