# Evaluation And Performance Report

Reader: reviewer checking whether performance and quality claims are reproducible.

Post-read action: rerun the deterministic measurements and understand what they do and do not prove.

## Current Measurement Method

The deterministic evaluation uses built-in synthetic documents and queries. It does not call a paid model provider. Metrics cover retrieval quality, citation validity, prompt-injection resistance, no-answer behavior, token budget, estimated cost, and mock-mode latency.

Run:

```bash
make eval
```

## Latest Local Result

Measured on 2026-08-02 in the local development environment:

- Dataset: 3 synthetic documents, 4 queries, 1 prompt-injection example, 1 no-answer case.
- Hybrid mean reciprocal rank: 1.0.
- Hybrid nDCG@3: 1.0.
- Hybrid precision@3: 0.875.
- Hybrid recall@3: 1.0.
- Citation coverage: 1.0.
- Citation validity: 1.0.
- Prompt-injection resistance fixture: 1.0.
- No-answer correctness: 1.0.
- Mock-mode latency: 1 ms.
- Estimated cost: 0.000056 USD.
- Token usage: 112.

## What This Does Not Prove

- It does not prove production retrieval quality on a large private corpus.
- It does not benchmark real provider first-token latency.
- It does not measure OCR-heavy ingestion throughput.
- It does not validate GPU model throughput.
- It does not replace Playwright or accessibility testing.

## Recommended Release Measurements

Before tagging a public release, record:

- Hardware and operating system.
- Docker image tags.
- Dataset size and file types.
- Ingestion throughput.
- Search latency by mode.
- Mock first-token latency.
- API health and chat endpoint latency.
- Deterministic evaluation output.
- Test counts.
