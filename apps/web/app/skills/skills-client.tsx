"use client";

import {
  createLoomiClient,
  type AgentRunDetail,
  type SkillDetail,
  type SkillDryRunResponse,
  type SkillImportResponse,
  type SkillStarterTemplate,
  type SkillTest,
  type SkillTestRun,
  type SkillValidationResult,
  type SkillVersion,
} from "@loomi/contracts";
import { StatusPill } from "@loomi/ui";
import {
  Archive,
  Beaker,
  BrainCircuit,
  CheckCircle2,
  Code2,
  Copy,
  Download,
  GitCompare,
  Home,
  KeyRound,
  Library,
  Loader2,
  LogIn,
  MessageSquare,
  PackagePlus,
  Play,
  Plug,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Workflow,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const navigation = [
  { label: "Home", icon: Home, href: "/" },
  { label: "Chat", icon: MessageSquare, href: "/chat" },
  { label: "Knowledge", icon: Library, href: "/knowledge" },
  { label: "Search", icon: Search, href: "/search" },
  { label: "Runs", icon: Workflow, href: "/runs" },
  { label: "Skills", icon: Sparkles, href: "/skills", current: true },
  { label: "MCP", icon: Plug, href: "/mcp" },
];

const builtinTools = [
  "knowledge.search",
  "knowledge.get_document_metadata",
  "knowledge.get_source_excerpt",
  "calculator",
  "notes.create_draft",
];

type FormState = {
  name: string;
  version: string;
  description: string;
  promptTemplate: string;
  inputField: string;
  outputField: string;
  retrievalMode: "none" | "lexical" | "semantic" | "hybrid";
  topK: number;
  modelCapability: "fast" | "balanced" | "reasoning";
  maxInputTokens: number;
  maxOutputTokens: number;
  maxSteps: number;
  maxToolCalls: number;
  timeoutSeconds: number;
  allowedTools: string[];
};

const defaultForm: FormState = {
  name: "calculator-skill",
  version: "1.0.0",
  description: "Calculate a synthetic expression with a safe runtime tool.",
  promptTemplate: "Calculate {{ input.expression }}.",
  inputField: "expression",
  outputField: "answer_text",
  retrievalMode: "none",
  topK: 0,
  modelCapability: "reasoning",
  maxInputTokens: 12000,
  maxOutputTokens: 2000,
  maxSteps: 6,
  maxToolCalls: 3,
  timeoutSeconds: 120,
  allowedTools: ["calculator"],
};

export function SkillsClient() {
  const apiClient = useMemo(() => createLoomiClient(resolveApiBase()), []);
  const [email, setEmail] = useState("owner@loomi.local");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillDetail[]>([]);
  const [activeSkill, setActiveSkill] = useState<SkillDetail | null>(null);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [starters, setStarters] = useState<SkillStarterTemplate[]>([]);
  const [form, setForm] = useState<FormState>(defaultForm);
  const [manifestText, setManifestText] = useState(
    prettyJson(manifestFromForm(defaultForm)),
  );
  const [validation, setValidation] = useState<SkillValidationResult | null>(
    null,
  );
  const [dryRun, setDryRun] = useState<SkillDryRunResponse | null>(null);
  const [tests, setTests] = useState<SkillTest[]>([]);
  const [testRun, setTestRun] = useState<SkillTestRun | null>(null);
  const [lastRun, setLastRun] = useState<AgentRunDetail | null>(null);
  const [diff, setDiff] = useState<Record<string, unknown> | null>(null);
  const [importReview, setImportReview] = useState<SkillImportResponse | null>(
    null,
  );
  const [exportText, setExportText] = useState("");
  const [dryRunInput, setDryRunInput] = useState(
    prettyJson({ expression: "2 + 2" }),
  );
  const [executeInput, setExecuteInput] = useState(
    prettyJson({ expression: "2 + 2" }),
  );
  const [testFixture, setTestFixture] = useState(
    prettyJson({
      input: { expression: "2 + 2" },
      deterministic_model_result: { answer_text: "Result: 4.", citations: [] },
    }),
  );
  const [testExpected, setTestExpected] = useState(
    prettyJson({
      validation_result: true,
      output_schema_result: true,
      policy_allowed_tools: ["calculator"],
    }),
  );
  const [importText, setImportText] = useState(
    prettyJson({
      format: "loomi.skill.bundle.v1",
      manifest: manifestFromForm(defaultForm),
      tests: [],
    }),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeVersion =
    activeSkill?.versions.find((version) => version.id === activeVersionId) ??
    activeSkill?.versions[0] ??
    null;

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
    const [skillList, starterList] = await Promise.all([
      apiClient.listSkills(new URLSearchParams({ limit: "50" })),
      apiClient.listSkillStarterTemplates(),
    ]);
    const details = await Promise.all(
      skillList.items.map((skill) => apiClient.getSkill(skill.id)),
    );
    setSkills(details);
    setStarters(starterList.items);
    const next =
      details.find((skill) => skill.id === activeSkill?.id) ??
      details[0] ??
      null;
    setActiveSkill(next);
    setActiveVersionId(
      next?.current_version_id ?? next?.versions[0]?.id ?? null,
    );
    if (next) {
      await loadTests(next.id, next.current_version_id ?? next.versions[0]?.id);
    }
  }

  async function validateManifest() {
    setBusy(true);
    setError(null);
    try {
      const manifest = parseJsonObject(manifestText);
      const result = await apiClient.validateSkillManifest(manifest);
      setValidation(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Validation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createDraft() {
    if (!csrfToken) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const manifest = parseJsonObject(manifestText);
      const created = await apiClient.createSkill(csrfToken, manifest);
      setActiveSkill(created);
      setActiveVersionId(
        created.current_version_id ?? created.versions[0]?.id ?? null,
      );
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Create failed.");
    } finally {
      setBusy(false);
    }
  }

  async function updateDraft() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await apiClient.updateSkillVersion(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
        parseJsonObject(manifestText),
      );
      setActiveSkill(updated);
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function lifecycle(action: "publish" | "archive" | "disable") {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    if (
      action === "publish" &&
      !window.confirm(
        `Publish immutable version ${activeVersion.version} of ${activeSkill.name}?`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated =
        action === "publish"
          ? await apiClient.publishSkillVersion(
              activeSkill.id,
              activeVersion.id,
              csrfToken,
            )
          : action === "archive"
            ? await apiClient.archiveSkillVersion(
                activeSkill.id,
                activeVersion.id,
                csrfToken,
              )
            : await apiClient.disableSkillVersion(
                activeSkill.id,
                activeVersion.id,
                csrfToken,
              );
      setActiveSkill(updated);
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `${action} failed.`);
    } finally {
      setBusy(false);
    }
  }

  async function cloneVersion() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    const newVersion = window.prompt("New SemVer for the draft clone", "1.0.1");
    if (!newVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await apiClient.cloneSkillVersion(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
        newVersion,
      );
      setActiveSkill(updated);
      setActiveVersionId(
        updated.current_version_id ?? updated.versions[0]?.id ?? null,
      );
      await refreshAll();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Clone failed.");
    } finally {
      setBusy(false);
    }
  }

  async function dryRunActive() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.dryRunSkillVersion(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
        { input: parseJsonObject(dryRunInput) },
      );
      setDryRun(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dry run failed.");
    } finally {
      setBusy(false);
    }
  }

  async function executeActive() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await apiClient.executeSkillVersion(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
        parseJsonObject(executeInput),
      );
      setLastRun(run);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Execution failed.");
    } finally {
      setBusy(false);
    }
  }

  async function loadTests(
    skillId: string,
    versionId: string | undefined | null,
  ) {
    if (!versionId) {
      setTests([]);
      return;
    }
    const response = await apiClient.listSkillTests(skillId, versionId);
    setTests(response.items);
  }

  async function addTest() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.createSkillTest(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
        {
          name: "Synthetic validation",
          fixture: parseJsonObject(testFixture),
          expected: parseJsonObject(testExpected),
        },
      );
      await loadTests(activeSkill.id, activeVersion.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Create test failed.");
    } finally {
      setBusy(false);
    }
  }

  async function runTests() {
    if (!csrfToken || !activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const run = await apiClient.runSkillTests(
        activeSkill.id,
        activeVersion.id,
        csrfToken,
      );
      setTestRun(run);
      await loadTests(activeSkill.id, activeVersion.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Test run failed.");
    } finally {
      setBusy(false);
    }
  }

  async function exportActive() {
    if (!activeSkill || !activeVersion) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const bundle = await apiClient.exportSkillVersion(
        activeSkill.id,
        activeVersion.id,
        false,
      );
      setExportText(prettyJson(bundle));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function reviewImport(persist: boolean) {
    if (!csrfToken) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const review = await apiClient.importSkillBundle(
        csrfToken,
        importText,
        persist,
      );
      setImportReview(review);
      if (review.skill) {
        setActiveSkill(review.skill);
        setActiveVersionId(
          review.skill.current_version_id ??
            review.skill.versions[0]?.id ??
            null,
        );
        await refreshAll();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  async function diffWith(version: SkillVersion) {
    if (!activeSkill || !activeVersion || version.id === activeVersion.id) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.diffSkillVersions(
        activeSkill.id,
        activeVersion.id,
        version.id,
      );
      setDiff(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Diff failed.");
    } finally {
      setBusy(false);
    }
  }

  function applyForm(next: FormState) {
    setForm(next);
    setManifestText(prettyJson(manifestFromForm(next)));
  }

  function loadManifest(manifest: Record<string, unknown>) {
    setManifestText(prettyJson(manifest));
    setForm(formFromManifest(manifest));
    setValidation(null);
    setDryRun(null);
  }

  function selectSkill(skill: SkillDetail) {
    const selectedVersion =
      skill.current_version_id ?? skill.versions[0]?.id ?? null;
    setActiveSkill(skill);
    setActiveVersionId(selectedVersion);
    const version = skill.versions.find((item) => item.id === selectedVersion);
    if (version) {
      loadManifest(version.manifest);
      void loadTests(skill.id, version.id);
    }
  }

  function selectVersion(version: SkillVersion) {
    setActiveVersionId(version.id);
    loadManifest(version.manifest);
    if (activeSkill) {
      void loadTests(activeSkill.id, version.id);
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
            <p className="brand-subtitle">Skill editor</p>
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
            <p className="eyebrow">Declarative skills</p>
            <h1>Versioned prompts, bounded tools, deterministic tests.</h1>
            <p className="topbar-copy">
              Create safe reusable skills with strict manifests, immutable
              published versions, dry-run previews, and server-side policy
              intersection.
            </p>
          </div>
          <section className="environment-panel" aria-label="Skill status">
            <p className="panel-label">Skills</p>
            <p className="panel-value">{skills.length}</p>
            <StatusPill
              tone={activeVersion?.state === "published" ? "good" : "neutral"}
            >
              {activeVersion?.state ?? "Draft"}
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

        <div className="skills-layout">
          <section className="skill-panel" aria-labelledby="skill-library">
            <PanelHeader
              id="skill-library"
              title="Library"
              icon={<Sparkles size={18} />}
            />
            <div className="skill-list">
              {skills.map((skill) => (
                <button
                  className={`skill-list-item ${skill.id === activeSkill?.id ? "is-active" : ""}`}
                  key={skill.id}
                  onClick={() => selectSkill(skill)}
                >
                  <span>{skill.name}</span>
                  <StatusPill
                    tone={skill.state === "published" ? "good" : "neutral"}
                  >
                    {skill.current_version ?? skill.state}
                  </StatusPill>
                </button>
              ))}
              {!skills.length && (
                <p className="empty-copy">Login and create a draft skill.</p>
              )}
            </div>
            <PanelHeader
              id="skill-starters"
              title="Starters"
              icon={<PackagePlus size={18} />}
            />
            <div className="skill-starters">
              {starters.map((starter) => {
                const manifest = starter.manifest as {
                  metadata?: { name?: string; description?: string };
                };
                return (
                  <button
                    key={
                      manifest.metadata?.name ??
                      JSON.stringify(starter.manifest)
                    }
                    className="skill-starter"
                    onClick={() => loadManifest(starter.manifest)}
                  >
                    <span>{manifest.metadata?.name ?? "starter"}</span>
                    <small>
                      {manifest.metadata?.description ?? "Template manifest"}
                    </small>
                  </button>
                );
              })}
            </div>
          </section>

          <section
            className="skill-panel skill-editor-panel"
            aria-labelledby="skill-editor"
          >
            <PanelHeader
              id="skill-editor"
              title="Editor"
              icon={<Code2 size={18} />}
            />
            <div className="skill-form-grid">
              <label>
                Name
                <input
                  value={form.name}
                  onChange={(event) =>
                    applyForm({ ...form, name: event.target.value })
                  }
                />
              </label>
              <label>
                Version
                <input
                  value={form.version}
                  onChange={(event) =>
                    applyForm({ ...form, version: event.target.value })
                  }
                />
              </label>
              <label className="skill-wide">
                Description
                <input
                  value={form.description}
                  onChange={(event) =>
                    applyForm({ ...form, description: event.target.value })
                  }
                />
              </label>
              <label className="skill-wide">
                Prompt template
                <textarea
                  rows={4}
                  value={form.promptTemplate}
                  onChange={(event) =>
                    applyForm({ ...form, promptTemplate: event.target.value })
                  }
                />
              </label>
              <label>
                Input field
                <input
                  value={form.inputField}
                  onChange={(event) =>
                    applyForm({ ...form, inputField: event.target.value })
                  }
                />
              </label>
              <label>
                Output field
                <input
                  value={form.outputField}
                  onChange={(event) =>
                    applyForm({ ...form, outputField: event.target.value })
                  }
                />
              </label>
              <label>
                Retrieval
                <select
                  value={form.retrievalMode}
                  onChange={(event) =>
                    applyForm({
                      ...form,
                      retrievalMode: event.target
                        .value as FormState["retrievalMode"],
                    })
                  }
                >
                  <option value="none">none</option>
                  <option value="lexical">lexical</option>
                  <option value="semantic">semantic</option>
                  <option value="hybrid">hybrid</option>
                </select>
              </label>
              <label>
                Top K
                <input
                  type="number"
                  value={form.topK}
                  onChange={(event) =>
                    applyForm({ ...form, topK: Number(event.target.value) })
                  }
                />
              </label>
              <label>
                Capability
                <select
                  value={form.modelCapability}
                  onChange={(event) =>
                    applyForm({
                      ...form,
                      modelCapability: event.target
                        .value as FormState["modelCapability"],
                    })
                  }
                >
                  <option value="fast">fast</option>
                  <option value="balanced">balanced</option>
                  <option value="reasoning">reasoning</option>
                </select>
              </label>
              <label>
                Max steps
                <input
                  type="number"
                  value={form.maxSteps}
                  onChange={(event) =>
                    applyForm({ ...form, maxSteps: Number(event.target.value) })
                  }
                />
              </label>
              <label>
                Tool calls
                <input
                  type="number"
                  value={form.maxToolCalls}
                  onChange={(event) =>
                    applyForm({
                      ...form,
                      maxToolCalls: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label>
                Timeout
                <input
                  type="number"
                  value={form.timeoutSeconds}
                  onChange={(event) =>
                    applyForm({
                      ...form,
                      timeoutSeconds: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>

            <div className="skill-tool-grid" aria-label="Allowed tools">
              {builtinTools.map((toolId) => (
                <label key={toolId} className="skill-tool-toggle">
                  <input
                    type="checkbox"
                    checked={form.allowedTools.includes(toolId)}
                    onChange={(event) => {
                      const nextTools = event.target.checked
                        ? [...form.allowedTools, toolId]
                        : form.allowedTools.filter((tool) => tool !== toolId);
                      applyForm({ ...form, allowedTools: nextTools });
                    }}
                  />
                  <span>{toolId}</span>
                </label>
              ))}
            </div>

            <label className="skill-manifest-editor">
              Manifest JSON
              <textarea
                rows={18}
                value={manifestText}
                onChange={(event) => setManifestText(event.target.value)}
              />
            </label>
            <div className="skill-command-row">
              <button
                className="button-secondary"
                onClick={validateManifest}
                disabled={busy}
              >
                <ShieldCheck size={16} aria-hidden="true" />
                <span>Validate</span>
              </button>
              <button
                className="button-primary"
                onClick={createDraft}
                disabled={!csrfToken || busy}
              >
                <Save size={16} aria-hidden="true" />
                <span>Create Draft</span>
              </button>
              <button
                className="button-secondary"
                onClick={updateDraft}
                disabled={
                  !csrfToken ||
                  !activeVersion ||
                  activeVersion.state !== "draft" ||
                  busy
                }
              >
                <Save size={16} aria-hidden="true" />
                <span>Update Draft</span>
              </button>
            </div>
            <ValidationPanel validation={validation} />
          </section>

          <section className="skill-panel" aria-labelledby="skill-policy">
            <PanelHeader
              id="skill-policy"
              title="Policy"
              icon={<ShieldCheck size={18} />}
            />
            <VersionHistory
              versions={activeSkill?.versions ?? []}
              activeVersionId={activeVersion?.id ?? null}
              onSelect={selectVersion}
              onDiff={diffWith}
            />
            <div className="skill-command-row skill-command-stack">
              <button
                className="button-primary"
                onClick={() => lifecycle("publish")}
                disabled={
                  !csrfToken ||
                  !activeVersion ||
                  activeVersion.state !== "draft" ||
                  busy
                }
              >
                <CheckCircle2 size={16} aria-hidden="true" />
                <span>Publish</span>
              </button>
              <button
                className="button-secondary"
                onClick={cloneVersion}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <Copy size={16} aria-hidden="true" />
                <span>Clone Version</span>
              </button>
              <button
                className="button-secondary"
                onClick={() => lifecycle("disable")}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <XCircle size={16} aria-hidden="true" />
                <span>Disable</span>
              </button>
              <button
                className="button-secondary"
                onClick={() => lifecycle("archive")}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <Archive size={16} aria-hidden="true" />
                <span>Archive</span>
              </button>
            </div>
            <JsonBlock title="Version diff" value={diff} />
          </section>

          <section
            className="skill-panel skill-editor-panel"
            aria-labelledby="skill-runner"
          >
            <PanelHeader
              id="skill-runner"
              title="Dry Run And Execute"
              icon={<Play size={18} />}
            />
            <div className="skill-run-grid">
              <label>
                Dry-run input
                <textarea
                  rows={7}
                  value={dryRunInput}
                  onChange={(event) => setDryRunInput(event.target.value)}
                />
              </label>
              <label>
                Execute input
                <textarea
                  rows={7}
                  value={executeInput}
                  onChange={(event) => setExecuteInput(event.target.value)}
                />
              </label>
            </div>
            <div className="skill-command-row">
              <button
                className="button-secondary"
                onClick={dryRunActive}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <ShieldCheck size={16} aria-hidden="true" />
                <span>Dry Run</span>
              </button>
              <button
                className="button-primary"
                onClick={executeActive}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <Play size={16} aria-hidden="true" />
                <span>Execute</span>
              </button>
            </div>
            <JsonBlock title="Dry-run preview" value={dryRun} />
            <JsonBlock title="Last run" value={lastRun} />
          </section>

          <section className="skill-panel" aria-labelledby="skill-tests">
            <PanelHeader
              id="skill-tests"
              title="Tests"
              icon={<Beaker size={18} />}
            />
            <label className="skill-manifest-editor">
              Fixture
              <textarea
                rows={7}
                value={testFixture}
                onChange={(event) => setTestFixture(event.target.value)}
              />
            </label>
            <label className="skill-manifest-editor">
              Expected
              <textarea
                rows={7}
                value={testExpected}
                onChange={(event) => setTestExpected(event.target.value)}
              />
            </label>
            <div className="skill-command-row">
              <button
                className="button-secondary"
                onClick={addTest}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <Save size={16} aria-hidden="true" />
                <span>Add Test</span>
              </button>
              <button
                className="button-primary"
                onClick={runTests}
                disabled={!csrfToken || !activeVersion || busy}
              >
                <Beaker size={16} aria-hidden="true" />
                <span>Run Tests</span>
              </button>
            </div>
            <div className="skill-test-list">
              {tests.map((test) => (
                <div className="skill-test-row" key={test.id}>
                  <span>{test.name}</span>
                  <small>
                    {Object.keys(test.fixture).join(", ") || "empty fixture"}
                  </small>
                </div>
              ))}
            </div>
            <JsonBlock title="Last test run" value={testRun} />
          </section>

          <section className="skill-panel" aria-labelledby="skill-portability">
            <PanelHeader
              id="skill-portability"
              title="Import / Export"
              icon={<Upload size={18} />}
            />
            <label className="skill-manifest-editor">
              Import bundle
              <textarea
                rows={9}
                value={importText}
                onChange={(event) => setImportText(event.target.value)}
              />
            </label>
            <div className="skill-command-row">
              <button
                className="button-secondary"
                onClick={() => reviewImport(false)}
                disabled={!csrfToken || busy}
              >
                <ShieldCheck size={16} aria-hidden="true" />
                <span>Review Import</span>
              </button>
              <button
                className="button-primary"
                onClick={() => reviewImport(true)}
                disabled={!csrfToken || busy}
              >
                <PackagePlus size={16} aria-hidden="true" />
                <span>Import Draft</span>
              </button>
              <button
                className="button-secondary"
                onClick={exportActive}
                disabled={!activeVersion || busy}
              >
                <Download size={16} aria-hidden="true" />
                <span>Export</span>
              </button>
            </div>
            <JsonBlock title="Import review" value={importReview} />
            <label className="skill-manifest-editor">
              Export bundle
              <textarea
                rows={9}
                value={exportText}
                onChange={(event) => setExportText(event.target.value)}
              />
            </label>
          </section>
        </div>
      </main>
    </div>
  );
}

function PanelHeader({
  id,
  title,
  icon,
}: {
  id: string;
  title: string;
  icon: ReactNode;
}) {
  return (
    <div className="section-header">
      <h2 className="section-title" id={id}>
        {title}
      </h2>
      {icon}
    </div>
  );
}

function ValidationPanel({
  validation,
}: {
  validation: SkillValidationResult | null;
}) {
  if (!validation) {
    return <p className="empty-copy">No validation run yet.</p>;
  }
  return (
    <div className="skill-validation">
      <StatusPill tone={validation.valid ? "good" : "bad"}>
        {validation.valid ? "Valid" : "Invalid"}
      </StatusPill>
      {[...validation.errors, ...validation.warnings].map((issue) => (
        <p key={`${issue.path}-${issue.code}-${issue.detail}`}>
          <strong>{issue.code}</strong> {issue.path}: {issue.detail}
        </p>
      ))}
      {!validation.errors.length && !validation.warnings.length && (
        <p>Checksum {validation.checksum}</p>
      )}
    </div>
  );
}

function VersionHistory({
  versions,
  activeVersionId,
  onSelect,
  onDiff,
}: {
  versions: SkillVersion[];
  activeVersionId: string | null;
  onSelect: (version: SkillVersion) => void;
  onDiff: (version: SkillVersion) => void;
}) {
  if (!versions.length) {
    return <p className="empty-copy">No persisted versions.</p>;
  }
  return (
    <div className="skill-version-list">
      {versions.map((version) => (
        <article
          className={`skill-version-row ${version.id === activeVersionId ? "is-active" : ""}`}
          key={version.id}
        >
          <button onClick={() => onSelect(version)}>
            <span>{version.version}</span>
            <StatusPill
              tone={version.state === "published" ? "good" : "neutral"}
            >
              {version.state}
            </StatusPill>
          </button>
          <button
            className="icon-button"
            onClick={() => onDiff(version)}
            title="Diff with active"
          >
            <GitCompare size={15} aria-hidden="true" />
          </button>
        </article>
      ))}
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  if (!value) {
    return null;
  }
  return (
    <div className="skill-json-block">
      <p>{title}</p>
      <pre>{prettyJson(value)}</pre>
    </div>
  );
}

function manifestFromForm(form: FormState): Record<string, unknown> {
  return {
    apiVersion: "loomi.dev/v1",
    kind: "Skill",
    metadata: {
      name: form.name,
      version: form.version,
      description: form.description,
    },
    spec: {
      inputSchema: {
        type: "object",
        properties: {
          [form.inputField]: {
            type: "string",
            minLength: 1,
            maxLength: 2000,
          },
        },
        required: [form.inputField],
        additionalProperties: false,
      },
      outputSchema: {
        type: "object",
        properties: {
          [form.outputField]: {
            type: "string",
            maxLength: 20000,
          },
          citations: {
            type: "array",
            maxItems: 50,
          },
        },
        required: [form.outputField],
        additionalProperties: true,
      },
      promptTemplate: form.promptTemplate,
      retrievalPolicy: { mode: form.retrievalMode, topK: form.topK },
      allowedTools: form.allowedTools,
      approvalPolicy: { mode: "runtime" },
      modelPolicy: {
        capability: form.modelCapability,
        maxInputTokens: form.maxInputTokens,
        maxOutputTokens: form.maxOutputTokens,
      },
      limits: {
        maxSteps: form.maxSteps,
        maxToolCalls: form.maxToolCalls,
        timeoutSeconds: form.timeoutSeconds,
      },
    },
  };
}

function formFromManifest(manifest: Record<string, unknown>): FormState {
  const metadata = objectAt(manifest, "metadata");
  const spec = objectAt(manifest, "spec");
  const inputSchema = objectAt(spec, "inputSchema");
  const inputProperties = objectAt(inputSchema, "properties");
  const firstInput = Object.keys(inputProperties)[0] ?? "expression";
  const outputSchema = objectAt(spec, "outputSchema");
  const outputProperties = objectAt(outputSchema, "properties");
  const firstOutput =
    Object.keys(outputProperties).find((key) => key !== "citations") ??
    "answer_text";
  const retrieval = objectAt(spec, "retrievalPolicy");
  const modelPolicy = objectAt(spec, "modelPolicy");
  const limits = objectAt(spec, "limits");
  return {
    name: stringAt(metadata, "name", defaultForm.name),
    version: stringAt(metadata, "version", defaultForm.version),
    description: stringAt(metadata, "description", defaultForm.description),
    promptTemplate: stringAt(
      spec,
      "promptTemplate",
      defaultForm.promptTemplate,
    ),
    inputField: firstInput,
    outputField: firstOutput,
    retrievalMode: stringAt(
      retrieval,
      "mode",
      "none",
    ) as FormState["retrievalMode"],
    topK: numberAt(retrieval, "topK", 0),
    modelCapability: stringAt(
      modelPolicy,
      "capability",
      "reasoning",
    ) as FormState["modelCapability"],
    maxInputTokens: numberAt(modelPolicy, "maxInputTokens", 12000),
    maxOutputTokens: numberAt(modelPolicy, "maxOutputTokens", 2000),
    maxSteps: numberAt(limits, "maxSteps", 6),
    maxToolCalls: numberAt(limits, "maxToolCalls", 3),
    timeoutSeconds: numberAt(limits, "timeoutSeconds", 120),
    allowedTools: arrayAt(spec, "allowedTools").filter(
      (item): item is string => typeof item === "string",
    ),
  };
}

function parseJsonObject(value: string): Record<string, unknown> {
  const parsed = JSON.parse(value) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON value must be an object.");
  }
  return parsed as Record<string, unknown>;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function objectAt(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringAt(
  source: Record<string, unknown>,
  key: string,
  fallback: string,
) {
  const value = source[key];
  return typeof value === "string" ? value : fallback;
}

function numberAt(
  source: Record<string, unknown>,
  key: string,
  fallback: number,
) {
  const value = source[key];
  return typeof value === "number" ? value : fallback;
}

function arrayAt(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return Array.isArray(value) ? value : [];
}

function resolveApiBase() {
  return API_BASE.replace(/\/$/, "");
}
