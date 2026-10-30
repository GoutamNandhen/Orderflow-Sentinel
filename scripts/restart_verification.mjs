// Run with ports 8000 free, 5173/5174 serving the two applications.
// Uses a new isolated DB and never resets existing application data.
import { chromium } from "playwright";
import { expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
const apiPort = process.env.TEST_API_PORT || "8000";
const apiUrl = `http://localhost:${apiPort}`;
const shopUrl = process.env.TEST_SHOP_URL || "http://localhost:5173";
const consoleUrl = process.env.TEST_CONSOLE_URL || "http://localhost:5174";
const root = fileURLToPath(new URL("..", import.meta.url));
const testOperatorPassword = crypto.randomUUID() + crypto.randomUUID();
const db = resolve(
  root,
  "work",
  `restart-${crypto.randomUUID()}.db`,
).replaceAll("\\", "/");
mkdirSync(resolve(root, "work"), { recursive: true });
mkdirSync(resolve(root, "docs/screenshots"), { recursive: true });
let server, browser, shop, consolePage;
let stage = "starting";
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function start() {
  server = spawn(
    resolve(root, ".venv/Scripts/python.exe"),
    [
      "-m",
      "uvicorn",
      "backend.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      apiPort,
      "--log-level",
      "warning",
    ],
    {
      cwd: root,
      env: {
        ...process.env,
        DATABASE_URL: "sqlite:///" + db,
        OPERATOR_PASSWORD: testOperatorPassword,
      },
      windowsHide: true,
      stdio: "pipe",
    },
  );
  server.stderr.on("data", (data) => process.stderr.write(data));
  for (let n = 0; n < 200; n++) {
    if (server.exitCode !== null)
      throw new Error("Backend exited unexpectedly");
    try {
      const r = await fetch(apiUrl + "/api/health");
      if (r.ok) return;
    } catch {}
    await delay(100);
  }
  throw new Error("Backend did not become healthy");
}
async function stop() {
  if (!server || server.exitCode !== null) return;
  const old = server;
  old.kill();
  await Promise.race([new Promise((r) => old.once("exit", r)), delay(10000)]);
}
try {
  try {
    const r = await fetch(apiUrl + "/api/health");
    if (r.ok)
      throw new Error(
        "Port 8000 must be free. Stop the existing backend before running this isolated test.",
      );
  } catch (e) {
    if (e.message.startsWith("Port 8000")) throw e;
  }
  await start();
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    timezoneId: "Asia/Kolkata",
  });
  const customer = crypto.randomUUID() + crypto.randomUUID();
  await context.addCookies([
    { name: "of_customer", value: customer, domain: "localhost", path: "/" },
  ]);
  shop = await context.newPage();
  consolePage = await context.newPage();
  const appErrors = [];
  for (const p of [shop, consolePage])
    p.on("pageerror", (e) => appErrors.push(e.message));
  await shop.goto(shopUrl);
  await consolePage.goto(consoleUrl);
  await consolePage.locator("input[name=password]").fill(testOperatorPassword);
  await consolePage
    .getByRole("button", { name: "Sign In", exact: true })
    .click();
  await expect(
    consolePage.getByText("Connection: Live", { exact: true }).first(),
  ).toBeVisible();
  const operator = await consolePage.evaluate(() =>
    localStorage.getItem("sentinel_operator"),
  );
  const headers = {
    Authorization: "Bearer " + operator,
    "X-Customer-Session": customer,
    "Idempotency-Key": crypto.randomUUID(),
  };
  const config = await (
    await context.request.get(apiUrl + "/api/console/settings", {
      headers,
    })
  ).json();
  await context.request.post(apiUrl + "/api/console/settings", {
    headers,
    data: { ...config, force_error: "API_TIMEOUT", retry_failures: 2 },
  });
  const response = await context.request.post(apiUrl + "/api/orders", {
    headers,
    data: {
      user_name: "Restart Demo Customer",
      phone: "DEMO_CONTACT",
      address: "DEMO_LOCATION",
      contact_mode: "demo",
      pincode: "560038",
      payment_method: "UPI",
      items: [{ product_id: "PROD-109", qty: 1 }],
    },
  });
  const order = await response.json();
  expect(order.status).toBe("AUTO_FIXING");
  await shop.goto(
    `${shopUrl}/?order=${order.id}&token=${encodeURIComponent(order.tracking_token)}`,
  );
  await expect(
    shop.getByText("Connection: Live", { exact: true }).first(),
  ).toBeVisible();
  const before = await (
    await context.request.get(apiUrl + "/api/console/jobs", {
      headers,
    })
  ).json();
  expect(before.some((j) => j.status === "PENDING")).toBe(true);
  await shop.screenshot({
    path: resolve(root, "docs/screenshots/restart-before.png"),
  });
  await stop();
  stage = "backend stopped";
  await expect(
    consolePage.getByText("Reconnecting", { exact: true }).first(),
  ).toBeVisible({ timeout: 10000 });
  await delay(1200);
  await start();
  stage = "backend restarted, waiting for sockets";
  await expect(
    consolePage.getByText("Connection: Live", { exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    shop.getByText("Connection: Live", { exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  await expect
    .poll(
      async () => {
        const r = await context.request.get(
          apiUrl + "/api/orders/" + order.id,
          { headers },
        );
        return (await r.json()).status;
      },
      { timeout: 20000 },
    )
    .toBe("CONFIRMED");
  const after = await (
    await context.request.get(apiUrl + "/api/orders/" + order.id, {
      headers,
    })
  ).json();
  const sequence = await (
    await context.request.get(apiUrl + "/api/demo/status")
  ).json();
  const products = await (
    await context.request.get(apiUrl + "/api/products")
  ).json();
  expect(after.attempt_count).toBe(3);
  expect(after.payment.attempt_count).toBe(1);
  expect(after.fulfilment).toBe("UNFULFILLED");
  expect(sequence.next_sequence).toBe(2);
  expect(products.find((p) => p.id === "PROD-109").stock).toBe(99);
  expect(appErrors).toEqual([]);
  await shop.screenshot({
    path: resolve(root, "docs/screenshots/restart-after.png"),
  });
  const result = {
    passed: true,
    timestamp: new Date().toISOString(),
    checks: {
      actual_backend_process_restart: true,
      pending_recovery_resumed: true,
      independent_tabs_reconnected: true,
      private_customer_snapshot_resynchronised: true,
      operator_session_survived: true,
      sequence_preserved: true,
      stock_reservation_preserved: true,
      payment_not_double_charged: true,
      attempt_count: after.attempt_count,
      fulfilment: after.fulfilment,
    },
    appErrors,
  };
  writeFileSync(
    resolve(root, "docs/restart-results.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error("Restart verification stage:", stage);
  if (consolePage) {
    console.error(
      (await consolePage.locator("body").innerText()).slice(0, 2200),
    );
    console.error(
      "Local operator token retained:",
      !!(await consolePage.evaluate(() =>
        localStorage.getItem("sentinel_operator"),
      )),
    );
  }
  throw error;
} finally {
  await browser?.close();
  await stop();
}
