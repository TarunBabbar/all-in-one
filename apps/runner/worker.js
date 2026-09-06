/**
 * QA/One runner worker — executes generated Playwright suites in isolation.
 *
 * Receives { suiteId, files: [{ name, content }], baseUrl } over HTTP, writes
 * the suite into an isolated temp project, runs `npx playwright test` with the
 * JSON reporter, and returns per-test results (status, title, error, duration).
 *
 * Patterns merged:
 *  - ETL Buddy: sandboxed execution of generated tests in a disposable dir.
 *  - OmnyGO: results come back as structured evidence, never self-reported.
 *  - QAE2E: real execution happens in a container, never on the API host.
 *
 * The base image (mcr.microsoft.com/playwright) already has browsers + npx.
 */
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtemp, rm, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PORT = Number(process.env.PORT ?? 8787);
const execFileAsync = promisify(execFile);

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function runSuite(payload) {
  const { suiteId, files = [], baseUrl } = payload;
  const dir = await mkdtemp(join(tmpdir(), "qahub-run-"));
  try {
    // Layout: package.json + playwright.config + the spec files.
    await writeFile(
      join(dir, "package.json"),
      JSON.stringify({ name: `qahub-${suiteId}`, private: true }, null, 2),
    );
    await writeFile(
      join(dir, "playwright.config.js"),
      `module.exports = { testDir: "./tests", reporter: [["json", { outputFile: "results.json" }], ["line"]], use: { baseURL: ${JSON.stringify(
        baseUrl ?? "http://localhost:3000",
      )}, headless: true } };`,
    );
    for (const f of files || []) {
      const target = join(dir, "tests", f.name);
      await mkdir(join(dir, "tests"), { recursive: true });
      await writeFile(target, f.content);
    }

    // Install @playwright/test in the isolated dir (npm ci-style, offline cache
    // makes this fast in the container; plain npm install otherwise).
    await writeFile(join(dir, "package.json"), JSON.stringify({
      name: `qahub-${suiteId}`,
      private: true,
      devDependencies: { "@playwright/test": "1.63.0" },
    }, null, 2));
    await execFileAsync("npm", ["install", "--no-audit", "--no-fund"], { cwd: dir });

    // Run the suite.
    let stdout = "";
    try {
      ({ stdout } = await execFileAsync(
        "npx", ["playwright", "test", "--reporter=json"], { cwd: dir, timeout: 180_000 },
      ));
    } catch (e) {
      stdout = e.stdout || "";
    }

    // Parse the JSON reporter output from stdout.
    let parsed = null;
    try {
      parsed = JSON.parse(stdout);
    } catch {
      parsed = null;
    }
    const results = (parsed?.suites ?? []).flatMap((s) =>
      (s.specs ?? []).map((spec) => {
        const t = spec.tests?.[0]?.results?.[0] ?? {};
        return {
          id: spec.title,
          title: spec.title,
          status: t.status ?? "unknown",
          error: t.error?.message ?? null,
          duration_ms: t.duration ?? null,
        };
      }),
    );
    return { suiteId, results, ok: parsed !== null, raw_stdout_excerpt: (stdout || "").slice(-2000) };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { status: "ok", service: "qahub-runner", port: PORT });
    return;
  }

  if (req.method === "POST" && url.pathname === "/run") {
    try {
      const payload = await readBody(req);
      const result = await runSuite(payload);
      sendJson(res, 200, result);
    } catch (e) {
      sendJson(res, 500, { error: "run_failed", message: e.message });
    }
    return;
  }

  sendJson(res, 404, { error: "not_found", path: url.pathname });
});

server.listen(PORT, () => {
  console.log(`[qahub-runner] listening on :${PORT}`);
});
