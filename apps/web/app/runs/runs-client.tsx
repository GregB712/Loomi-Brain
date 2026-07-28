"use client";

import {
  createLoomiClient,
  type AgentApproval,
  type AgentRunDetail,
  type AgentRunListResponse,
  type AgentRunSummary,
  type AgentToolCall,
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  Activity,
  BrainCircuit,
  Check,
  CircleStop,
  Home,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const defaultTools = [
  "knowledge.search",
  "knowledge.get_document_metadata",
  "knowledge.get_source_excerpt",
  "calculator",
  "notes.create_draft",
];

export function RunsClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [runs, setRuns] = useState<AgentRunListResponse | null>(null);
  const [activeRun, setActiveRun] = useState<AgentRunDetail | null>(null);
  const [stateFilter, setStateFilter] = useState("");
  const [ownerRequest, setOwnerRequest] = useState("Calculate 2 + 3 * 4.");
  const [allowedTools, setAllowedTools] = useState<string[]>(defaultTools);
  const [maxSteps, setMaxSteps] = useState(16);
  const [maxToolCalls, setMaxToolCalls] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      await refreshRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshRuns(nextState = stateFilter) {
    const params = new URLSearchParams({ limit: "30", offset: "0" });
    if (nextState) {
      params.set("state", nextState);
    }
    const list = await apiClient.listAgentRuns(params);
    setRuns(list);
    const selected = list.items.find((run) => run.id === activeRun?.id);
    const nextRun = selected ?? list.items[0];
    if (nextRun) {
      setActiveRun(await apiClient.getAgentRun(nextRun.id));
    } else {
      setActiveRun(null);
    }
  }

  async function startRun() {
    if (!csrfToken || !ownerRequest.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiClient.createAgentRun(csrfToken, {
        owner_request: ownerRequest.trim(),
        allowed_tools: allowedTools,
        limits: {
          max_steps: maxSteps,
          max_tool_calls: maxToolCalls,
        },
      });
      setActiveRun(created);
      await refreshRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Run failed.");
    } finally {
      setBusy(false);
    }
  }

  async function selectRun(run: AgentRunSummary) {
    setActiveRun(await apiClient.getAgentRun(run.id));
  }

  async function approve(approval: AgentApproval) {
    if (!csrfToken || !activeRun || approval.status !== "pending") {
      return;
    }
    setBusy(true);
    try {
      const next = await apiClient.approveAgentToolCall(
        activeRun.id,
        approval.id,
        csrfToken,
      );
      setActiveRun(next);
      await refreshRuns();
    } finally {
      setBusy(false);
    }
  }

  async function deny(approval: AgentApproval) {
    if (!csrfToken || !activeRun || approval.status !== "pending") {
      return;
    }
    setBusy(true);
    try {
      const next = await apiClient.denyAgentToolCall(
        activeRun.id,
        approval.id,
        csrfToken,
        "Denied from run inspector.",
      );
      setActiveRun(next);
      await refreshRuns();
    } finally {
      setBusy(false);
    }
  }

  async function cancelActiveRun() {
    if (!csrfToken || !activeRun) {
      return;
    }
    setBusy(true);
    try {
      setActiveRun(await apiClient.cancelAgentRun(activeRun.id, csrfToken));
      await refreshRuns();
    } finally {
      setBusy(false);
    }
  }

  async function retryActiveRun() {
    if (!csrfToken || !activeRun) {
      return;
    }
    setBusy(true);
    try {
      setActiveRun(await apiClient.retryAgentRun(activeRun.id, csrfToken));
      await refreshRuns();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Retry failed.");
    } finally {
      setBusy(false);
    }
  }

  function toggleTool(toolId: string) {
    setAllowedTools((current) =>
      current.includes(toolId)
        ? current.filter((item) => item !== toolId)
        : [...current, toolId],
    );
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
            <p className="brand-subtitle">Run inspector</p>
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
              <Link className="nav-link" href="/runs" aria-current="page">
                <Workflow size={18} aria-hidden="true" />
                <span>Runs</span>
              </Link>
            </li>
          </ul>
        </nav>
      </aside>

      <main className="main runs-main">
        <header className="knowledge-header">
          <div>
            <p className="eyebrow">Controlled agent runtime</p>
            <h1>Inspect every state, tool, and approval.</h1>
            <p className="topbar-copy">
              Start bounded agent runs, review persisted state transitions, and
              approve or deny sensitive tool calls with exact argument hashes.
            </p>
          </div>
          <section className="environment-panel" aria-label="Runtime status">
            <p className="panel-label">Runtime</p>
            <p className="panel-value">Explicit state machine</p>
            <StatusPill tone="good">Phase 4</StatusPill>
          </section>
        </header>

        {!csrfToken ? (
          <section className="auth-panel" aria-labelledby="runs-auth-title">
            <h2 id="runs-auth-title">Owner Login</h2>
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
          <div className="runs-layout">
            <section className="run-composer" aria-labelledby="new-run-title">
              <div className="section-header">
                <h2 className="section-title" id="new-run-title">
                  New Run
                </h2>
                <Activity size={18} aria-hidden="true" />
              </div>
              <label>
                Owner request
                <textarea
                  value={ownerRequest}
                  onChange={(event) => setOwnerRequest(event.target.value)}
                />
              </label>
              <div className="limit-grid">
                <label>
                  Max steps
                  <input
                    type="number"
                    min={1}
                    max={64}
                    value={maxSteps}
                    onChange={(event) =>
                      setMaxSteps(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Max tools
                  <input
                    type="number"
                    min={0}
                    max={12}
                    value={maxToolCalls}
                    onChange={(event) =>
                      setMaxToolCalls(Number(event.target.value))
                    }
                  />
                </label>
              </div>
              <fieldset className="tool-allowlist">
                <legend>Allowed tools</legend>
                {defaultTools.map((toolId) => (
                  <label className="toggle-row" key={toolId}>
                    <input
                      type="checkbox"
                      checked={allowedTools.includes(toolId)}
                      onChange={() => toggleTool(toolId)}
                    />
                    {toolId}
                  </label>
                ))}
              </fieldset>
              <button
                className="command-button"
                type="button"
                disabled={busy || allowedTools.length === 0}
                onClick={() => void startRun()}
              >
                {busy ? (
                  <Loader2 size={18} aria-hidden="true" />
                ) : (
                  <Workflow size={18} aria-hidden="true" />
                )}
                Start Run
              </button>
              {error ? <p className="form-error">{error}</p> : null}
            </section>

            <section
              className="run-list-panel"
              aria-labelledby="run-list-title"
            >
              <div className="section-header">
                <h2 className="section-title" id="run-list-title">
                  Runs
                </h2>
                <select
                  aria-label="Filter by state"
                  value={stateFilter}
                  onChange={(event) => {
                    const next = event.target.value;
                    setStateFilter(next);
                    void refreshRuns(next);
                  }}
                >
                  <option value="">All states</option>
                  <option value="request_tool_approval">
                    Waiting approval
                  </option>
                  <option value="complete">Complete</option>
                  <option value="failed">Failed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <div className="run-table" aria-live="polite">
                {runs?.items.length ? (
                  runs.items.map((run) => (
                    <button
                      key={run.id}
                      type="button"
                      aria-pressed={activeRun?.id === run.id}
                      onClick={() => void selectRun(run)}
                    >
                      <span>
                        <strong>{run.owner_request ?? "Untitled run"}</strong>
                        <small>
                          {run.id.slice(0, 8)} · {run.model}
                        </small>
                      </span>
                      <StatusPill tone={stateTone(run.state)}>
                        {run.state}
                      </StatusPill>
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    <Workflow size={22} aria-hidden="true" />
                    <p>No agent runs match this filter.</p>
                  </div>
                )}
              </div>
            </section>

            <section
              className="run-inspector"
              aria-live="polite"
              aria-labelledby="run-inspector-title"
            >
              <div className="section-header">
                <h2 className="section-title" id="run-inspector-title">
                  Inspector
                </h2>
                {activeRun ? (
                  <StatusPill tone={stateTone(activeRun.state)}>
                    {activeRun.state}
                  </StatusPill>
                ) : null}
              </div>
              {activeRun ? (
                <>
                  <div className="run-actions">
                    <button
                      type="button"
                      disabled={
                        busy ||
                        ["complete", "failed", "cancelled"].includes(
                          activeRun.state,
                        )
                      }
                      onClick={() => void cancelActiveRun()}
                    >
                      <CircleStop size={17} aria-hidden="true" />
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={busy || activeRun.state !== "failed"}
                      onClick={() => void retryActiveRun()}
                    >
                      <RefreshCw size={17} aria-hidden="true" />
                      Retry
                    </button>
                  </div>
                  <RunStats run={activeRun} />
                  <ApprovalList
                    approvals={activeRun.approvals}
                    busy={busy}
                    onApprove={approve}
                    onDeny={deny}
                  />
                  <ToolList toolCalls={activeRun.tool_calls} />
                  <Timeline run={activeRun} />
                  <section>
                    <h3 className="section-title">Result</h3>
                    <pre className="debug-block">
                      {JSON.stringify(activeRun.sanitized_output, null, 2)}
                    </pre>
                  </section>
                </>
              ) : (
                <div className="empty-state">
                  <Workflow size={22} aria-hidden="true" />
                  <p>Select or start a run to inspect its timeline.</p>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function RunStats({ run }: { run: AgentRunDetail }) {
  return (
    <div className="run-stat-grid">
      <div>
        <span>Trace</span>
        <strong>{run.trace_id?.slice(0, 12) ?? "none"}</strong>
      </div>
      <div>
        <span>Latency</span>
        <strong>{run.latency_ms ?? 0}ms</strong>
      </div>
      <div>
        <span>Tokens</span>
        <strong>{String(run.usage.total_tokens ?? 0)}</strong>
      </div>
      <div>
        <span>Cost</span>
        <strong>${String(run.usage.estimated_cost_usd ?? 0)}</strong>
      </div>
    </div>
  );
}

function ApprovalList({
  approvals,
  busy,
  onApprove,
  onDeny,
}: {
  approvals: AgentApproval[];
  busy: boolean;
  onApprove: (approval: AgentApproval) => Promise<void>;
  onDeny: (approval: AgentApproval) => Promise<void>;
}) {
  return (
    <section>
      <h3 className="section-title">Approvals</h3>
      {approvals.length === 0 ? (
        <p className="item-meta">No approval requests for this run.</p>
      ) : (
        <div className="approval-stack">
          {approvals.map((approval) => (
            <article className="approval-card" key={approval.id}>
              <div className="result-card__head">
                <div>
                  <p className="item-title">{approval.tool_id}</p>
                  <p className="item-meta">
                    {approval.risk_class} ·{" "}
                    {approval.arguments_hash?.slice(0, 16)}
                  </p>
                </div>
                <StatusPill tone={approvalTone(approval.status)}>
                  {approval.status}
                </StatusPill>
              </div>
              <pre className="debug-block">
                {JSON.stringify(approval.approval_metadata, null, 2)}
              </pre>
              <div className="approval-actions">
                <button
                  type="button"
                  disabled={busy || approval.status !== "pending"}
                  onClick={() => void onApprove(approval)}
                >
                  <Check size={17} aria-hidden="true" />
                  Approve
                </button>
                <button
                  type="button"
                  disabled={busy || approval.status !== "pending"}
                  onClick={() => void onDeny(approval)}
                >
                  <X size={17} aria-hidden="true" />
                  Deny
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ToolList({ toolCalls }: { toolCalls: AgentToolCall[] }) {
  return (
    <section>
      <h3 className="section-title">Tools</h3>
      {toolCalls.length === 0 ? (
        <p className="item-meta">No tool calls were selected.</p>
      ) : (
        <div className="tool-stack">
          {toolCalls.map((toolCall) => (
            <article className="tool-card" key={toolCall.id}>
              <div className="result-card__head">
                <div>
                  <p className="item-title">{toolCall.tool_id}</p>
                  <p className="item-meta">
                    {toolCall.risk_class} ·{" "}
                    {toolCall.arguments_hash?.slice(0, 16)}
                  </p>
                </div>
                <StatusPill tone={toolTone(toolCall.status)}>
                  {toolCall.status}
                </StatusPill>
              </div>
              <div className="tool-json-grid">
                <pre className="debug-block">
                  {JSON.stringify(toolCall.redacted_arguments, null, 2)}
                </pre>
                <pre className="debug-block">
                  {JSON.stringify(toolCall.redacted_result, null, 2)}
                </pre>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Timeline({ run }: { run: AgentRunDetail }) {
  return (
    <section>
      <h3 className="section-title">Timeline</h3>
      <ol className="run-timeline">
        {run.events.map((event) => (
          <li key={event.id}>
            <span>{event.sequence_number}</span>
            <div>
              <strong>{event.event_type}</strong>
              <small>{new Date(event.created_at).toLocaleTimeString()}</small>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function stateTone(state: string): "neutral" | "good" | "warn" | "bad" {
  if (state === "complete") {
    return "good";
  }
  if (state === "failed") {
    return "bad";
  }
  if (state === "cancelled" || state === "request_tool_approval") {
    return "warn";
  }
  return "neutral";
}

function approvalTone(status: string): "neutral" | "good" | "warn" | "bad" {
  if (status === "approved") {
    return "good";
  }
  if (status === "denied" || status === "expired") {
    return "bad";
  }
  return "warn";
}

function toolTone(status: string): "neutral" | "good" | "warn" | "bad" {
  if (status === "succeeded") {
    return "good";
  }
  if (status === "failed" || status === "denied") {
    return "bad";
  }
  if (status === "approval_required" || status === "running") {
    return "warn";
  }
  return "neutral";
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
