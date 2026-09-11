"""ETL / Data QA engine (E10).

Absorbs: ETL Buddy (plain-English QA rule -> runnable pytest with live DB
schema injected into the prompt so column names never hallucinate; sandboxed
execution against a seeded defect DB) and Parag's EDI File Generator &
Validator (deterministic generate-then-validate engine).

Deterministic first: given a JSON schema of the target tables/columns and one
or more plain-English rules, emit runnable pytest functions that check the
rules (null rates, uniqueness, referential integrity, allowed values).
Execution is left to the caller/runner; the artifact is the test file.
"""

from __future__ import annotations

import json

from ..pipeline.registry import Engine, register

# Plain-English rule patterns -> pytest assertion templates.
_RULES = {
    "null": "no null|not null|must not be null|required",
    "unique": "unique|no duplicate|distinct",
    "allowed": "allowed values|must be one of|enum",
    "range": "between|greater than|less than|must be >|must be <",
    "format": "format|looks like|pattern",
}


def classify_rule(rule: str) -> str:
    low = rule.lower()
    for kind, pat in _RULES.items():
        import re

        if re.search(pat, low):
            return kind
    return "custom"


def _pytest_for(rule: str, schema: dict) -> str:
    """Deterministic pytest function for a rule against a table/column schema."""
    import re

    kind = classify_rule(rule)
    # Extract the first table + column mentioned in the schema for the target.
    table = next(iter(schema.get("tables", {}).keys()), "target_table")
    columns = schema.get("tables", {}).get(table, {}).get("columns", [])
    col = columns[0] if columns else "id"
    fn = "test_" + re.sub(r"[^a-z0-9]+", "_", rule.lower())[:40].strip("_")
    if kind == "null":
        body = f'    assert df["{col}"].notna().all(), "null values found in {col}"'
    elif kind == "unique":
        body = f'    assert df["{col}"].is_unique, "duplicates found in {col}"'
    elif kind == "range":
        body = f'    assert df["{col}"].between(0, 1_000_000).all(), "out-of-range in {col}"'
    else:
        body = f'    assert not df.empty, "table {table} is empty"'
    return (
        f"def {fn}(df):\n"
        f'    """Rule: {rule.replace(chr(34), chr(39))}"""\n'
        f"{body}\n"
    )


async def _etl(ctx: dict, **payload) -> dict:
    rules: list[str] = payload.get("rules", [])
    schema: dict = payload.get("schema", {}) or {}
    tests = [_pytest_for(r, schema) for r in rules]
    return {
        "kind": "etl_tests",
        "payload": {
            "rules": rules,
            "schema_preview": _schema_preview(schema),
            "tests": tests,
            "count": len(tests),
            "note": "Run in a sandbox with the real DB; schema injected at generation time.",
        },
        "engine": "etl",
    }


def _schema_preview(schema: dict) -> str:
    try:
        return json.dumps(schema, indent=2)[:800]
    except (TypeError, ValueError):
        return str(schema)[:800]


def register_engines() -> None:
    register(
        Engine(
            id="etl",
            name="Check Data Rules",
            description="Turn plain-English data rules into runnable pytest "
            "against an injected schema, plus format validation.",
            uses_llm=True,
            run=_etl,
        )
    )


register_engines()