"use client";

import { useEffect, useState } from "react";

import {
  getSettings,
  saveSettings,
  testGithub,
  testJira,
  type SettingsGroups,
} from "@/lib/api";

const MASK = "********";

interface TestState {
  status: "idle" | "testing" | "ok" | "error";
  message?: string;
}

function ConnectorCard({
  title,
  icon,
  fields,
  values,
  onChange,
  onTest,
  test,
  children,
}: {
  title: string;
  icon: string;
  fields: { key: string; label: string; type?: "password" | "text" }[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onTest: () => void;
  test: TestState;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border bg-[var(--bg-elev)] p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold">
          {icon} {title}
        </h2>
        <button
          onClick={onTest}
          disabled={test.status === "testing"}
          className="rounded-md border border-[var(--line-strong)] px-3 py-1.5 text-xs font-semibold hover:bg-[var(--bg-hover)] disabled:opacity-40"
        >
          {test.status === "testing" ? "Testing…" : "Test connection"}
        </button>
      </div>

      <div className="mt-4 space-y-3">
        {fields.map((f) => (
          <div key={f.key}>
            <label className="text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
              {f.label}
            </label>
            <input
              type={f.type ?? "text"}
              value={values[f.key] ?? ""}
              onChange={(e) => onChange(f.key, e.target.value)}
              className="mt-1 w-full rounded-md border bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              placeholder={f.type === "password" ? "••••••••" : ""}
            />
          </div>
        ))}
        {children}
      </div>

      {test.status === "ok" && (
        <p className="mt-3 rounded-md bg-[var(--ok)]/10 px-3 py-2 text-xs text-[var(--ok)]">
          ✓ {test.message}
        </p>
      )}
      {test.status === "error" && (
        <p className="mt-3 rounded-md bg-[var(--bad)]/10 px-3 py-2 text-xs text-[var(--bad)]">
          ✗ {test.message}
        </p>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [jira, setJira] = useState<Record<string, string>>({});
  const [github, setGithub] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [jiraTest, setJiraTest] = useState<TestState>({ status: "idle" });
  const [githubTest, setGithubTest] = useState<TestState>({ status: "idle" });

  useEffect(() => {
    getSettings()
      .then((s: SettingsGroups) => {
        setJira(s.jira ?? {});
        setGithub(s.github ?? {});
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const setJiraField = (key: string, value: string) =>
    setJira((prev) => ({ ...prev, [key]: value }));
  const setGithubField = (key: string, value: string) =>
    setGithub((prev) => ({ ...prev, [key]: value }));

  const save = async () => {
    setSaving(true);
    setSavedMsg(null);
    try {
      await saveSettings({ jira, github });
      setSavedMsg("Settings saved.");
    } catch (e) {
      setSavedMsg(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (which: "jira" | "github") => {
    const set = which === "jira" ? setJiraTest : setGithubTest;
    set({ status: "testing" });
    try {
      if (which === "jira") {
        const res = await testJira();
        if (res.ok) {
          set({ status: "ok", message: `Connected as ${res.display_name ?? "user"}` });
        } else {
          set({ status: "error", message: res.error ?? "Connection failed" });
        }
      } else {
        const res = await testGithub();
        if (res.ok) {
          set({ status: "ok", message: `Authenticated as ${res.user} · ${res.full_name ?? res.repo ?? ""}` });
        } else {
          set({ status: "error", message: res.error ?? "Connection failed" });
        }
      }
    } catch (e) {
      set({ status: "error", message: (e as Error).message });
    }
  };

  if (!loaded) {
    return <div className="text-sm text-[var(--ink-faint)]">Loading settings…</div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
          Settings
        </p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Connections</h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--ink-soft)]">
          Store your Jira and GitHub credentials so the platform can pull
          requirements and push code. Secrets are masked on read.
        </p>
      </header>

      <ConnectorCard
        title="Jira"
        icon="📋"
        fields={[
          { key: "url", label: "Jira URL" },
          { key: "email", label: "Email" },
          { key: "api_token", label: "API token", type: "password" },
        ]}
        values={jira}
        onChange={setJiraField}
        onTest={() => runTest("jira")}
        test={jiraTest}
      />

      <ConnectorCard
        title="GitHub"
        icon="🐙"
        fields={[
          { key: "token", label: "Personal access token", type: "password" },
          { key: "repo", label: "Repo (owner/repo)" },
          { key: "branch", label: "Branch" },
        ]}
        values={github}
        onChange={setGithubField}
        onTest={() => runTest("github")}
        test={githubTest}
      />

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-md bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)] disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
        {savedMsg && <span className="text-sm text-[var(--ink-soft)]">{savedMsg}</span>}
      </div>

      <p className="text-xs text-[var(--ink-faint)]">
        Tip: saved values are stored in the app database and seed from{" "}
        <code className="rounded bg-[var(--bg-sunken)] px-1">services/api/.env</code> on first
        run. A field showing {MASK} keeps its stored secret when you save.
      </p>
    </div>
  );
}
