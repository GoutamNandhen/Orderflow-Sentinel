import { test, expect, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const apiUrl = process.env.TEST_API_URL || "http://localhost:8000";
const shopUrl = process.env.TEST_SHOP_URL || "http://localhost:5173";
const consoleUrl = process.env.TEST_CONSOLE_URL || "http://localhost:5174";

test("five customer bookings, independent console, recovery, refund, acceptance and all screens", async ({
  context,
  page: shop,
}) => {
  mkdirSync("docs/screenshots", { recursive: true });
  const externalRequests: string[] = [];
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (["localhost", "127.0.0.1"].includes(url.hostname))
      return route.continue();
    externalRequests.push(url.href);
    return route.abort();
  });
  const consolePage = await context.newPage(),
    errors: string[] = [];
  for (const page of [shop, consolePage]) {
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
  }
  await shop.goto(shopUrl);
  await expect(shop.locator(".product-card")).toHaveCount(20);
  await shop.screenshot({ path: "docs/screenshots/shop-desktop.png" });
  await consolePage.goto(consoleUrl);
  await consolePage
    .locator("input[name=password]")
    .fill(
      process.env.OPERATOR_PASSWORD ||
        readFileSync("backend/data/operator-password.local", "utf8").trim(),
    );
  await consolePage
    .getByRole("button", { name: "Sign In", exact: true })
    .click();
  await expect(
    consolePage.getByText("Connection: Live", { exact: true }).first(),
  ).toBeVisible();
  const token = await consolePage.evaluate(() =>
    localStorage.getItem("sentinel_operator")!,
  );
  const apiHeaders = { Authorization: "Bearer " + token };
  const start = await context.request.get(apiUrl + "/api/demo/status");
  expect((await start.json()).next_sequence).toBe(1);
  const booked: Record<string, unknown>[] = [];
  for (let position = 1; position <= 5; position++) {
    if (position > 1) await shop.locator(".brand").click();
    const product = shop.locator(".product-card").filter({
      hasText:
        position === 4 ? "Humalog Mix25 Insulin" : "Amul Milk & Sourdough",
    });
    await product
      .getByRole("button", { name: "Add to Cart", exact: true })
      .click();
    await shop.getByRole("button", { name: /^Cart / }).click();
    if (position === 1)
      await shop.screenshot({ path: "docs/screenshots/shop-checkout.png" });
    const result = shop.waitForResponse(
      (r) => r.url().endsWith("/api/orders") && r.request().method() === "POST",
    );
    await shop
      .getByRole("button", { name: "Place Order", exact: true })
      .click();
    const response = await result;
    expect(response.status()).toBe(201);
    const order = await response.json();
    booked.push(order);
    expect(order.booking_seq).toBe(position);
    expect(order.initial_failed).toBe([2, 4, 5].includes(position));
    await expect(
      shop.getByRole("heading", { name: "Live Order Tracking" }),
    ).toBeVisible();
    await expect(
      shop.getByRole("button", { name: "Cart 0", exact: true }),
    ).toBeVisible();
    await expect(
      shop.getByText("Connection: Live", { exact: true }).first(),
    ).toBeVisible();
    await expect(consolePage.locator(".kpi").first()).toContainText(
      String(position),
    );
  }
  // Timeout recovers through an actual backend job, and does not claim delivery.
  await expect
    .poll(async () => {
      const result = await context.request.get(
        apiUrl + "/api/console/orders?q=ORD-000002",
        { headers: apiHeaders },
      );
      return (await result.json()).items[0].status;
    })
    .toBe("CONFIRMED");
  const queue = await context.request.get(apiUrl + "/api/console/incidents", {
    headers: apiHeaders,
  });
  const incidents = (await queue.json()).items;
  expect(incidents).toHaveLength(3);
  const timeout = incidents.find(
    (i: { order_id: string }) => i.order_id === "ORD-000002",
  );
  expect(timeout.resolved_by).toBe("ENGINE");
  expect(timeout.order.fulfilment).toBe("UNFULFILLED");
  expect(timeout.model_output.confidence).toBeGreaterThanOrEqual(0.9);
  await consolePage.screenshot({
    path: "docs/screenshots/console-dashboard.png",
  });
  await consolePage.getByRole("button", { name: /Incidents Queue/ }).click();
  await expect(
    consolePage.getByRole("heading", { name: "Incident Queue", exact: true }),
  ).toBeVisible();
  await consolePage.screenshot({ path: "docs/screenshots/console-queue.png" });
  const row = consolePage.getByRole("row").filter({ hasText: "ORD-000004" });
  await row.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(
    consolePage.getByRole("heading", { name: /Incident Investigation/ }),
  ).toBeVisible();
  await expect(
    consolePage.getByRole("button", { name: "Approve Suggested", exact: true }),
  ).toBeDisabled();
  await consolePage.screenshot({
    path: "docs/screenshots/console-incident.png",
    fullPage: true,
  });
  await shop.getByLabel("Select order to track").selectOption("ORD-000004");
  await expect(shop.getByText("DEBIT UNKNOWN", { exact: true })).toBeVisible();
  await shop.screenshot({ path: "docs/screenshots/shop-payment-review.png" });
  // Review the ledger, then explicitly confirm a refund. No extra debit.
  await consolePage
    .getByRole("button", { name: "CHECK PAYMENT", exact: true })
    .click();
  let actionResponse = consolePage.waitForResponse((r) =>
    /\/incidents\/[^/]+\/action$/.test(r.url()),
  );
  await consolePage
    .getByRole("button", { name: "Execute CHECK PAYMENT", exact: true })
    .click();
  let outcome = await (await actionResponse).json();
  expect(outcome.ok).toBe(true);
  expect(outcome.incident.order.payment.attempt_count).toBe(1);
  await expect(
    consolePage.getByRole("button", { name: "REFUND", exact: true }),
  ).toBeEnabled();
  await consolePage
    .getByRole("button", { name: "REFUND", exact: true })
    .click();
  await consolePage
    .getByRole("button", { name: "Execute REFUND", exact: true })
    .click();
  await expect(consolePage.getByRole("dialog")).toBeVisible();
  await consolePage.screenshot({
    path: "docs/screenshots/console-refund-confirmation.png",
  });
  actionResponse = consolePage.waitForResponse((r) =>
    /\/incidents\/[^/]+\/action$/.test(r.url()),
  );
  await consolePage
    .getByRole("button", { name: "Confirm & Execute", exact: true })
    .click();
  outcome = await (await actionResponse).json();
  expect(outcome.incident.order.refund.status).toBe("PENDING");
  await expect(shop.getByText("Refund PENDING", { exact: true })).toBeVisible();
  await shop.screenshot({ path: "docs/screenshots/shop-refund-pending.png" });
  await expect(shop.getByText("Refund COMPLETED", { exact: true })).toBeVisible(
    { timeout: 15000 },
  );
  // Stock transfer is one-click restricted despite low numeric risk. Offer waits for acceptance.
  await consolePage.getByRole("button", { name: /Incidents Queue/ }).click();
  await consolePage
    .getByRole("row")
    .filter({ hasText: "ORD-000005" })
    .getByRole("button", { name: "Inspect", exact: true })
    .click();
  await expect(
    consolePage.getByRole("button", { name: "Approve Suggested", exact: true }),
  ).toBeEnabled();
  await consolePage
    .getByRole("button", { name: "OFFER SUBSTITUTE", exact: true })
    .click();
  actionResponse = consolePage.waitForResponse((r) =>
    /\/incidents\/[^/]+\/action$/.test(r.url()),
  );
  await consolePage
    .getByRole("button", { name: "Execute OFFER SUBSTITUTE", exact: true })
    .click();
  outcome = await (await actionResponse).json();
  expect(outcome.incident.status).not.toBe("RESOLVED");
  await shop.getByLabel("Select order to track").selectOption("ORD-000005");
  await expect(
    shop.getByRole("button", { name: "Accept Change", exact: true }),
  ).toBeVisible();
  await shop.screenshot({ path: "docs/screenshots/shop-offer-acceptance.png" });
  await shop
    .getByRole("button", { name: "Accept Change", exact: true })
    .click();
  await expect(
    shop.getByText("The order issue has been resolved.", { exact: false }),
  ).not.toBeVisible();
  await expect(
    shop.getByText("Your accepted change has been applied.", { exact: false }),
  ).toBeVisible();
  await expect(
    consolePage.getByText("RESOLVED", { exact: true }).first(),
  ).toBeVisible();
  // Every console destination is connected; export and retraining are actual jobs.
  await consolePage
    .getByRole("button", { name: "Resolution History", exact: true })
    .click();
  await expect(
    consolePage.getByText("ORD-000004", { exact: true }),
  ).toBeVisible();
  const download = consolePage.waitForEvent("download");
  await consolePage
    .getByRole("button", { name: "Export Filtered CSV" })
    .click();
  expect((await download).suggestedFilename()).toBe(
    "sentinel-filtered-history.csv",
  );
  await consolePage.screenshot({
    path: "docs/screenshots/console-history.png",
  });
  for (const [name, title] of [
    ["Orders", "Platform Orders Directory"],
    ["Gateway Health", "Gateway & Partner Circuit Health"],
    ["Analytics", "Incident & Recovery Analytics"],
    ["Settings", "Simulator & Guardrail Settings"],
  ]) {
    await consolePage
      .getByRole("navigation", { name: "Console navigation" })
      .getByRole("button", { name, exact: true })
      .click();
    await expect(
      consolePage.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
  }
  await consolePage
    .getByRole("button", { name: "Retrain Model", exact: true })
    .click();
  await expect(
    consolePage.getByText("DONE", { exact: true }).first(),
  ).toBeVisible({ timeout: 30000 });
  await consolePage.screenshot({
    path: "docs/screenshots/console-settings.png",
    fullPage: true,
  });
  await shop.setViewportSize({ width: 390, height: 844 });
  await shop.screenshot({
    path: "docs/screenshots/shop-tracking-mobile.png",
    fullPage: true,
  });
  await shop.locator(".brand").click();
  await shop.screenshot({ path: "docs/screenshots/shop-mobile.png" });
  expect(
    await shop.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await consolePage.setViewportSize({ width: 390, height: 844 });
  await consolePage.getByRole("button", { name: /Incidents Queue/ }).click();
  await consolePage.getByLabel("Incident status filter").selectOption("");
  await consolePage
    .getByRole("row")
    .filter({ hasText: "ORD-000005" })
    .getByRole("button", { name: "Inspect", exact: true })
    .click();
  await expect(
    consolePage.getByRole("heading", { name: "Risk Score Breakdown" }),
  ).toBeVisible();
  await consolePage.screenshot({
    path: "docs/screenshots/console-incident-mobile.png",
    fullPage: true,
  });
  expect(
    await consolePage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await consolePage
    .getByRole("button", { name: "Dashboard", exact: true })
    .click();
  await consolePage.screenshot({
    path: "docs/screenshots/console-mobile.png",
    fullPage: true,
  });
  expect(
    await consolePage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await context.storageState({ path: "work/browser-session.json" });
  expect(externalRequests).toEqual([]);
  expect(errors).toEqual([]);
});

test("reference screenshots at desktop and mobile", async ({ page }) => {
  await page.goto(pathToFileURL(resolve("docs/reference.html")).href, {
    waitUntil: "networkidle",
    timeout: 60000,
  });
  await page.screenshot({
    path: "docs/screenshots/reference-shop-desktop.png",
  });
  await page.locator("#switcher-sentinel").click();
  await page.screenshot({
    path: "docs/screenshots/reference-console-desktop.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "docs/screenshots/reference-console-mobile.png",
  });
  await page.locator("#switcher-shopease").click();
  await page.screenshot({ path: "docs/screenshots/reference-shop-mobile.png" });
});
