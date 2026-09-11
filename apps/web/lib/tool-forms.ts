// Per-engine input forms. Each entry describes the payload keys a standalone
// tool workspace renders and posts to /engines/{id}/run.
//
// Titles and descriptions are NOT here — they come from the engine catalog
// (GET /engines), so a tool is named in exactly one place.

export interface ToolField {
  name: string; // payload key
  label: string;
  type: "text" | "textarea" | "json" | "number" | "checkbox";
  placeholder?: string;
  default?: string;
  required?: boolean;
}

export interface ToolFormDef {
  engine: string;
  fields: ToolField[];
}

export const TOOL_FORMS: Record<string, ToolFormDef> = {
  intake: {
    engine: "intake",
    fields: [
      { name: "text", label: "Requirement text", type: "textarea", required: true },
      {
        name: "source",
        label: "Source",
        type: "text",
        default: "text",
        placeholder: "text, jira, url, confluence, pdf",
      },
    ],
  },
  "requirement-doctor": {
    engine: "requirement-doctor",
    fields: [{ name: "text", label: "Requirement text", type: "textarea", required: true }],
  },
  "test-cases": {
    engine: "test-cases",
    fields: [
      { name: "text", label: "Requirement text", type: "textarea", required: true },
      {
        name: "plan",
        label: "Test plan (JSON)",
        type: "json",
        placeholder: '{"criteria": [{"id": "AC-01", "text": "…"}]}',
      },
    ],
  },
  codegen: {
    engine: "codegen",
    fields: [
      { name: "cases", label: "Test cases (JSON array)", type: "json" },
      { name: "base_url", label: "Base URL of the app under test", type: "text" },
    ],
  },
  "failure-triage": {
    engine: "failure-triage",
    fields: [{ name: "results", label: "Run results (JSON array)", type: "json" }],
  },
  visual: {
    engine: "visual",
    fields: [
      { name: "diff_percent", label: "Difference (0-100)", type: "number" },
      { name: "findings", label: "Findings (JSON array)", type: "json" },
    ],
  },
  a11y: {
    engine: "a11y",
    fields: [{ name: "html", label: "HTML to scan", type: "textarea", required: true }],
  },
  "api-testing": {
    engine: "api-testing",
    fields: [
      { name: "method", label: "Method", type: "text", default: "GET" },
      { name: "url", label: "Endpoint URL", type: "text", required: true },
      { name: "execute", label: "Send a live request", type: "checkbox" },
    ],
  },
  etl: {
    engine: "etl",
    fields: [
      { name: "rules", label: "Data rules (JSON array of strings)", type: "json" },
      { name: "schema", label: "Table schema (JSON)", type: "json" },
    ],
  },
  "release-gate": {
    engine: "release-gate",
    fields: [{ name: "results", label: "Run results (JSON array)", type: "json" }],
  },
  leakage: {
    engine: "leakage",
    fields: [{ name: "defects", label: "Defects (JSON array)", type: "json" }],
  },
  rag: {
    engine: "rag",
    fields: [
      { name: "document", label: "Document text", type: "textarea", required: true },
      { name: "query", label: "Question", type: "text" },
      { name: "top_k", label: "Chunks to retrieve", type: "number", default: "3" },
    ],
  },
  "agent-security": {
    engine: "agent-security",
    fields: [
      { name: "expected_path", label: "Expected path (JSON)", type: "json" },
      { name: "actual_trace", label: "Actual trace (JSON)", type: "json" },
    ],
  },
  executor: {
    engine: "executor",
    fields: [
      { name: "files", label: "Suite files (JSON array of {name, content})", type: "json" },
      { name: "base_url", label: "Base URL of the app under test", type: "text" },
    ],
  },
  "prompt-eval": {
    engine: "prompt-eval",
    fields: [{ name: "rows", label: "Test rows (JSON array)", type: "json" }],
  },
};
