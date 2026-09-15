import { expect, test } from "@playwright/test";

test("answer shows model and mode with execution metrics collapsed", async ({ page }, testInfo) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "quality", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: "Paris HQ has an active ventilation alert.",
    citations: [],
    execution: {
      selected_model: "gpt-5-mini-2025-08-07",
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
  await expect(page.getByRole("heading", { name: "gpt-5-mini-2025-08-07" })).toBeVisible();
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
  await page.screenshot({ path: testInfo.outputPath("answer-expanded.png"), fullPage: true });
  await page.getByText("Show more details", { exact: true }).click();
  await expect(details.getByText("Agent latency", { exact: true })).toBeHidden();
});