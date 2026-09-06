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
  state: string; // not_started | draft | awaiting_approval | approved | ...
  output_artifact_id: string | null;
}

export interface PipelineState {
  project_id: string;
  current_stage: string;
  stages: Record<string, StageStatus>;
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

export function testGithub(): Promise<{
  ok: boolean;
  error?: string;
  user?: string;
  full_name?: string;
}> {
  return request<{ ok: boolean; error?: string; user?: string; full_name?: string }>(
    "/settings/test/github",
  );
}