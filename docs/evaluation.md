# Evaluation

Phase 3 ships a deterministic synthetic evaluation command:

```bash
make eval
```

The dataset contains synthetic documents, representative queries, relevant chunk labels, a no-answer question, a prompt-injection fixture, and expected citation sources.

The command reports:

- precision@3;
- recall@3;
- mean reciprocal rank;
- citation validity;
- deterministic groundedness;
- answer relevance;
- no-answer correctness;
- latency;
- token usage;
- estimated cost.

Model-judged metrics are explicitly disabled in the default command. Future optional evaluation can add an LLM judge, but those metrics must be reported separately from deterministic checks.
