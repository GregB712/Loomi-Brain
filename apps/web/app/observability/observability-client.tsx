"use client";

import {
  createLoomiClient,
  type ObservabilityEvaluationHistory,
  type ObservabilityFeedbackSummary,
  type ObservabilityRetrievalResponse,
  type ObservabilityRun,
  type ObservabilityStatus,
  type ObservabilitySummary,
} from "@loomi/contracts";
import { MetricCard, StatusPill } from "@loomi/ui";
import {
  Activity,
  BarChart3,
  BrainCircuit,
  Clock3,
  Database,
  Gauge,
  Home,
  Library,
  Link2,
  Loader2,
  LogIn,
  MessageSquare,
  RefreshCw,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function ObservabilityClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [rangeDays, setRangeDays] = useState("7");
  const [runKind, setRunKind] = useState("");
  const [status, setStatus] = useState<ObservabilityStatus | null>(null);
  const [summary, setSummary] = useState<ObservabilitySummary | null>(null);
  const [runs, setRuns] = useState<ObservabilityRun[]>([]);
  const [retrieval, setRetrieval] =
    useState<ObservabilityRetrievalResponse | null>(null);
  const [evaluations, setEvaluations] =
    useState<ObservabilityEvaluationHistory | null>(null);
  const [feedback, setFeedback] = useState<ObservabilityFeedbackSummary | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      await refreshAll(rangeDays, runKind);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshAll(nextRange = rangeDays, nextRunKind = runKind) {
    setBusy(true);
    setError(null);
    try {
      const params = rangeParams(nextRange);
      const runParams = new URLSearchParams(params);
      if (nextRunKind) {
        runParams.set("run_kind", nextRunKind);
      }
      const [
        nextStatus,
        nextSummary,
        nextRuns,
        nextRetrieval,
        nextEvaluations,
        nextFeedback,
      ] = await Promise.all([
        apiClient.observabilityStatus(),
        apiClient.observabilitySummary(params),
        apiClient.observabilityRuns(runParams),
        apiClient.observabilityRetrieval(params),
        apiClient.observabilityEvaluations(params),
        apiClient.observabilityFeedback(params),
      ]);
      setStatus(nextStatus);
      setSummary(nextSummary);
      setRuns(nextRuns.items);
      setRetrieval(nextRetrieval);
      setEvaluations(nextEvaluations);
      setFeedback(nextFeedback);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Observability refresh failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <BrainCircuit size={23} strokeWidth={1.8} />
          </div>
          <div>
            <p className="brand-title">Loomi-Brain</p>
            <p className="brand-subtitle">Observability</p>
          </div>
        </div>
        <nav>
          <ul className="nav-list">
            <li>
              <Link className="nav-link" href="/">
                <Home size={18} aria-hidden="true" />
                <span>Home</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/knowledge">
                <Library size={18} aria-hidden="true" />
                <span>Knowledge</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/search">
                <Search size={18} aria-hidden="true" />
                <span>Search</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/chat">
                <MessageSquare size={18} aria-hidden="true" />
                <span>Chat</span>
              </Link>
            </li>
            <li>
              <Link className="nav-link" href="/runs">
                <Workflow size={18} aria-hidden="true" />
                <span>Runs</span>
              </Link>
            </li>
            <li>
              <Link
                className="nav-link"
                href="/observability"
                aria-current="page"
              >
                <Activity size={18} aria-hidden="true" />
                <span>Observability</span>
              </Link>
            </li>
          </ul>
        </nav>
      </aside>

      <main className="main observability-main">
        <header className="knowledge-header">
          <div>
            <p className="eyebrow">LLM observability</p>
            <h1>Trace product health without exposing private content.</h1>
            <p className="topbar-copy">
              Review sanitized spans, model usage, retrieval diagnostics,
              ingestion health, policy decisions, owner feedback, and
              deterministic evaluation status.
            </p>
          </div>
          <section className="environment-panel" aria-label="Telemetry status">
            <p className="panel-label">Exporter</p>
            <p className="panel-value">{status?.exporter ?? "unknown"}</p>
            <StatusPill tone={statusTone(status)}>
              {statusLabel(status)}
            </StatusPill>
          </section>
        </header>

        {!csrfToken ? (
          <section className="auth-panel" aria-labelledby="observability-auth">
            <h2 id="observability-auth">Owner Login</h2>
            <label>
              Email
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button
              className="command-button"
              type="button"
              disabled={busy}
              onClick={() => void handleLogin()}
            >
              <LogIn size={18} aria-hidden="true" />
              Sign In
            </button>
            {error ? <p className="form-error">{error}</p> : null}
          </section>
        ) : (
          <div className="observability-layout">
            <section
              className="observability-controls"
              aria-labelledby="observability-controls-title"
            >
              <div className="section-header">
                <h2 className="section-title" id="observability-controls-title">
                  Filters
                </h2>
                <Gauge size={18} aria-hidden="true" />
              </div>
              <label>
                Range
                <select
                  value={rangeDays}
                  onChange={(event) => {
                    const next = event.target.value;
                    setRangeDays(next);
                    void refreshAll(next, runKind);
                  }}
                >
                  <option value="1">Last 24 hours</option>
                  <option value="7">Last 7 days</option>
                  <option value="14">Last 14 days</option>
                  <option value="30">Last 30 days</option>
                </select>
              </label>
              <label>
                Run kind
                <select
                  value={runKind}
                  onChange={(event) => {
                    const next = event.target.value;
                    setRunKind(next);
                    void refreshAll(rangeDays, next);
                  }}
                >
                  <option value="">All runs</option>
                  <option value="chat">Chat</option>
                  <option value="agent">Agent</option>
                </select>
              </label>
              <button
                className="command-button"
                type="button"
                disabled={busy}
                onClick={() => void refreshAll()}
              >
                {busy ? (
                  <Loader2 size={18} aria-hidden="true" />
                ) : (
                  <RefreshCw size={18} aria-hidden="true" />
                )}
                Refresh
              </button>
              {status ? <TelemetryState status={status} /> : null}
              {error ? <p className="form-error">{error}</p> : null}
            </section>

            <section className="observability-content" aria-live="polite">
              <div className="metrics observability-metrics">
                <MetricCard
                  label="Runs"
                  value={String(summary?.runs.total ?? 0)}
                  detail={`${percent(summary?.runs.success_rate ?? 0)} success`}
                  icon={<Workflow size={21} aria-hidden="true" />}
                />
                <MetricCard
                  label="Latency p95"
                  value={`${summary?.telemetry.latency_p95_ms ?? 0}ms`}
                  detail={`${summary?.telemetry.spans ?? 0} sampled spans`}
                  icon={<Clock3 size={21} aria-hidden="true" />}
                />
                <MetricCard
                  label="Tokens"
                  value={compact(summary?.model_usage.total_tokens ?? 0)}
                  detail={`$${summary?.model_usage.estimated_cost_usd ?? 0}`}
                  icon={<BarChart3 size={21} aria-hidden="true" />}
                />
                <MetricCard
                  label="Evaluation"
                  value={summary?.evaluation.passed === false ? "Fail" : "Pass"}
                  detail={summary?.evaluation.baseline_name ?? "synthetic"}
                  icon={<ShieldCheck size={21} aria-hidden="true" />}
                />
              </div>

              <div className="observability-grid">
                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Recent Runs</h2>
                    <Activity size={18} aria-hidden="true" />
                  </div>
                  <div className="observability-run-list">
                    {runs.length ? (
                      runs.map((run) => <RunRow key={run.id} run={run} />)
                    ) : (
                      <p className="item-meta">No runs in this range.</p>
                    )}
                  </div>
                </section>

                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Provider Usage</h2>
                    <BarChart3 size={18} aria-hidden="true" />
                  </div>
                  <BreakdownTable
                    rows={
                      summary?.providers.map((provider) => ({
                        label: `${provider.provider} / ${provider.model}`,
                        value: `${provider.runs} runs`,
                        detail: `${compact(provider.tokens)} tokens · $${provider.estimated_cost_usd}`,
                      })) ?? []
                    }
                  />
                </section>

                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Retrieval Diagnostics</h2>
                    <Search size={18} aria-hidden="true" />
                  </div>
                  <BreakdownTable
                    rows={
                      retrieval?.summary.by_mode.map((mode) => ({
                        label: mode.mode,
                        value: `${mode.runs} searches`,
                        detail: `${mode.avg_candidates} avg candidates · ${mode.latency_p95_ms}ms p95`,
                      })) ?? []
                    }
                  />
                </section>

                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Ingestion And Policy</h2>
                    <Database size={18} aria-hidden="true" />
                  </div>
                  <div className="signal-grid">
                    <Signal label="Jobs" value={summary?.ingestion.total} />
                    <Signal label="Chunks" value={summary?.ingestion.chunks} />
                    <Signal label="Tools" value={summary?.tools.total} />
                    <Signal
                      label="Approvals"
                      value={summary?.approvals.total}
                    />
                  </div>
                  <pre className="debug-block">
                    {JSON.stringify(
                      {
                        ingestion: summary?.ingestion.by_status,
                        tools: summary?.tools.by_status,
                        approvals: summary?.approvals.by_status,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </section>

                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Evaluation History</h2>
                    <ShieldCheck size={18} aria-hidden="true" />
                  </div>
                  <EvaluationSummary evaluations={evaluations} />
                </section>

                <section className="observability-panel">
                  <div className="section-header">
                    <h2 className="section-title">Owner Feedback</h2>
                    <MessageSquare size={18} aria-hidden="true" />
                  </div>
                  <p className="item-title">{feedback?.total ?? 0} ratings</p>
                  <pre className="debug-block">
                    {JSON.stringify(feedback?.by_rating ?? {}, null, 2)}
                  </pre>
                </section>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function TelemetryState({ status }: { status: ObservabilityStatus }) {
  return (
    <div className="telemetry-state">
      <StatusPill tone={status.enabled ? "good" : "warn"}>
        {status.enabled ? "enabled" : "disabled"}
      </StatusPill>
      <StatusPill tone={status.local_only ? "warn" : "good"}>
        {status.local_only ? "local only" : "external export"}
      </StatusPill>
      <StatusPill tone={status.content_capture === "none" ? "good" : "warn"}>
        {status.content_capture}
      </StatusPill>
      <p className="item-meta">
        Sample rate {Math.round(status.sample_rate * 100)}% · retention{" "}
        {status.retention_days} days · last export{" "}
        {status.latest_exporter_status ?? "none"}
      </p>
    </div>
  );
}

function RunRow({ run }: { run: ObservabilityRun }) {
  return (
    <article className="observability-run-row">
      <div>
        <p className="item-title">
          {run.run_kind} · {run.provider ?? "unknown"}
        </p>
        <p className="item-meta">
          {run.model ?? "unknown model"} · {run.latency_ms ?? 0}ms ·{" "}
          {compact(Number(run.usage.total_tokens ?? 0))} tokens
        </p>
        <p className="item-meta">{new Date(run.created_at).toLocaleString()}</p>
      </div>
      <div className="run-trace-cell">
        <StatusPill tone={run.state === "failed" ? "bad" : "neutral"}>
          {run.state}
        </StatusPill>
        {run.trace_url ? (
          <a className="trace-link" href={run.trace_url}>
            <Link2 size={15} aria-hidden="true" />
            Trace
          </a>
        ) : (
          <span className="trace-chip">
            {run.trace_id?.slice(0, 12) ?? "no trace"}
          </span>
        )}
      </div>
    </article>
  );
}

function BreakdownTable({
  rows,
}: {
  rows: Array<{ label: string; value: string; detail: string }>;
}) {
  if (!rows.length) {
    return <p className="item-meta">No data in this range.</p>;
  }
  return (
    <div className="breakdown-table">
      {rows.map((row) => (
        <div key={row.label}>
          <span>{row.label}</span>
          <strong>{row.value}</strong>
          <small>{row.detail}</small>
        </div>
      ))}
    </div>
  );
}

function EvaluationSummary({
  evaluations,
}: {
  evaluations: ObservabilityEvaluationHistory | null;
}) {
  const report = evaluations?.current_synthetic_report;
  const deterministic = report?.deterministic_metrics as
    Record<string, unknown> | undefined;
  const regression = report?.regression_summary as
    Record<string, unknown> | undefined;
  return (
    <div className="evaluation-summary">
      <StatusPill tone={regression?.passed === false ? "bad" : "good"}>
        {regression?.passed === false ? "regression" : "clean"}
      </StatusPill>
      <div className="signal-grid">
        <Signal label="Precision@3" value={deterministic?.precision_at_3} />
        <Signal label="Recall@3" value={deterministic?.recall_at_3} />
        <Signal label="MRR" value={deterministic?.mean_reciprocal_rank} />
        <Signal label="nDCG@3" value={deterministic?.ndcg_at_3} />
      </div>
    </div>
  );
}

function Signal({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{String(value ?? 0)}</strong>
    </div>
  );
}

function statusTone(status: ObservabilityStatus | null) {
  if (!status?.enabled) {
    return "warn" as const;
  }
  if (status.latest_exporter_status === "failed") {
    return "bad" as const;
  }
  return "good" as const;
}

function statusLabel(status: ObservabilityStatus | null) {
  if (!status) {
    return "Sign in";
  }
  if (!status.enabled) {
    return "Disabled";
  }
  if (status.local_only) {
    return "Local only";
  }
  return "Enabled";
}

function rangeParams(days: string) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - Number(days));
  return new URLSearchParams({
    start: start.toISOString(),
    end: end.toISOString(),
  });
}

function compact(value: number) {
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function resolveApiBase() {
  if (typeof window === "undefined") {
    return API_BASE;
  }
  try {
    const configured = new URL(API_BASE);
    const currentHost = window.location.hostname;
    const loopbackHosts = new Set(["localhost", "127.0.0.1"]);
    if (
      loopbackHosts.has(configured.hostname) &&
      loopbackHosts.has(currentHost)
    ) {
      configured.hostname = currentHost;
      return configured.origin;
    }
  } catch {
    return API_BASE;
  }
  return API_BASE;
}
