/**
 * QA/One runner worker — Phase 0 skeleton.
 *
 * Standalone HTTP worker that the API will dispatch Playwright runs to.
 * Phase 0 ships a /health endpoint and a stub /run that returns a structured
 * "not implemented" response; Phase 1 fills in real suite execution against
 * the mcr.microsoft.com/playwright image.
 *
 * Pattern: PlaywrightExt's local WebSocket bridge + ETL Buddy's sandboxed
 * execution — generated code runs only inside this isolated worker, never on
 * the API host.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.PORT ?? 8787);

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);

  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { status: "ok", service: "qahub-runner", port: PORT });
    return;
  }

  if (req.method === "POST" && url.pathname === "/run") {
    // Phase 1: receive { suiteId, files: {name, content}[] }, execute with
    // @playwright/test in an isolated project dir, stream back JSON results,
    // screenshots and traces.
    sendJson(res, 501, {
      error: "not_implemented",
      message: "Runner execution lands in Phase 1. Health check works.",
    });
    return;
  }

  sendJson(res, 404, { error: "not_found", path: url.pathname });
});

server.listen(PORT, () => {
  console.log(`[qahub-runner] listening on :${PORT}`);
});
