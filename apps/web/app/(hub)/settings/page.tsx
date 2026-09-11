"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/badge";
import {
  getSettings,
  saveSettings,
  testGithub,
  testJira,
  type SettingsGroups,
} from "@/lib/api";
import { Icon, type IconName } from "@/lib/icons";

const MASK = "********";

/**
 * Matches the input treatment used by the tool workspace, so a field looks the
 * same wherever it appears in the product.
 */
const INPUT_CLASS =
  "mt-1.5 w-full rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 py-2 text-[12.5px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]";

/** The secondary button, shared with the pipeline's per-agent actions. */
const SECONDARY_BTN =
  "press inline-flex shrink-0 items-center gap-1.5 rounded-[7px] border border-[var(--line-strong)] px-2.5 py-1.5 text-[12.5px] font-semibold text-[var(--ink-soft)] transition-colors hover:border-[var(--accent)] hover:text-[var(--ink)] disabled:opacity-40";

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
}: {
  title: string;
  icon: IconName;
  fields: { key: string; label: string; type?: "password" | "text" }[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onTest: () => void;
  test: TestState;
}) {
  const testing = test.status === "testing";
  const settled = test.status === "ok" || test.status === "error";
  const ok = test.status === "ok";

  return (
    <section className="overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3">
        <h2 className="flex items-center gap-2 text-[14px] font-semibold text-[var(--ink)]">
          <Icon name={icon} size={15} className="text-[var(--ink-soft)]" />
          {title}
        </h2>
        <button onClick={onTest} disabled={testing} className={SECONDARY_BTN}>
          <Icon name={testing ? "clock" : "link"} size={12} />
          {testing ? "Testing…" : "Test connection"}
        </button>
      </div>

      <div className="space-y-4 px-5 py-4">
        {fields.map((f) => (
          <div key={f.key}>
            <label htmlFor={`${title}-${f.key}`} className="field-label block">
              {f.label}
            </label>
            <input
              id={`${title}-${f.key}`}
              type={f.type ?? "text"}
              value={values[f.key] ?? ""}
              onChange={(e) => onChange(f.key, e.target.value)}
              placeholder={f.type === "password" ? "••••••••" : ""}
              className={INPUT_CLASS}
              style={f.type === "password" ? { fontFamily: "var(--font-mono)" } : undefined}
              autoComplete="off"
            />
          </div>
        ))}

        {/* The status word rides in the shared Badge; the message carries the
            detail. A coloured div with a glyph in it was neither. */}
        {settled && (
          <div
            className={`qa-fade flex flex-wrap items-center gap-2 rounded-[var(--r-md)] border px-3 py-2.5 ${
              ok
                ? "border-[var(--ok)]/30 bg-[var(--ok-soft)]"
                : "border-[var(--bad)]/30 bg-[var(--bad-soft)]"
            }`}
          >
            <Badge tone={ok ? "ok" : "bad"} dot>
              {ok ? "connected" : "failed"}
            </Badge>
            <span className="min-w-0 flex-1 text-[12px] leading-relaxed text-[var(--ink-soft)]">
              {test.message}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const [jira, setJira] = useState<Record<string, string>>({});
  const [github, setGithub] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<TestState>({ status: "idle" });
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
    setSaveState({ status: "idle" });
    try {
      await saveSettings({ jira, github });
      setSaveState({ status: "ok", message: "Stored in the app database." });
    } catch (e) {
      setSaveState({ status: "error", message: (e as Error).message });
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
        set(
          res.ok
            ? { status: "ok", message: `Authenticated as ${res.display_name ?? "user"}` }
            : { status: "error", message: res.error ?? "Connection failed" },
        );
      } else {
        const res = await testGithub();
        if (res.ok) {
          const repo = res.full_name ? ` · ${res.full_name}` : "";
          const branch = res.default_branch ? ` (${res.default_branch})` : "";
          set({
            status: "ok",
            message: `Authenticated as ${res.user ?? "user"}${repo}${branch}`,
          });
        } else {
          set({ status: "error", message: res.error ?? "Connection failed" });
        }
      }
    } catch (e) {
      set({ status: "error", message: (e as Error).message });
    }
  };

  if (!loaded) {
    return (
      <div className="mx-auto max-w-[900px]">
        <div className="h-6 w-28 animate-pulse rounded-[6px] bg-[var(--bg-elev)]" />
        <div className="mb-7 mt-3 h-9 w-52 animate-pulse rounded-[8px] bg-[var(--bg-elev)]" />
        <div className="space-y-5">
          <div className="h-56 animate-pulse rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]" />
          <div className="h-56 animate-pulse rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[900px]">
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="accent" dot>
          Settings
        </Badge>
      </div>

      <h1 className="text-[30px] font-semibold leading-tight text-[var(--ink)]">
        Connections
      </h1>
      <p className="mb-7 mt-2.5 max-w-[62ch] text-[14px] leading-relaxed text-[var(--ink-soft)]">
        Store your Jira and GitHub credentials so the platform can pull
        requirements and push code. Secrets are masked on read.
      </p>

      <div className="space-y-5">
        <ConnectorCard
          title="Jira"
          icon="intake"
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
          icon="link"
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

        <button
          onClick={save}
          disabled={saving}
          className="press inline-flex items-center gap-1.5 rounded-[var(--r-md)] bg-[var(--accent)] px-5 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
        >
          <Icon name={saving ? "clock" : "check"} size={13} />
          {saving ? "Saving…" : "Save settings"}
        </button>

        {/* Same shape as the connector test result, so feedback reads the same
            way wherever it appears. */}
        {(saveState.status === "ok" || saveState.status === "error") && (
          <div
            className={`qa-fade flex flex-wrap items-center gap-2 rounded-[var(--r-md)] border px-3 py-2.5 ${
              saveState.status === "ok"
                ? "border-[var(--ok)]/30 bg-[var(--ok-soft)]"
                : "border-[var(--bad)]/30 bg-[var(--bad-soft)]"
            }`}
          >
            <Badge tone={saveState.status === "ok" ? "ok" : "bad"} dot>
              {saveState.status === "ok" ? "saved" : "save failed"}
            </Badge>
            <span className="min-w-0 flex-1 text-[12px] leading-relaxed text-[var(--ink-soft)]">
              {saveState.message}
            </span>
          </div>
        )}

        <p className="text-[12px] leading-relaxed text-[var(--ink-faint)]">
          Saved values live in the app database and seed from{" "}
          <code className="rounded-[3px] bg-[var(--bg-sunken)] px-1.5 py-0.5 text-[11px] text-[var(--ink-soft)]">
            services/api/.env
          </code>{" "}
          on first run. A field showing {MASK} keeps its stored secret when you
          save.
        </p>
      </div>
    </div>
  );
}
