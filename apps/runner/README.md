# QA/One Playwright runner — sandboxed test executor.
#
# Phase 0: skeleton worker. Phase 1: receives generated suites over HTTP from
# the API, runs them in an isolated Playwright context, streams JSON results +
# screenshots + traces back, and supports the approve-gated self-heal loop
# (VisionTestAI pattern: locator patch -> re-run, cap 3 attempts).
