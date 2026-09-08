/**
 * QA/One runner worker — executes generated Playwright suites in isolation.
 *
 * Receives { suiteId, files: [{ name, content }], baseUrl } over HTTP, writes
 * the suite into a per-request temp project, runs Playwright with the JSON
 * reporter, and returns per-test results.
 *
 * Local-dev friendly: a persistent workspace keeps @playwright/test installed
 * across runs (no per-request npm install) and installs browsers once on first
 * use. Each request's temp project junctions the workspace node_modules so the
 * generated spec's `import "@playwright/test"` resolves instantly.
 *
 * Windows note: npm/npx are .cmd shims, so they are invoked through `cmd /c`
 * (direct execFile cannot spawn a .cmd without a shell).
 */
import { createServer } from "node:http";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { access, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const PORT = Number(process.env.PORT ?? 8787);
const WORKSPACE = process.env.RUNNER_WORKSPACE ?? join(tmpdir(), "qahub-runner-home");
const PLAYWRIGHT_VERSION = "1.63.0";
const IS_WIN = process.platform === "win32";
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
    // Quote args so cmd /c receives a single well-formed command line.
    const quoted = args.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ");
    return execFileAsync("cmd", ["/c", `${cmd} ${quoted}`], opts);
  }
  return execFileAsync(cmd, args, opts);
}

// ---- workspace setup (once) ----

async function ensureWorkspace() {
  if (await exists(join(WORKSPACE, "node_modules"))) return;
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
  console.log("[qahub-runner] installing @playwright/test into workspace (first run only)…");
  await run("npm", ["install", "--no-audit", "--no-fund"], {
    cwd: WORKSPACE,
    timeout: 600_000,
  });
  if (!process.env.RUNNER_DOCKER) {
    console.log("[qahub-runner] installing Playwright chromium browser (first run only)…");
    try {
      await run("npx", ["playwright", "install", "chromium"], {
        cwd: WORKSPACE,
        timeout: 600_000,
      });
    } catch (e) {
      console.log("[qahub-runner] browser install warning:", (e.message || "").slice(0, 300));
    }
  }
}

// ---- run one suite ----

async function runSuite(payload) {
  const { suiteId, files = [], baseUrl } = payload;
  await ensureWorkspace();

  const dir = await mkdtemp(join(tmpdir(), "qahub-run-"));
  try {
    await writeFile(
      join(dir, "package.json"),
      JSON.stringify(
        {
          name: `qahub-${suiteId}`,
          private: true,
          devDependencies: { "@playwright/test": PLAYWRIGHT_VERSION },
        },
        null,
        2,
      ),
    );
    await writeFile(
      join(dir, "playwright.config.js"),
      `module.exports = { testDir: "./tests", reporter: [["json", { outputFile: "results.json" }], ["line"]], use: { baseURL: ${JSON.stringify(
        baseUrl ?? "http://localhost:3000",
      )}, headless: true } };`,
    );
    for (const f of files || []) {
      const target = join(dir, "tests", f.name);
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, f.content);
    }

    // Junction the workspace node_modules so the spec's @playwright/test import
    // resolves without a per-run install.
    await linkNodeModules(dir);

    const cli = join(WORKSPACE, "node_modules", "playwright", "cli.js");
    let stdout = "";
    try {
      ({ stdout } = await execFileAsync(process.execPath, [cli, "test", "--reporter=json"], {
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

async function linkNodeModules(dir) {
  const nm = join(dir, "node_modules");
  await rm(nm, { recursive: true, force: true });
  if (IS_WIN) {
    // Windows directory junction (no admin needed).
    try {
      await execFileAsync("cmd", ["/c", "mklink", "/J", nm, join(WORKSPACE, "node_modules")]);
      return;
    } catch {
      // fall through to symlink
    }
    try {
      await execFileAsync("cmd", ["/c", "mklink", "/D", nm, join(WORKSPACE, "node_modules")]);
      return;
    } catch {
      // leave node_modules absent; the playwright CLI still resolves its own
      // deps from the workspace path.
    }
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
  console.log(`[qahub-runner] workspace: ${WORKSPACE}`);
  ensureWorkspace().then(
    () => console.log("[qahub-runner] workspace ready"),
    (e) => console.log("[qahub-runner] workspace setup failed:", (e.message || "").slice(0, 300)),
  );
});
