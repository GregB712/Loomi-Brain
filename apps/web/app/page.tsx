import {
  Activity,
  Bot,
  BrainCircuit,
  Database,
  FileText,
  Gauge,
  Home,
  KeyRound,
  Library,
  MessageSquare,
  Plug,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { MetricCard, StatusPill } from "@loomi/ui";

const navigation = [
  { label: "Home", icon: Home, current: true, href: "/" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  { label: "Knowledge", icon: Library, href: "/knowledge" },
  { label: "Search", icon: Search, href: "/search" },
  { label: "Runs", icon: Workflow, href: "#" },
  { label: "Skills", icon: Sparkles, href: "#" },
  { label: "MCP", icon: Plug, href: "#" },
  { label: "Observability", icon: Activity, href: "#" },
  { label: "Settings", icon: KeyRound, href: "#" },
];

const pipeline = [
  {
    title: "Foundation slice",
    meta: "Owner auth, health, migrations, local services, CI",
    tone: "good" as const,
    status: "Ready",
  },
  {
    title: "Knowledge ingestion",
    meta: "Upload, scan, parse, chunk, embed, index",
    tone: "good" as const,
    status: "Ready",
  },
  {
    title: "Cited chat",
    meta: "Hybrid retrieval, mock LLM mode, citation validation",
    tone: "good" as const,
    status: "Ready",
  },
];

const runs = [
  {
    title: "Design verification",
    meta: "Docs, ADRs, threat model, and implementation plan are linked",
    tone: "good" as const,
    status: "Clean",
  },
  {
    title: "Owner boundary",
    meta: "Server-side sessions, CSRF, revocation, and scoped resources",
    tone: "good" as const,
    status: "Guarded",
  },
  {
    title: "Provider gateway",
    meta: "Adapter contract begins after ingestion and retrieval slices",
    tone: "warn" as const,
    status: "Pending",
  },
  {
    title: "MCP safety",
    meta: "Registry and approval policy defined in ADR 0005",
    tone: "neutral" as const,
    status: "Planned",
  },
];

export default function DashboardPage() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <BrainCircuit size={23} strokeWidth={1.8} />
          </div>
          <div>
            <p className="brand-title">Loomi-Brain</p>
            <p className="brand-subtitle">Owner workspace</p>
          </div>
        </div>

        <nav>
          <ul className="nav-list">
            {navigation.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.label}>
                  <a
                    className="nav-link"
                    href={item.href}
                    aria-current={item.current ? "page" : undefined}
                  >
                    <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                    <span>{item.label}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Secure second brain</p>
            <h1>Private knowledge, cited answers, controlled agents.</h1>
            <p className="topbar-copy">
              A single-owner workspace for document intelligence, hybrid
              retrieval, model observability, MCP approvals, and safe
              declarative skills.
            </p>
          </div>

          <section
            className="environment-panel"
            aria-label="Environment status"
          >
            <p className="panel-label">Phase</p>
            <p className="panel-value">Search + Chat</p>
            <StatusPill tone="good">Phase 3</StatusPill>
          </section>
        </header>

        <div className="dashboard-grid">
          <section className="metrics" aria-label="Workspace metrics">
            <MetricCard
              label="Documents"
              value="0"
              detail="Owner uploads are available in Knowledge"
              icon={<FileText size={21} strokeWidth={1.8} />}
            />
            <MetricCard
              label="Retrieval modes"
              value="3"
              detail="Lexical, semantic, hybrid"
              icon={<Search size={21} strokeWidth={1.8} />}
            />
            <MetricCard
              label="Agent states"
              value="10"
              detail="Bounded state machine"
              icon={<Bot size={21} strokeWidth={1.8} />}
            />
            <MetricCard
              label="Security gates"
              value="8"
              detail="Auth, upload, SSRF, MCP, skills"
              icon={<ShieldCheck size={21} strokeWidth={1.8} />}
            />
          </section>

          <section className="workstream" aria-labelledby="workstream-title">
            <div className="section-header">
              <h2 className="section-title" id="workstream-title">
                Workstream
              </h2>
              <Gauge size={18} strokeWidth={1.8} aria-hidden="true" />
            </div>
            <ul className="pipeline-list">
              {pipeline.map((item) => (
                <li className="pipeline-item" key={item.title}>
                  <div>
                    <p className="item-title">{item.title}</p>
                    <p className="item-meta">{item.meta}</p>
                  </div>
                  <StatusPill tone={item.tone}>{item.status}</StatusPill>
                </li>
              ))}
            </ul>
          </section>

          <section className="runs" aria-labelledby="runs-title">
            <div className="section-header">
              <h2 className="section-title" id="runs-title">
                Run Signals
              </h2>
              <Database size={18} strokeWidth={1.8} aria-hidden="true" />
            </div>
            <ul className="run-list">
              {runs.map((item) => (
                <li className="run-item" key={item.title}>
                  <div>
                    <p className="item-title">{item.title}</p>
                    <p className="item-meta">{item.meta}</p>
                  </div>
                  <StatusPill tone={item.tone}>{item.status}</StatusPill>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}
