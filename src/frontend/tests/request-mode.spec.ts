import { expect, test } from "@playwright/test";

test("single agent and gateway modes preserve the prompt and route each request", async ({ page }, testInfo) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) =>
    route.fulfill({ json: { answer: "Test answer", citations: [], execution: null } }),
  );
  await page.goto("/");

  const question = "List the buildings and their active alerts.";
  await page.getByRole("textbox", { name: "Building question" }).fill(question);
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Agents", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /Quick lookup|Live operations|Compliance analysis/ })).toHaveCount(0);

  for (const [label, mode, count] of [
    ["Agents", "agents", 1],
    ["AI Gateway", "gateway", 1],
    ["Agents", "agents", 2],
  ] as const) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(question);
    const pendingRequest = page.waitForRequest(
      (request) => request.url().endsWith("/ask") && request.method() === "POST",
    );
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const request = await pendingRequest;
    expect(request.postDataJSON()).toEqual({ question, mode });
    await expect(page.getByText("Test answer", { exact: true })).toHaveCount(count);
    await expect(page.getByText("Test answer", { exact: true }).last()).toBeVisible();
  }

  await page.screenshot({ path: testInfo.outputPath("agents-mode.png"), fullPage: true });
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(page.getByText("Test answer", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Router:/ })).toHaveCount(0);
  await expect(page.getByText("Model: gpt-5-mini", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "AI Gateway", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(question);
  const editedQuestion = "What drives cooling demand?";
  await page.getByRole("textbox", { name: "Building question" }).fill(editedQuestion);
  const gatewayRequest = page.waitForRequest(
    (request) => request.url().endsWith("/ask") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await gatewayRequest).postDataJSON()).toEqual({ question: editedQuestion, mode: "gateway" });
  await expect(page.getByText("Test answer", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Test answer", { exact: true }).last()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("gateway-mode.png"), fullPage: true });
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Router:/ })).toBeVisible();
  await expect(page.getByText("Model: gpt-5-mini", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Building question" })).toHaveValue(editedQuestion);
  const foundryRequest = page.waitForRequest(
    (request) => request.url().endsWith("/ask") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  expect((await foundryRequest).postDataJSON()).toEqual({ question: editedQuestion, mode: "agents" });
  await expect(page.getByText("Test answer", { exact: true })).toHaveCount(3);
  await expect(page.getByText("Test answer", { exact: true }).last()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("switching modes cancels in the original history and ignores a stale answer after returning", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  let release: () => void = () => {};
  const pendingAnswer = new Promise<void>((resolve) => { release = resolve; });
  let agentRequests = 0;
  await page.route("**/ask", async (route) => {
    if (route.request().postDataJSON().mode === "agents" && agentRequests++ === 0) {
      await pendingAnswer;
      await route.fulfill({ json: { answer: "Stale agent answer", citations: [] } });
    } else {
      await route.fulfill({ json: {
        answer: route.request().postDataJSON().mode === "gateway" ? "Gateway answer" : "Recovered agent answer",
        citations: [],
      } });
    }
  });
  await page.goto("/");
  const prompt = page.getByRole("textbox", { name: "Building question" });
  await prompt.fill("Cancelled agent question");
  const started = page.waitForRequest((request) => request.url().endsWith("/ask"));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await started;
  const staleFinished = page.waitForEvent("requestfailed",
    (request) => request.url().endsWith("/ask") && request.postDataJSON().mode === "agents");
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeEnabled();
  await expect(page.getByRole("article", { name: "User message", exact: true })).toHaveCount(0);
  await expect(page.getByText("Request cancelled after switching modes.", { exact: true })).toHaveCount(0);
  await prompt.fill("Gateway question");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Gateway answer", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(page.getByRole("article", { name: "User message", exact: true })).toContainText("Cancelled agent question");
  await expect(page.getByRole("status")).toHaveText("Request cancelled after switching modes.");
  release();
  await staleFinished;
  await expect(page.getByText("Stale agent answer", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("article", { name: "Assistant reply", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Model execution" })).toHaveCount(0);
  await prompt.fill("Recovered agent question");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Recovered agent answer", { exact: true })).toBeVisible();
  await expect(page.getByRole("article", { name: "User message", exact: true })).toHaveCount(2);
  await expect(page.getByRole("status")).toHaveText("Request cancelled after switching modes.");
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(page.getByText("Gateway answer", { exact: true })).toBeVisible();
  await expect(page.getByText("Recovered agent answer", { exact: true })).toHaveCount(0);
});

test("gateway stays usable when agent router settings are unavailable", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ status: 503, json: { detail: "Router unavailable" } }),
  );
  await page.route("**/ask", (route) => {
    expect(route.request().postDataJSON().mode).toBe("gateway");
    return route.fulfill({ json: { answer: "Fixed-model answer", citations: [], execution: null } });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Router: unavailable", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Router:/ })).toHaveCount(0);
  await expect(page.locator(".router-load-error")).toHaveCount(0);
  await expect(page.getByText("Model: gpt-5-mini", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Fixed-model answer", { exact: true })).toBeVisible();
});