/**
 * QA/One runner worker — executes generated Playwright suites in isolation.
 *
 * Receives { suiteId, files: [{ name, content }], baseUrl } over HTTP, writes
 * the suite into a per-request temp project, runs Playwright with the JSON
 * reporter, and returns per-test results.
 *
 * Install resolution (robust): rather than assuming its own temp workspace is
 * populated, the worker walks a candidate list — env override, the runner app's
 * own node_modules, parent node_modules (monorepo root), the temp workspace —
 * and verifies each actually contains a usable Playwright CLI (cli.js, not just
 * a node_modules dir; a partial/empty install previously poisoned this check
 * forever). Only when nothing usable is found does it `npm install` into the
 * temp workspace. Browsers default to the shared ms-playwright cache.
 *
 * Windows note: npm/npx are .cmd shims, so they are invoked through `cmd /c`
 * (direct execFile cannot spawn a .cmd without a shell).
 */
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { access, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve as pathResolve } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.PORT ?? 8787);
const WORKSPACE = process.env.RUNNER_WORKSPACE ?? join(tmpdir(), "qahub-runner-home");
const PLAYWRIGHT_VERSION = "1.63.0";
const IS_WIN = process.platform === "win32";
const APP_DIR = dirname(fileURLToPath(import.meta.url));
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

async function exists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

/** Run a command, routing .cmd shims through cmd /c on Windows. */
async function run(cmd, args, opts = {}) {
  if (IS_WIN && (cmd === "npm" || cmd === "npx")) {
    const quoted = args.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");
    return execFileAsync("cmd", ["/c", `${cmd} ${quoted}`], opts);
  }
  return execFileAsync(cmd, args, opts);
}

// ---- playwright install resolution ----

/** A CLI is usable when cli.js exists for either the `playwright` package or
 * `@playwright/test` (they ship the same test runner entry). */
async function cliIn(nodeModulesDir) {
  const candidates = [
    join(nodeModulesDir, "playwright", "cli.js"),
    join(nodeModulesDir, "@playwright", "test", "cli.js"),
  ];
  for (const c of candidates) {
    if (await exists(c)) return c;
  }
  return null;
}

/** Walk up from a dir collecting `<dir>/node_modules` candidates. */
function parentNodeModules(startDir, maxLevels = 5) {
  const out = [];
  let dir = pathResolve(startDir);
  for (let i = 0; i < maxLevels; i++) {
    out.push(join(dir, "node_modules"));
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return out;
}

/** Resolve a usable install: env override → app → monorepo parents → workspace. */
async function resolveInstall() {
  if (process.env.RUNNER_PLAYWRIGHT_DIR) {
    const cli = await cliIn(process.env.RUNNER_PLAYWRIGHT_DIR);
    if (cli) return { nodeModules: process.env.RUNNER_PLAYWRIGHT_DIR, cli };
  }
  const seen = new Set();
  for (const nm of [
    join(APP_DIR, "node_modules"),
    ...parentNodeModules(APP_DIR),
    join(WORKSPACE, "node_modules"),
  ]) {
    const key = pathResolve(nm).toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    const cli = await cliIn(nm);
    if (cli) return { nodeModules: nm, cli };
  }
  return null;
}

/** Install into the temp workspace when nothing usable exists anywhere. */
async function installIntoWorkspace() {
  await mkdir(WORKSPACE, { recursive: true });
  await writeFile(
    join(WORKSPACE, "package.json"),
    JSON.stringify(
      {
        name: "qahub-runner-workspace",
        private: true,
        devDependencies: { "@playwright/test": PLAYWRIGHT_VERSION },
      },
      null,
      2,
    ),
  );
  console.log("[qahub-runner] no usable Playwright found — installing into workspace…");
  await run("npm", ["install", "--no-audit", "--no-fund"], {
    cwd: WORKSPACE,
    timeout: 600_000,
  });
  return resolveInstall();
}

/** Ensure the Chromium browser matches this Playwright version. `install` is a
 * fast no-op when the correct revision is already in the cache, so we always
 * run it once at startup rather than guessing cache paths (the version-specific
 * chromium-<rev> dir is what must exist, not the cache root). */
async function ensureBrowsers(install) {
  if (process.env.RUNNER_DOCKER) return;
  try {
    await execFileAsync(process.execPath, [install.cli, "install", "chromium"], {
      cwd: WORKSPACE,
      timeout: 600_000,
    });
  } catch (e) {
    console.log("[qahub-runner] browser install warning:", (e.message || "").slice(0, 300));
  }
}

let _install = null;
async function getInstall() {
  if (_install) return _install;
  await mkdir(WORKSPACE, { recursive: true });
  _install = (await resolveInstall()) ?? (await installIntoWorkspace());
  if (_install) {
    console.log(`[qahub-runner] using Playwright at ${_install.cli}`);
    await ensureBrowsers(_install);
  }
  return _install;
}

// ---- run one suite ----

async function runSuite(payload) {
  const { suiteId, files = [], baseUrl } = payload;
  const install = await getInstall();
  if (!install) {
    return {
      suiteId,
      results: [],
      ok: false,
      error: "no usable Playwright install found",
      raw_stdout_excerpt: "Playwright could not be resolved in any candidate node_modules.",
    };
  }

  const dir = await mkdtemp(join(tmpdir(), "qahub-run-"));
  try {
    await writeFile(
      join(dir, "package.json"),
      JSON.stringify({ name: `qahub-${suiteId}`, private: true }, null, 2),
    );
    await writeFile(
      join(dir, "playwright.config.js"),
      `module.exports = {
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["json", { outputFile: "results.json" }], ["line"]],
  use: {
    baseURL: ${JSON.stringify(baseUrl ?? "http://localhost:3000")},
    headless: true,
    navigationTimeout: 45_000,
    actionTimeout: 20_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
};`,
    );
    for (const f of files || []) {
      const target = join(dir, "tests", f.name);
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, f.content);
    }

    // Junction the resolved node_modules so the spec's `@playwright/test` import
    // resolves without any per-run install.
    await linkNodeModules(dir, install.nodeModules);

    let stdout = "";
    try {
      ({ stdout } = await execFileAsync(process.execPath, [install.cli, "test", "--reporter=json"], {
        cwd: dir,
        timeout: 240_000,
      }));
    } catch (e) {
      stdout = e.stdout || e.message || "";
    }

    let parsed = null;
    try {
      parsed = JSON.parse(stdout);
    } catch {
      parsed = null;
    }
    const results = collectSpecs(parsed, join(dir, "tests"));
    return { suiteId, results, ok: parsed !== null, raw_stdout_excerpt: (stdout || "").slice(-2000) };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

// ---- JSON reporter parsing ----

/**
 * Rank a spec's outcome across attempts. Playwright retries a test and records
 * one entry per attempt; the spec is only "passed" if every attempt passed.
 * Lower rank = worse, so we keep the worst.
 */
const STATUS_RANK = { passed: 6, skipped: 5, timedOut: 1, interrupted: 2, failed: 0, broken: 0 };
function worstStatus(attempts) {
  let worst = null;
  for (const a of attempts) {
    const s = a?.status ?? "unknown";
    if (worst === null || (STATUS_RANK[s] ?? 3) < (STATUS_RANK[worst] ?? 3)) worst = s;
  }
  return worst ?? "unknown";
}

/** Map Playwright's result status to the pipeline's vocabulary. timedOut and
 * interrupted are failures, not unknowns — the release gate and triage only
 * count "failed"/"passed"/"skipped". */
function normalizeStatus(s) {
  const t = String(s ?? "unknown").toLowerCase();
  if (t === "timedout" || t === "interrupted" || t === "broken") return "failed";
  return t || "unknown";
}

/**
 * Recursively collect specs from a Playwright JSON report. The report nests
 * suites mirroring the testDir tree (tests/e2e/auth/login.spec.ts produces a
 * `suites -> suites -> specs` chain), so a one-level read finds nothing.
 * `suite.file` is absolute in the report — it is relativized to `baseDir` for
 * readable ids.
 */
function collectSpecs(report, baseDir) {
  const out = [];
  const rel = (file) => {
    if (typeof file !== "string" || !file) return null;
    try {
      const r = relative(baseDir, file);
      return r && !r.startsWith("..") ? r.replace(/\\/g, "/") : file;
    } catch {
      return file;
    }
  };
  const walk = (suite) => {
    const file = rel(suite?.file);
    for (const spec of suite?.specs ?? []) {
      const attempts = spec.tests?.flatMap((t) => t.results ?? []) ?? [];
      const status = normalizeStatus(worstStatus(attempts));
      const failed = attempts.find((a) => normalizeStatus(a?.status) !== "passed");
      const duration = attempts.reduce((sum, a) => sum + (a?.duration ?? 0), 0);
      out.push({
        id: file ? `${file} › ${spec.title}` : spec.title,
        title: spec.title,
        file,
        status,
        error: failed?.error?.message ?? null,
        duration_ms: duration || null,
      });
    }
    for (const child of suite?.suites ?? []) walk(child);
  };
  for (const s of report?.suites ?? []) walk(s);
  return out;
}

async function linkNodeModules(dir, nodeModulesDir) {
  const nm = join(dir, "node_modules");
  await rm(nm, { recursive: true, force: true });
  if (IS_WIN) {
    for (const flag of ["/J", "/D"]) {
      try {
        await execFileAsync("cmd", ["/c", "mklink", flag, nm, nodeModulesDir]);
        return;
      } catch {
        // try the next link type
      }
    }
    return;
  }
  try {
    await execFileAsync("ln", ["-s", nodeModulesDir, nm]);
  } catch {
    // specs will surface a clear module-not-found if the link failed
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
      sendJson(res, 500, { error: "run_failed", message: (e.message || "").slice(0, 500) });
    }
    return;
  }

  sendJson(res, 404, { error: "not_found", path: url.pathname });
});

server.listen(PORT, () => {
  console.log(`[qahub-runner] listening on :${PORT}`);
  getInstall().then(
    (i) => console.log(i ? "[qahub-runner] ready" : "[qahub-runner] no Playwright install resolved"),
    (e) => console.log("[qahub-runner] install resolution failed:", (e.message || "").slice(0, 300)),
  );
});
