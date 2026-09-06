"""Export adapters — one canonical TestCase model fans out to many formats.

Absorbs: TestCaseAI (CSV/Excel/JSON/PDF/TestRail/Azure DevOps exporters from a
single model), Sankar's deterministic CSV contract (stable columns, exact
order). Phase 1 ships CSV + Jira markdown; Excel/TestRail/AzDO slots in here
behind the same adapter shape.
"""

from __future__ import annotations

import csv
import io


def _cell(case: dict, key: str) -> str:
    v = case.get(key)
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    return "" if v is None else str(v)


# Stable column contract (Sankar): same order/names every export.
CSV_COLUMNS = [
    "id",
    "title",
    "type",
    "priority",
    "severity",
    "preconditions",
    "steps",
    "expected",
    "automation_rec",
    "source_evidence",
]


def cases_to_csv(cases: list[dict]) -> str:
    """Deterministic CSV export with the stable column contract."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for case in cases:
        writer.writerow({col: _cell(case, col) for col in CSV_COLUMNS})
    return buf.getvalue()


def cases_to_jira_markdown(cases: list[dict]) -> str:
    """Jira-ready markdown: each case as a bullet group a QA can paste."""
    lines: list[str] = ["h2. Generated Test Cases", ""]
    for case in cases:
        lines.append(f"h3. {_cell(case, 'id')} — {_cell(case, 'title')}")
        lines.append(f"*Type:* {_cell(case, 'type')}  |  "
                     f"*Priority:* {_cell(case, 'priority')}  |  "
                     f"*Severity:* {_cell(case, 'severity')}  |  "
                     f"*Automation:* {_cell(case, 'automation_rec')}")
        if case.get("preconditions"):
            lines.append(f"*Preconditions:* {_cell(case, 'preconditions')}")
        lines.append("*Steps:*")
        steps = case.get("steps")
        if isinstance(steps, list):
            for step in steps:
                lines.append(f"# {step}")
        else:
            lines.append(f"# {steps}")
        lines.append(f"*Expected:* {_cell(case, 'expected')}")
        lines.append("")
    return "\n".join(lines)


def export_cases(cases: list[dict], fmt: str = "csv") -> tuple[str, str]:
    """Adapter entry: returns (content, content_type). fmt in csv|jira."""
    if fmt == "jira":
        return cases_to_jira_markdown(cases), "text/markdown"
    if fmt == "json":
        import json

        return json.dumps(cases, indent=2), "application/json"
    return cases_to_csv(cases), "text/csv"
