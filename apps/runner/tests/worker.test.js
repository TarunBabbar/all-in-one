import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";

const PORT = 8791; // distinct from dev default so tests never clash

test("runner boots and /health responds ok", async () => {
  const child = spawn(process.execPath, ["worker.js"], {
    env: { ...process.env, PORT: String(PORT) },
    stdio: ["ignore", "pipe", "pipe"],
  });

  try {
    // Wait for the server to accept connections.
    const base = `http://localhost:${PORT}`;
    let ok = false;
    for (let i = 0; i < 50; i++) {
      try {
        const r = await fetch(`${base}/health`);
        if (r.ok) {
          ok = true;
          break;
        }
      } catch {
        // not up yet
      }
      await new Promise((res) => setTimeout(res, 100));
    }
    assert.ok(ok, "runner did not become healthy in time");

    const body = await (await fetch(`${base}/health`)).json();
    assert.equal(body.status, "ok");
    assert.equal(body.service, "qahub-runner");

    // Unknown route -> 404.
    const missing = await fetch(`${base}/nope`);
    assert.equal(missing.status, 404);
  } finally {
    child.kill();
  }
});

test("runner /run is a Phase 1 stub (501)", async () => {
  const child = spawn(process.execPath, ["worker.js"], {
    env: { ...process.env, PORT: String(PORT + 1) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  try {
    const base = `http://localhost:${PORT + 1}`;
    let ok = false;
    for (let i = 0; i < 50; i++) {
      try {
        const r = await fetch(`${base}/health`);
        if (r.ok) {
          ok = true;
          break;
        }
      } catch {
        // not up yet
      }
      await new Promise((res) => setTimeout(res, 100));
    }
    assert.ok(ok, "runner did not become healthy in time");

    const res = await fetch(`${base}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suiteId: "test" }),
    });
    assert.equal(res.status, 501);
    const body = await res.json();
    assert.equal(body.error, "not_implemented");
  } finally {
    child.kill();
  }
});
