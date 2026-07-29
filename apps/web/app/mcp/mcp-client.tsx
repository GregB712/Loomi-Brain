"use client";

import {
  createLoomiClient,
  type AgentRunDetail,
  type MCPCapability,
  type MCPRiskClass,
  type MCPServer,
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  AlertTriangle,
  BrainCircuit,
  Check,
  CircleStop,
  DatabaseZap,
  Home,
  KeyRound,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  Plug,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const navigation = [
  { label: "Home", icon: Home, href: "/" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  { label: "Knowledge", icon: Library, href: "/knowledge" },
  { label: "Search", icon: Search, href: "/search" },
  { label: "Runs", icon: Workflow, href: "/runs" },
  { label: "MCP", icon: Plug, href: "/mcp", current: true },
];

const riskOptions: MCPRiskClass[] = [
  "read-only",
  "local-mutation",
  "external-mutation",
  "credential-sensitive",
  "destructive",
];

export function MCPClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [activeServer, setActiveServer] = useState<MCPServer | null>(null);
  const [auditItems, setAuditItems] = useState<
    Array<{
      id: string;
      event_type: string;
      request_id: string | null;
      trace_id: string | null;
      metadata: Record<string, unknown>;
      created_at: string;
    }>
  >([]);
  const [newName, setNewName] = useState("Loomi test MCP");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<AgentRunDetail | null>(null);

  async function login() {
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.login(email, password);
      setCsrfToken(response.csrf_token);
      setPassword("");
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshAll() {
    const [serverList, audit] = await Promise.all([
      apiClient.listMcpServers(new URLSearchParams({ limit: "50" })),
      apiClient.mcpAudit(new URLSearchParams({ limit: "50" })),
    ]);
    setServers(serverList.items);
    setAuditItems(audit.items);
    const selected =
      serverList.items.find((server) => server.id === activeServer?.id) ??
      serverList.items[0] ??
      null;
    if (selected) {
      setActiveServer(await apiClient.getMcpServer(selected.id));
    } else {
      setActiveServer(null);
    }
  }

  async function createTestServer() {
    if (!csrfToken || !newName.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await apiClient.createMcpServer(csrfToken, {
        name: newName.trim(),
        description: description.trim() || null,
        transport: "stdio",
        template_name: "loomi-test",
        output_size_limit: 12000,
      });
      setActiveServer(await apiClient.getMcpServer(created.id));
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Create failed.");
    } finally {
      setBusy(false);
    }
  }

  async function serverAction(
    server: MCPServer,
    action: "test" | "refresh" | "enable" | "disable" | "delete",
  ) {
    if (!csrfToken) {
      return;
    }
    if (
      action === "delete" &&
      !window.confirm(
        `Delete MCP server "${server.name}" and its cached policies?`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (action === "test") {
        await apiClient.testMcpConnection(server.id, csrfToken);
      } else if (action === "refresh") {
        await apiClient.refreshMcpCapabilities(server.id, csrfToken);
      } else if (action === "delete") {
        await apiClient.deleteMcpServer(server.id, csrfToken, server.name);
      } else {
        await apiClient.setMcpServerEnabled(
          server.id,
          csrfToken,
          action === "enable",
        );
      }
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function updatePolicy(capability: MCPCapability, payload: PolicyState) {
    if (!csrfToken) {
      return;
    }
    const broadening =
      (payload.enabled && !capability.enabled) ||
      (capability.risk_class !== "read-only" &&
        payload.riskClass === "read-only") ||
      (capability.approval_policy !== "never" &&
        payload.approvalPolicy === "never");
    if (
      broadening &&
      !window.confirm(
        "This broadens MCP tool access for the agent runtime. Continue?",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.updateMcpCapabilityPolicy(capability.id, csrfToken, {
        enabled: payload.enabled,
        risk_class: payload.riskClass,
        approval_policy: payload.approvalPolicy,
        expected_side_effects: payload.expectedSideEffects,
        confirm_broadening: true,
      });
      if (activeServer) {
        setActiveServer(await apiClient.getMcpServer(activeServer.id));
      }
      await refreshAll();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Policy update failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function invokeCapability(
    capability: MCPCapability,
    args: Record<string, unknown>,
  ) {
    if (!csrfToken || !activeServer) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await apiClient.invokeMcpCapability(
        activeServer.id,
        capability.id,
        csrfToken,
        { arguments: args },
      );
      setLastRun(run);
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Invocation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function decideApproval(run: AgentRunDetail, approve: boolean) {
    if (!csrfToken) {
      return;
    }
    const pending = run.approvals.find(
      (approval) => approval.status === "pending",
    );
    if (!pending) {
      return;
    }
    setBusy(true);
    try {
      const next = approve
        ? await apiClient.approveAgentToolCall(run.id, pending.id, csrfToken)
        : await apiClient.denyAgentToolCall(
            run.id,
            pending.id,
            csrfToken,
            "Denied from MCP console.",
          );
      setLastRun(next);
      await refreshAll();
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
            <p className="brand-subtitle">MCP boundary</p>
          </div>
        </div>
        <nav>
          <ul className="nav-list">
            {navigation.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.label}>
                  <Link
                    className="nav-link"
                    href={item.href}
                    aria-current={item.current ? "page" : undefined}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      <main className="main">
        <header className="knowledge-header">
          <div>
            <p className="eyebrow">Secure MCP client</p>
            <h1>Approved tools, explicit policy, visible execution.</h1>
            <p className="topbar-copy">
              Register MCP servers, inspect untrusted capabilities, enable exact
              tools, and route execution through the agent approval state
              machine.
            </p>
          </div>
          <section className="environment-panel" aria-label="MCP status">
            <p className="panel-label">Servers</p>
            <p className="panel-value">{servers.length}</p>
            <StatusPill
              tone={
                servers.some((server) => server.enabled) ? "good" : "neutral"
              }
            >
              {servers.some((server) => server.enabled)
                ? "Enabled"
                : "Deny default"}
            </StatusPill>
          </section>
        </header>

        <section className="mcp-login-row" aria-label="Owner session">
          <input
            aria-label="Owner email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <input
            aria-label="Owner password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Owner password"
          />
          <button className="button-primary" onClick={login} disabled={busy}>
            {busy ? (
              <Loader2 size={16} aria-hidden="true" />
            ) : (
              <LogIn size={16} aria-hidden="true" />
            )}
            <span>{csrfToken ? "Refresh Session" : "Login"}</span>
          </button>
          {csrfToken && (
            <button
              className="button-secondary"
              onClick={refreshAll}
              disabled={busy}
            >
              <RefreshCw size={16} aria-hidden="true" />
              <span>Refresh</span>
            </button>
          )}
        </section>

        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        <div className="mcp-layout">
          <section className="mcp-panel" aria-labelledby="mcp-registry">
            <div className="section-header">
              <h2 className="section-title" id="mcp-registry">
                Registry
              </h2>
              <Plug size={18} aria-hidden="true" />
            </div>
            <div className="mcp-form">
              <label>
                Server name
                <input
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                />
              </label>
              <label>
                Description
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                />
              </label>
              <button
                className="button-primary"
                onClick={createTestServer}
                disabled={!csrfToken || busy}
              >
                <DatabaseZap size={16} aria-hidden="true" />
                <span>Add Test Server</span>
              </button>
            </div>
            <div className="mcp-server-list">
              {servers.map((server) => (
                <MCPServerCard
                  key={server.id}
                  server={server}
                  active={server.id === activeServer?.id}
                  onSelect={() => setActiveServer(server)}
                  onAction={(action) => serverAction(server, action)}
                  disabled={!csrfToken || busy}
                />
              ))}
            </div>
          </section>

          <section
            className="mcp-panel mcp-panel-wide"
            aria-labelledby="mcp-capabilities"
          >
            <div className="section-header">
              <h2 className="section-title" id="mcp-capabilities">
                Capabilities
              </h2>
              <ShieldCheck size={18} aria-hidden="true" />
            </div>
            {activeServer ? (
              <>
                <ConnectionStatus server={activeServer} />
                <CapabilityList
                  capabilities={activeServer.capabilities ?? []}
                  onPolicy={updatePolicy}
                  onInvoke={invokeCapability}
                  disabled={!csrfToken || busy}
                />
              </>
            ) : (
              <p className="empty-copy">Register or select an MCP server.</p>
            )}
          </section>

          <section className="mcp-panel" aria-labelledby="mcp-audit">
            <div className="section-header">
              <h2 className="section-title" id="mcp-audit">
                Audit
              </h2>
              <KeyRound size={18} aria-hidden="true" />
            </div>
            <MCPApprovalDetails
              run={lastRun}
              onDecision={decideApproval}
              disabled={busy}
            />
            <MCPAuditTable items={auditItems} />
          </section>
        </div>
      </main>
    </div>
  );
}

type ServerAction = "test" | "refresh" | "enable" | "disable" | "delete";

type PolicyState = {
  enabled: boolean;
  riskClass: MCPRiskClass;
  approvalPolicy: "never" | "risk-based" | "always";
  expectedSideEffects: string;
};

function MCPServerCard({
  server,
  active,
  onSelect,
  onAction,
  disabled,
}: {
  server: MCPServer;
  active: boolean;
  onSelect: () => void;
  onAction: (action: ServerAction) => void;
  disabled: boolean;
}) {
  return (
    <article className={`mcp-server-card ${active ? "is-active" : ""}`}>
      <button className="mcp-server-select" onClick={onSelect}>
        <span>{server.name}</span>
        <ConnectionStatus server={server} compact />
      </button>
      <p>{server.description || "Stdio template server"}</p>
      <div className="mcp-card-actions">
        <button
          onClick={() => onAction("test")}
          disabled={disabled}
          title="Test connection"
        >
          <Check size={15} aria-hidden="true" />
        </button>
        <button
          onClick={() => onAction("refresh")}
          disabled={disabled}
          title="Refresh capabilities"
        >
          <RefreshCw size={15} aria-hidden="true" />
        </button>
        <button
          onClick={() => onAction(server.enabled ? "disable" : "enable")}
          disabled={disabled}
          title={server.enabled ? "Disable server" : "Enable server"}
        >
          <CircleStop size={15} aria-hidden="true" />
        </button>
        <button
          onClick={() => onAction("delete")}
          disabled={disabled}
          title="Delete server"
        >
          <Trash2 size={15} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

function ConnectionStatus({
  server,
  compact = false,
}: {
  server: MCPServer;
  compact?: boolean;
}) {
  const tone =
    server.health_status === "connected"
      ? "good"
      : server.health_status === "failed"
        ? "bad"
        : "neutral";
  return (
    <span className={`mcp-connection ${compact ? "compact" : ""}`}>
      <StatusPill tone={tone}>
        {server.enabled ? server.health_status : "disabled"}
      </StatusPill>
      {!compact && <span>{server.health_detail || server.transport}</span>}
    </span>
  );
}

function CapabilityList({
  capabilities,
  onPolicy,
  onInvoke,
  disabled,
}: {
  capabilities: MCPCapability[];
  onPolicy: (capability: MCPCapability, payload: PolicyState) => void;
  onInvoke: (capability: MCPCapability, args: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  if (!capabilities.length) {
    return (
      <p className="empty-copy">
        Refresh capabilities to inspect tools, resources, and prompts.
      </p>
    );
  }
  return (
    <div className="mcp-capability-list">
      {capabilities.map((capability) => (
        <article className="mcp-capability" key={capability.id}>
          <div className="mcp-capability-head">
            <div>
              <p className="item-title">
                {capability.title || capability.name}
              </p>
              <p className="item-meta">
                {capability.capability_type} · {capability.name}
              </p>
            </div>
            <RiskBadge
              risk={capability.risk_class}
              enabled={capability.enabled}
            />
          </div>
          <p className="mcp-description">
            {capability.description || "No description supplied."}
          </p>
          {capability.capability_type === "tool" ? (
            <ToolPolicyEditor
              capability={capability}
              onSave={(payload) => onPolicy(capability, payload)}
              onInvoke={(args) => onInvoke(capability, args)}
              disabled={disabled}
            />
          ) : (
            <p className="mcp-muted">
              Display-only metadata. It is never executed or trusted.
            </p>
          )}
        </article>
      ))}
    </div>
  );
}

function ToolPolicyEditor({
  capability,
  onSave,
  onInvoke,
  disabled,
}: {
  capability: MCPCapability;
  onSave: (payload: PolicyState) => void;
  onInvoke: (args: Record<string, unknown>) => void;
  disabled: boolean;
}) {
  const [enabled, setEnabled] = useState(capability.enabled);
  const [riskClass, setRiskClass] = useState<MCPRiskClass>(
    capability.risk_class,
  );
  const [approvalPolicy, setApprovalPolicy] = useState<
    "never" | "risk-based" | "always"
  >(capability.approval_policy);
  const [sideEffects, setSideEffects] = useState(
    String(capability.metadata.expected_side_effects ?? ""),
  );
  const [args, setArgs] = useState(defaultArgs(capability.name));
  const [parseError, setParseError] = useState<string | null>(null);

  function invoke() {
    try {
      const parsed = JSON.parse(args) as Record<string, unknown>;
      setParseError(null);
      onInvoke(parsed);
    } catch {
      setParseError("Arguments must be a JSON object.");
    }
  }

  return (
    <div className="mcp-policy-editor">
      <label className="mcp-toggle">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        Enabled
      </label>
      <label>
        Risk
        <select
          value={riskClass}
          onChange={(event) => setRiskClass(event.target.value as MCPRiskClass)}
        >
          {riskOptions.map((risk) => (
            <option key={risk} value={risk}>
              {risk}
            </option>
          ))}
        </select>
      </label>
      <label>
        Approval
        <select
          value={approvalPolicy}
          onChange={(event) =>
            setApprovalPolicy(
              event.target.value as "never" | "risk-based" | "always",
            )
          }
        >
          <option value="never">never</option>
          <option value="risk-based">risk-based</option>
          <option value="always">always</option>
        </select>
      </label>
      <label className="mcp-editor-wide">
        Expected side effects
        <input
          value={sideEffects}
          onChange={(event) => setSideEffects(event.target.value)}
        />
      </label>
      <div className="mcp-editor-actions">
        <button
          className="button-secondary"
          disabled={disabled}
          onClick={() =>
            onSave({
              enabled,
              riskClass,
              approvalPolicy,
              expectedSideEffects: sideEffects,
            })
          }
        >
          <ShieldCheck size={15} aria-hidden="true" />
          <span>Save Policy</span>
        </button>
      </div>
      <label className="mcp-editor-wide">
        Test arguments
        <textarea
          value={args}
          onChange={(event) => setArgs(event.target.value)}
          rows={3}
        />
      </label>
      {parseError && <p className="mcp-error-text">{parseError}</p>}
      <button
        className="button-primary"
        disabled={disabled || !enabled}
        onClick={invoke}
      >
        <Plug size={15} aria-hidden="true" />
        <span>Invoke Via Agent</span>
      </button>
    </div>
  );
}

function RiskBadge({
  risk,
  enabled,
}: {
  risk: MCPRiskClass;
  enabled: boolean;
}) {
  const tone =
    risk === "read-only" ? "good" : risk === "local-mutation" ? "warn" : "bad";
  return (
    <span className="mcp-risk">
      {risk === "read-only" ? (
        <ShieldCheck size={14} aria-hidden="true" />
      ) : (
        <ShieldAlert size={14} aria-hidden="true" />
      )}
      <StatusPill tone={enabled ? tone : "neutral"}>
        {enabled ? risk : "disabled"}
      </StatusPill>
    </span>
  );
}

function MCPApprovalDetails({
  run,
  onDecision,
  disabled,
}: {
  run: AgentRunDetail | null;
  onDecision: (run: AgentRunDetail, approve: boolean) => void;
  disabled: boolean;
}) {
  if (!run) {
    return <p className="empty-copy">No MCP invocation selected.</p>;
  }
  const pending = run.approvals.find(
    (approval) => approval.status === "pending",
  );
  return (
    <div className="mcp-approval">
      <div>
        <p className="item-title">Last run</p>
        <p className="item-meta">
          {run.state} · {run.status_reason || "pending"}
        </p>
      </div>
      {pending ? (
        <>
          <div className="mcp-approval-warning">
            <AlertTriangle size={16} aria-hidden="true" />
            <span>
              {pending.tool_id} · {pending.risk_class}
            </span>
          </div>
          <div className="mcp-editor-actions">
            <button
              className="button-primary"
              disabled={disabled}
              onClick={() => onDecision(run, true)}
            >
              <Check size={15} aria-hidden="true" />
              <span>Approve</span>
            </button>
            <button
              className="button-secondary"
              disabled={disabled}
              onClick={() => onDecision(run, false)}
            >
              <CircleStop size={15} aria-hidden="true" />
              <span>Deny</span>
            </button>
          </div>
        </>
      ) : (
        <pre className="mcp-json">
          {JSON.stringify(run.tool_calls[0]?.redacted_result ?? {}, null, 2)}
        </pre>
      )}
    </div>
  );
}

function MCPAuditTable({
  items,
}: {
  items: Array<{
    id: string;
    event_type: string;
    request_id: string | null;
    trace_id: string | null;
    metadata: Record<string, unknown>;
    created_at: string;
  }>;
}) {
  return (
    <div className="mcp-audit-table">
      {items.map((item) => (
        <div className="mcp-audit-row" key={item.id}>
          <div>
            <p className="item-title">{item.event_type}</p>
            <p className="item-meta">
              {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
          <code>
            {String(item.metadata.server_name ?? item.trace_id ?? "mcp")}
          </code>
        </div>
      ))}
    </div>
  );
}

function defaultArgs(name: string) {
  if (name === "echo") {
    return JSON.stringify({ text: "hello from Loomi" }, null, 2);
  }
  if (name === "add") {
    return JSON.stringify({ a: 2, b: 3 }, null, 2);
  }
  if (name === "search_notes") {
    return JSON.stringify({ query: "policy" }, null, 2);
  }
  if (name === "risky_write") {
    return JSON.stringify({ target: "synthetic" }, null, 2);
  }
  return "{}";
}

function resolveApiBase() {
  if (typeof window === "undefined") {
    return API_BASE;
  }
  try {
    const configured = new URL(API_BASE);
    if (
      configured.hostname === "127.0.0.1" ||
      configured.hostname === "localhost"
    ) {
      return API_BASE;
    }
    return `${window.location.protocol}//${configured.host}`;
  } catch {
    return API_BASE;
  }
}
