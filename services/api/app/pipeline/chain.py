"""Server-side input chaining for the automatic pipeline.

The old flow hand-carried the previous stage's output on the client and posted
it back as the next stage's input. Here the chain runner resolves each stage's
input from the stored artifacts of earlier (approved) stages plus the
project-level `inputs` (requirement + per-stage overrides), so stages run
end-to-end automatically.

Stage -> engine input contract (matches what the engines expect):

    intake      -> {"text": <raw requirement>, "source": ...}   (from project inputs)
    doctor      -> {"text": requirement}
    test_plan   -> {"text": requirement}
    eval_plan   -> {"requirement", "plan"}
    test_cases  -> {"text": requirement, "plan"}                (cases conform to plan)
    eval_cases  -> {"requirement", "plan", "cases"}
    codegen     -> {"cases": [...], "base_url": ...}            (from test_cases artifact)
    eval_code   -> {"requirement", "plan", "cases", "code"}
    run         -> {"files": [...], "base_url": ..., "runner_url": ...} (from codegen artifact)
    triage      -> {"results": [...]}                           (from run artifact)
    visual      -> skipped by the auto chain (SKIPPABLE_STAGES)
    release     -> {"results": [...], "self_heal": ..., "gates": ...}

Each generator is followed by its eval gate, so a weak artifact is caught where
it was produced instead of propagating into automation.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.settings import get_settings
from .models import PIPELINE_STAGES, SKIPPABLE_STAGES, StageId

# Editable inputs a user may override per stage (surface in the failure UI).
# Defaults are filled from env-backed settings at resolve time, so nothing is
# hardcoded; empty values here mean "fall back to settings / prior output".
OVERRIDABLE_INPUTS: dict[str, dict[str, Any]] = {
    StageId.INTAKE.value: {"source": "text"},
    StageId.DOCTOR.value: {},
    StageId.TEST_PLAN.value: {},
    StageId.EVAL_PLAN.value: {},
    StageId.TEST_CASES.value: {},
    StageId.EVAL_CASES.value: {},
    StageId.CODEGEN.value: {"base_url": ""},
    StageId.EVAL_CODE.value: {},
    StageId.RUN.value: {"base_url": "", "runner_url": ""},
    StageId.TRIAGE.value: {},
    StageId.RELEASE.value: {},
}

# First http(s) URL in the requirement text — the app under test.
_URL_RE = re.compile(r"""https?://[^\s)\]},;'"<>]+""", re.IGNORECASE)


def detect_target_url(text: str) -> str:
    """Pull the app-under-test URL out of a requirement, if the user gave one.

    Matches an explicit `url:` source prefix first, then any http(s) link in
    the text. Returns "" when the requirement does not name a URL, so callers
    fall back to the env APP_BASE_URL default.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    m = re.match(r"^url\s*:\s*(\S+)", raw, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(".,")
    m = _URL_RE.search(raw)
    if m:
        return m.group(0).rstrip(".,;")
    return ""


def stage_order() -> list[StageId]:
    """The canonical execution order (visual stays optional/skippable)."""
    return [s for s in PIPELINE_STAGES if s not in SKIPPABLE_STAGES]


def _payload(artifact: Any | None) -> dict:
    return (artifact.payload if artifact is not None else None) or {}


_EVAL_STAGES = (StageId.EVAL_PLAN, StageId.EVAL_CASES, StageId.EVAL_CODE)


def _gate_summaries(artifacts: dict[StageId, Any]) -> list[dict]:
    """Carry each eval gate's verdict into the release stage.

    The Release Report has to be able to say "this passed the run but failed a
    gate", which is only possible if the gate results travel with it.
    """
    out: list[dict] = []
    for stage in _EVAL_STAGES:
        payload = _payload(artifacts.get(stage))
        if not payload:
            continue
        out.append(
            {
                "gate": payload.get("gate") or stage.value,
                "passed": bool(payload.get("passed")),
                "summary": payload.get("summary") or {},
            }
        )
    return out


def resolve_stage_inputs(
    *,
    stage: StageId,
    artifacts: dict[StageId, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Build the input dict for `stage` from prior artifacts + project inputs.

    `artifacts` maps StageId -> Artifact (approved stage outputs available so
    far). `inputs` is the project-level inputs blob (requirement + overrides).
    Any override the user supplied for this stage is merged last.
    """
    req = str(inputs.get("requirement", ""))
    overrides = dict(inputs.get("overrides", {}).get(stage.value, {}) or {})
    settings = get_settings()
    # Precedence for the app-under-test URL:
    #   1. requirement-derived URL (user pasted a link / url: prefix)
    #   2. env APP_BASE_URL fallback
    base_url = str(inputs.get("app_url") or detect_target_url(req) or settings.app_base_url)
    runner_url = settings.runner_url

    if stage == StageId.INTAKE:
        base = {"text": req, "source": inputs.get("source", "text")}

    elif stage in (StageId.DOCTOR, StageId.TEST_PLAN):
        base = {"text": req}

    elif stage == StageId.EVAL_PLAN:
        base = {"requirement": req, "plan": _payload(artifacts.get(StageId.TEST_PLAN))}

    elif stage == StageId.TEST_CASES:
        # The case generator now works from the approved plan, which is what
        # makes coverage traceable and the case gate meaningful.
        base = {"text": req, "plan": _payload(artifacts.get(StageId.TEST_PLAN))}

    elif stage == StageId.EVAL_CASES:
        base = {
            "requirement": req,
            "plan": _payload(artifacts.get(StageId.TEST_PLAN)),
            "cases": _payload(artifacts.get(StageId.TEST_CASES)).get("cases", []),
        }

    elif stage == StageId.CODEGEN:
        cases = _payload(artifacts.get(StageId.TEST_CASES)).get("cases", [])
        base = {"cases": cases, "base_url": base_url}

    elif stage == StageId.EVAL_CODE:
        base = {
            "requirement": req,
            "plan": _payload(artifacts.get(StageId.TEST_PLAN)),
            "cases": _payload(artifacts.get(StageId.TEST_CASES)).get("cases", []),
            "code": _payload(artifacts.get(StageId.CODEGEN)),
        }

    elif stage == StageId.RUN:
        codegen = _payload(artifacts.get(StageId.CODEGEN))
        files_map = codegen.get("files")
        # codegen stores files as {"tests": [{name, content}]} — the executor
        # and runner expect a flat [{name, content}] list.
        files = []
        if isinstance(files_map, dict):
            for entry in files_map.values():
                if isinstance(entry, list):
                    files.extend(e for e in entry if isinstance(e, dict))
        elif isinstance(files_map, list):
            files = [e for e in files_map if isinstance(e, dict)]
        base = {
            "files": files,
            # The locator map is what lets the executor heal a failing suite
            # instead of just reporting it.
            "locators": codegen.get("locators") or [],
            "base_url": base_url,
            "runner_url": runner_url,
        }

    elif stage == StageId.TRIAGE:
        results = _payload(artifacts.get(StageId.RUN)).get("results", [])
        base = {"results": results}

    elif stage == StageId.RELEASE:
        run_payload = _payload(artifacts.get(StageId.RUN))
        base = {
            "results": run_payload.get("results", []),
            "self_heal": {
                "attempts": run_payload.get("attempts") or [],
                "auto_fixed": run_payload.get("auto_fixed") or [],
                "manual_required": run_payload.get("manual_required") or [],
            },
            "gates": _gate_summaries(artifacts),
        }

    else:
        base = {}

    # Let user-supplied overrides win for the keys they provided.
    base.update({k: v for k, v in overrides.items() if v is not None and v != ""})
    return base


def first_pending_stage(
    stage_states: dict[StageId, str], skip_visual: bool = True
) -> StageId | None:
    """First stage that is not yet approved, in canonical order."""
    for stage in PIPELINE_STAGES:
        if skip_visual and stage in SKIPPABLE_STAGES:
            continue
        if stage_states.get(stage) != "approved":
            return stage
    return None
