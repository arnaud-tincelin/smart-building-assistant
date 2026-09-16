import { expect, test } from "@playwright/test";

test("answer shows model and mode with execution metrics collapsed", async ({ page }, testInfo) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "quality", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: "Paris HQ has an active ventilation alert.",
    citations: [],
    execution: {
      mode: "agents",
      requested_model: "model-router",
      reported_model: "gpt-4o-mini-2024-07-18",
      selected_model: "gpt-4o-mini-2024-07-18",
      routing_mode: "quality",
      latency_ms: 9650,
      response_id: "resp_01234567890123456789",
      routing_explanation: "Quality mode prioritizes model quality.",
      tools_used: ["operations_getBuildingData"],
      usage: {
        input_tokens: 1000, output_tokens: 95, total_tokens: 1095,
        reasoning_tokens: 20, cached_tokens: 0, cache_write_tokens: 0,
      },
    },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Paris HQ has an active ventilation alert.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "gpt-4o-mini-2024-07-18" })).toBeVisible();
  await expect(page.locator(".model-execution .routing-mode")).toHaveText("quality");
  const details = page.locator(".routing-details");
  for (const label of ["Agent latency", "Response tokens", "Response ID"]) {
    await expect(details.getByText(label, { exact: true })).toBeHidden();
  }
  await page.screenshot({ path: testInfo.outputPath("answer-collapsed.png"), fullPage: true });
  await page.getByText("Show more details", { exact: true }).click();
  for (const label of ["Agent latency", "Response tokens", "Response ID"]) {
    await expect(details.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(details.getByText("9.65 s", { exact: true })).toBeVisible();
  await expect(details.getByText("1,095", { exact: true })).toBeVisible();
  await expect(details.getByText("Quality mode prioritizes model quality.")).toBeVisible();
  await expect(details.getByText("operations_getBuildingData", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("answer-expanded.png"), fullPage: true });
  await page.getByText("Show more details", { exact: true }).click();
  await expect(details.getByText("Agent latency", { exact: true })).toBeHidden();
});

test("gateway response displays its own model and expandable measurements", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "cost", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: "Gateway result.",
    citations: [],
    execution: {
      mode: "gateway", requested_model: "gpt-5-mini",
      reported_model: "gpt-5-mini-2025-08-07", selected_model: "gpt-5-mini-2025-08-07",
      routing_mode: null, latency_ms: 1250, response_id: "chatcmpl-test",
      usage: null, tools_used: [], routing_explanation: "Reported by the final gateway response.",
    },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByRole("heading", { name: "gpt-5-mini-2025-08-07" })).toBeVisible();
  await expect(page.locator(".model-execution .routing-mode")).toHaveText("Fixed model");
  await page.getByText("Show more details", { exact: true }).click();
  await expect(page.getByText("Gateway latency", { exact: true })).toBeVisible();
  await expect(page.getByText("1.25 s", { exact: true })).toBeVisible();
  await expect(page.getByText("chatcmpl-test", { exact: true })).toBeVisible();
});

test("missing attribution is explicit and never replaced with the deployment name", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: "An answer with incomplete metadata.", citations: [],
    execution: {
      mode: "agents", requested_model: "model-router", reported_model: "model-router",
      selected_model: null, routing_mode: null, latency_ms: 100, response_id: null,
      usage: null, tools_used: [], routing_explanation: "The service did not disclose the model.",
    },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Model not disclosed", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "model-router", exact: true })).toHaveCount(0);
  await expect(page.locator(".routing-mode")).toHaveText("Router mode unavailable");
  await page.getByText("Show more details", { exact: true }).click();
  const total = page.locator(".execution-metrics > div").filter({
    has: page.getByText("Response tokens", { exact: true }),
  });
  await expect(total.locator("dd")).toHaveText("Not reported");
});

test("Markdown answer tables are readable without overflowing the page", async ({ page }, testInfo) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: [
      "Current active alerts:",
      "",
      "| Building | Building ID | Active alerts |",
      "|---|---|---|",
      "| Contoso Energy HQ | `paris-hq` | **ALT-PAR-001** - Cooling demand above baseline. |",
      "| Contoso Innovation Center | `seattle-lab` | None |",
    ].join("\n"),
    citations: [], execution: null,
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  const table = page.getByRole("region", { name: "Answer table" }).getByRole("table");
  await expect(table.getByRole("columnheader")).toHaveCount(3);
  await expect(table.getByRole("row")).toHaveCount(3);
  await expect(table.getByRole("cell", { name: "Contoso Energy HQ", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("answer-table.png"), fullPage: true });
});