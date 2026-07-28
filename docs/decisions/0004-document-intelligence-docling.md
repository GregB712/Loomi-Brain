# ADR 0004: Document Extraction Engine

## Status

Accepted with guardrails.

## Context

The product needs ingestion for PDFs, office documents, Markdown, text, HTML, CSV, images, and supported URLs while preserving structure, tables, page references, metadata, and provenance. Building rich extraction from scratch would be high risk and low leverage.

## Decision

Use Docling as the primary document extraction adapter where it supports the media type. Add narrow, explicit adapters for formats or behaviors that Docling does not cover well, such as CSV-specific table handling or strict Markdown extraction.

## Guardrails

- Run extraction in the worker, not the web process.
- Apply size, page count, decompression, runtime, and output limits.
- Store parser version and chunking strategy in provenance.
- Treat extracted text as untrusted data.
- Preserve warnings when structure, table extraction, OCR, or page references are incomplete.

## Consequences

- The project benefits from an actively maintained extraction ecosystem.
- The worker must isolate and monitor parser resource use.
- Evaluation fixtures must catch silent loss of tables, headings, page references, and citations.
