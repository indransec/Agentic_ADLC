// End-to-end tests (feature 022, research R-10): Chromium against a deterministic platform
// (tests/e2e/stack.py: seeded harness database, stub agents, the real API and adlc-web serving
// web/dist). `make web-e2e` builds web/dist first.
import { defineConfig, devices } from "@playwright/test";

const UI_PORT = process.env["E2E_UI_PORT"] ?? "8611";
const API_PORT = process.env["E2E_API_PORT"] ?? "8612";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // one seeded platform, shared in order
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${UI_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `env -u VIRTUAL_ENV uv run python -m tests.e2e.stack --ui-port ${UI_PORT} --api-port ${API_PORT} --state web/e2e/.stack.json`,
    cwd: "..",
    url: `http://127.0.0.1:${UI_PORT}/health`,
    timeout: 180_000,
    reuseExistingServer: false,
    stdout: "ignore",
    stderr: "pipe",
  },
});
