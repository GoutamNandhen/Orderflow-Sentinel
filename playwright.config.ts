import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  workers: 1,
  retries: 0,
  timeout: 120000,
  use: {
    headless: true,
    viewport: { width: 1440, height: 1000 },
    timezoneId: "Asia/Kolkata",
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["json", { outputFile: "docs/browser-results.json" }]],
  outputDir: "work/browser-artifacts",
});
