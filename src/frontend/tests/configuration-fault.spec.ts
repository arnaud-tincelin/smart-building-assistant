import { expect, test } from "@playwright/test";

for (const mode of ["Agents", "AI Gateway"]) {
  test(`${mode} displays a configuration fault and recovers on retry`, async ({ page }, testInfo) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({
      json: { mode: "balanced", editable: false, explicitly_set: false },
    }));
    let broken = true;
    await page.route("**/ask", (route) => route.fulfill(broken ? {
      status: 503,
      json: { detail: "Building operations unavailable: configuration_error. Reference: CFG-TEST" },
    } : {
      json: { answer: "Building operations recovered.", citations: [], execution: null },
    }));
    await page.goto("/");
    await page.getByRole("button", { name: mode, exact: true }).click();
    const question = page.getByRole("textbox", { name: "Building question" });
    await question.fill("List the Contoso buildings.");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    const history = page.getByRole("log", { name: "Conversation history" });
    await expect(history.getByRole("alert")).toContainText(
      "Building operations unavailable: configuration_error. Reference: CFG-TEST",
    );
    await expect(history.getByRole("article", { name: "Assistant reply", exact: true })).toHaveCount(0);
    await expect(question).toHaveValue("List the Contoso buildings.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath("configuration-fault.png"), fullPage: true });
    broken = false;
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Building operations recovered.", { exact: true })).toBeVisible();
    await expect(history.getByRole("alert")).toContainText("Reference: CFG-TEST");
    await expect(history.getByRole("article", { name: "Assistant reply", exact: true })).toHaveCount(1);
    await expect(history.getByRole("article", { name: "User message", exact: true })).toHaveCount(2);
  });

  test(`${mode} shows throttling clearly and keeps retry available`, async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({
      json: { mode: "balanced", editable: false },
    }));
    await page.route("**/ask", (route) => route.fulfill({
      status: 429,
      headers: { "Retry-After": "21" },
      json: { detail: "The model is rate-limited. Retry after 21s." },
    }));
    await page.goto("/");
    await page.getByRole("button", { name: mode, exact: true }).click();
    const question = page.getByRole("textbox", { name: "Building question" });
    await question.fill("List the Contoso buildings.");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("rate-limited. Retry after 21s.");
    await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeEnabled();
    await expect(question).toHaveValue("List the Contoso buildings.");
    await expect(page.getByRole("article", { name: "Assistant reply", exact: true })).toHaveCount(0);
  });
}