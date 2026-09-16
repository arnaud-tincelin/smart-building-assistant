import { expect, test } from "@playwright/test";

for (const mode of ["Foundry", "AI Gateway"]) {
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
    await expect(page.getByText(
      "Building operations unavailable: configuration_error. Reference: CFG-TEST",
      { exact: true },
    )).toBeVisible();
    await expect(question).toHaveValue("List the Contoso buildings.");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath("configuration-fault.png"), fullPage: true });
    broken = false;
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText("Building operations recovered.", { exact: true })).toBeVisible();
    // The failed exchange remains in the transcript (AC7): retrying does not
    // erase or relabel history, it only appends a new, successful turn.
    await expect(page.getByText(
      "Building operations unavailable: configuration_error. Reference: CFG-TEST",
      { exact: true },
    )).toBeVisible();
  });
}