// Pipeline stage wiring.
//
// A stage's *label* is the name of the engine behind it (see
// lib/engine-catalog.ts), so nothing here carries a name. This file owns only
// the facts the API has no opinion about: execution order, which engine runs a
// stage, and which icon represents it.

import type { IconName } from "./icons";

export interface StageDef {
  /** StageId, as the API stores it in stage_runs.stage. */
  stage: string;
  /** Engine id — the join key into the engine catalog. */
  engine: string;
  icon: IconName;
}

/** Every stage, in execution order, including the optional ones. */
export const ALL_STAGES = [
  { stage: "intake", engine: "intake", icon: "intake" },
  { stage: "doctor", engine: "requirement-doctor", icon: "doctor" },
  { stage: "test_plan", engine: "test-plan", icon: "plan" },
  { stage: "eval_plan", engine: "eval-plan", icon: "gate" },
  { stage: "test_cases", engine: "test-cases", icon: "cases" },
  { stage: "eval_cases", engine: "eval-cases", icon: "gate" },
  { stage: "codegen", engine: "codegen", icon: "codegen" },
  { stage: "eval_code", engine: "eval-code", icon: "gate" },
  { stage: "run", engine: "executor", icon: "runner" },
  { stage: "triage", engine: "failure-triage", icon: "triage" },
  { stage: "visual", engine: "visual", icon: "visual" },
  { stage: "release", engine: "release-gate", icon: "release" },
] as const satisfies readonly StageDef[];

/** The literal union of stage ids — so a typo is a compile error, not a
 * silently empty stage. */
export type StageId = (typeof ALL_STAGES)[number]["stage"];

/** Optional stages. The auto-chain never runs these, so they are excluded from
 * the chain, the totals and the progress bar. */
export const OPTIONAL_STAGES: ReadonlySet<string> = new Set(["visual"]);

/** The stages the automatic chain actually executes. */
export const CHAIN_STAGES = ALL_STAGES.filter((s) => !OPTIONAL_STAGES.has(s.stage));

/** Check stages: deterministic scoring, rendered as a metric table. */
export const CHECK_STAGES: ReadonlySet<string> = new Set([
  "eval_plan",
  "eval_cases",
  "eval_code",
]);

/**
 * A failed check is fixed by regenerating the artifact it examined, so resuming
 * one restarts its source stage. Re-running a deterministic check over identical
 * input reaches the identical verdict.
 */
const CHECK_SOURCE: Record<string, StageId> = {
  eval_plan: "test_plan",
  eval_cases: "test_cases",
  eval_code: "codegen",
};

export function resumeTarget(stage: string): StageId {
  return CHECK_SOURCE[stage] ?? (stage as StageId);
}

export function stageDef(stage: string): StageDef | undefined {
  return ALL_STAGES.find((s) => s.stage === stage);
}
