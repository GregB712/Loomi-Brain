# Evaluation

Phase 5 ships a deterministic synthetic evaluation command:

```bash
make eval
```

The dataset contains synthetic documents, representative queries, relevant chunk labels,
a no-answer question, a prompt-injection fixture, and expected citation sources.

The command reports:

- lexical, semantic, and hybrid retrieval metrics;
- precision@3;
- recall@3;
- mean reciprocal rank;
- nDCG@3;
- citation validity;
- citation coverage;
- deterministic groundedness and answer relevance heuristics;
- no-answer correctness;
- prompt-injection resistance;
- tool-policy compliance;
- latency;
- token usage;
- estimated cost.

The default command compares deterministic metrics to built-in regression thresholds and
exits non-zero on material quality or budget regressions. Optional `--baseline`,
`--thresholds`, and `--write-baseline` flags support file-based baselines for local
experiments.

Model-judged metrics are explicitly disabled in the default command. Future optional
evaluation can add an LLM judge, but those metrics must be reported separately from
deterministic checks and stay disabled in default CI if they require paid APIs.
