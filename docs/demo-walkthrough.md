# Demo Walkthrough

Reader: GitHub reviewer evaluating Loomi-Brain from a fresh clone.

Post-read action: run the synthetic demo without personal data or paid model credentials.

## Prepare

```bash
cp .env.example .env
make setup
docker compose -f infra/docker/compose.yml up --build -d postgres redis api worker web
```

Open the web app and sign in with the development-only owner credentials from the README.

## Synthetic Documents

Use synthetic files only. Good fixtures:

- Project note explaining hybrid search and reciprocal rank fusion.
- Meeting note with action items and dates.
- Security note containing an obvious prompt-injection sentence such as "ignore previous instructions".
- Small CSV with formula-like strings.
- Short Markdown note with headings and links.

## Flow

1. Upload the synthetic files in Knowledge.
2. Confirm ingestion reaches a completed state.
3. Run lexical, semantic, and hybrid search for the same query.
4. Ask Chat a question that should cite one or two documents.
5. Ask a no-answer question such as "What is the owner's bank account number?"
6. Open Runs and start a harmless agent run.
7. Approve a harmless tool only when the exact arguments match.
8. Open MCP and register the built-in test server.
9. Enable one harmless test tool and invoke it.
10. Open Skills, create a simple extraction skill, run a deterministic test, publish it, and execute it.
11. Open Observability and inspect sanitized spans and evaluation status.
12. Run:

```bash
make eval
```

## Screenshot Set

Capture these after synthetic data is loaded:

- Knowledge Library after ingestion.
- Hybrid search result comparison.
- Cited chat with source panel.
- Run Inspector paused at approval.
- MCP Console with the test server.
- Skill Editor test result.
- Observability dashboard summary.
