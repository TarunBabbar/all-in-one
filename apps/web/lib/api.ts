// Thin client for the QA/One API. Mirrors services/api routes.

import { API_URL } from "@/lib/types";

export { API_URL };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface StageStatus {
  state: string; // not_started | draft | running | awaiting_approval | approved | ...
  output_artifact_id: string | null;
  error: string | null;
  started_at?: string | null;
  updated_at?: string | null;
}

export interface PipelineState {
  project_id: string;
  current_stage: string;
  stages: Record<string, StageStatus>;
  inputs?: Record<string, unknown>;
  running?: boolean;
}

export interface LogEntry {
  id: string;
  stage: string | null;
  level: string;
  message: string;
  created_at: string;
}

export interface PipelineStatus {
  project_id: string;
  running: boolean;
  current_stage: string;
  inputs: Record<string, unknown>;
  stages: Record<string, StageStatus>;
  log: LogEntry[];
  defaults?: { base_url?: string; runner_url?: string };
}

export interface StageResult {
  stage: string;
  state: string;
  artifact_id?: string | null;
  payload?: Record<string, unknown>;
  error?: string | null;
}

export function createProject(name: string): Promise<Project> {
  return request<Project>(`/projects?name=${encodeURIComponent(name)}`, { method: "POST" });
}

export function getPipelineState(projectId: string): Promise<PipelineState> {
  return request<PipelineState>(`/pipeline/${projectId}`);
}

export function runStage(
  projectId: string,
  stage: string,
  engine: string,
  input: Record<string, unknown> = {},
): Promise<StageResult> {
  return request<StageResult>(`/pipeline/${projectId}/run-stage/${stage}`, {
    method: "POST",
    body: JSON.stringify({ engine, input }),
  });
}

export function approveStage(projectId: string, stage: string): Promise<{ state: string }> {
  return request<{ state: string }>(`/pipeline/${projectId}/approve/${stage}`, {
    method: "POST",
  });
}

export function requestChanges(projectId: string, stage: string): Promise<{ state: string }> {
  return request<{ state: string }>(`/pipeline/${projectId}/request-changes/${stage}`, {
    method: "POST",
  });
}

export interface PipelineActionOpts {
  requirement?: string;
  source?: string;
  startStage?: string;
  overrides?: Record<string, Record<string, unknown>>;
}

export function startPipeline(
  projectId: string,
  opts: PipelineActionOpts = {},
): Promise<{ ok: boolean; project_id: string; running: boolean }> {
  return request(`/pipeline/${projectId}/start`, {
    method: "POST",
    body: JSON.stringify({
      requirement: opts.requirement,
      source: opts.source,
      start_stage: opts.startStage,
      overrides: opts.overrides,
    }),
  });
}

export function resumePipeline(
  projectId: string,
  stage: string,
  opts: { requirement?: string; overrides?: Record<string, Record<string, unknown>> } = {},
): Promise<{ ok: boolean; project_id: string; running: boolean }> {
  return request(`/pipeline/${projectId}/resume`, {
    method: "POST",
    body: JSON.stringify({ stage, requirement: opts.requirement, overrides: opts.overrides }),
  });
}

export function stopPipeline(
  projectId: string,
): Promise<{ ok: boolean; project_id: string; running: boolean }> {
  return request(`/pipeline/${projectId}/stop`, { method: "POST" });
}

export function getPipelineStatus(projectId: string): Promise<PipelineStatus> {
  return request<PipelineStatus>(`/pipeline/${projectId}/status`);
}

export interface Artifact {
  id: string;
  project_id: string;
  stage: string;
  kind: string;
  payload: Record<string, unknown>;
  state: string;
  created_at: string;
}

export function getArtifact(artifactId: string): Promise<Artifact> {
  return request<Artifact>(`/artifacts/${artifactId}`);
}

export interface EngineRunResult {
  engine: string;
  kind: string;
  payload: Record<string, unknown>;
}

export function runEngine(engineId: string, input: Record<string, unknown> = {}): Promise<EngineRunResult> {
  return request<EngineRunResult>(`/engines/${engineId}/run`, {
    method: "POST",
    body: JSON.stringify({ input }),
  });
}

// ---- settings / connectors ----

export interface SettingsGroups {
  jira: Record<string, string>;
  github: Record<string, string>;
}

export function getSettings(): Promise<SettingsGroups> {
  return request<SettingsGroups>("/settings");
}

export function saveSettings(groups: SettingsGroups): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/settings", {
    method: "PUT",
    body: JSON.stringify(groups),
  });
}

export function testJira(): Promise<{ ok: boolean; error?: string; display_name?: string }> {
  return request<{ ok: boolean; error?: string; display_name?: string }>("/settings/test/jira");
}

export interface GithubTestResult {
  ok: boolean;
  error?: string;
  /** GitHub login of the authenticated user. */
  user?: string;
  /** "owner/repo" of the connected repository. */
  full_name?: string;
  default_branch?: string;
}

export function testGithub(): Promise<GithubTestResult> {
  return request<GithubTestResult>("/settings/test/github");
}

// ---- Jira issue fetch ----

export interface JiraIssue {
  key: string;
  summary: string;
  description: string;
  issue_type: string;
  status: string;
  priority: string;
  labels: string[];
  parent: string | null;
  url: string;
}

export function fetchJiraIssue(issueKey: string): Promise<{ issue: JiraIssue }> {
  return request<{ issue: JiraIssue }>("/connectors/jira/fetch", {
    method: "POST",
    body: JSON.stringify({ issue_key: issueKey }),
  });
}

// ---- GitHub push/pull ----

export interface GithubFile {
  path: string;
  content: string;
}

export function pushFilesToGithub(
  files: GithubFile[],
  opts: { prefix?: string; message?: string } = {},
): Promise<{ ok: boolean; results: { path: string; ok: boolean; commit_sha?: string; error?: string }[] }> {
  return request<{
    ok: boolean;
    results: { path: string; ok: boolean; commit_sha?: string; error?: string }[];
  }>("/connectors/github/push-files", {
    method: "POST",
    body: JSON.stringify({ files, prefix: opts.prefix, message: opts.message }),
  });
}

export function readGithubFile(path: string): Promise<{ ok: boolean; content: string; sha?: string }> {
  return request<{ ok: boolean; content: string; sha?: string }>(
    `/connectors/github/read?path=${encodeURIComponent(path)}`,
  );
}