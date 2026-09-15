import { expect, test } from "@playwright/test";

test("agent dropdown and call mode preserve the prompt and route each request", async ({ page }, testInfo) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) =>
    route.fulfill({ json: { answer: "Test answer", citations: [], execution: null } }),
  );
  await page.goto("/");

  const question = "List the buildings and their active alerts.";
  await page.getByRole("textbox", { name: "Building question" }).fill(question);
  const agentSelect = page.getByRole("combobox", { name: "Agent", exact: true });
  await expect(agentSelect).toHaveValue("live");
  await expect(page.getByRole("button", { name: "Foundry", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /Quick lookup|Live operations|Compliance analysis/ })).toHaveCount(0);

  for (const [agent, scenario] of [
    ["general", null],
    ["quick", "quick"],
    ["live", "live"],
    ["compliance", "compliance"],
  ]) {
    await agentSelect.selectOption(agent!);
    await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(question);
    const pendingRequest = page.waitForRequest(
      (request) => request.url().endsWith("/ask") && request.method() === "POST",
    );
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const request = await pendingRequest;
    expect(request.postDataJSON()).toEqual({ question, scenario });
    await expect(page.getByText("Test answer", { exact: true })).toBeVisible();
  }

  await page.screenshot({ path: testInfo.outputPath("foundry-agent-select.png"), fullPage: true });
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(page.getByText("Test answer", { exact: true })).toBeHidden();
  await expect(agentSelect).toBeHidden();
  await expect(page.getByRole("button", { name: "AI Gateway", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(question);
  const editedQuestion = "What drives cooling demand?";
  await page.getByRole("textbox", { name: "Building question" }).fill(editedQuestion);
  const gatewayRequest = page.waitForRequest(
    (request) => request.url().endsWith("/ask") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await gatewayRequest).postDataJSON()).toEqual({ question: editedQuestion, scenario: "governed" });
  await expect(page.getByText("Test answer", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("gateway-mode.png"), fullPage: true });
  await page.getByRole("button", { name: "Foundry", exact: true }).click();
  await expect(agentSelect).toHaveValue("compliance");
  await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(editedQuestion);
  const foundryRequest = page.waitForRequest(
    (request) => request.url().endsWith("/ask") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await foundryRequest).postDataJSON()).toEqual({ question: editedQuestion, scenario: "compliance" });
  await expect(page.getByText("Test answer", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});