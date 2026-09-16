import { expect, test } from "@playwright/test";

test("router stays visible when settings cannot be loaded", async ({ page }, testInfo) => {
  let updates = 0;
  await page.route("**/model-router/mode", (route) => {
    if (route.request().method() === "PUT") updates += 1;
    return route.fulfill({ status: 500, body: "Backend unavailable" });
  });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Router: unavailable", exact: true });
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(page.getByRole("menuitemradio")).toHaveCount(3);
  await expect(page.getByRole("menuitemradio", { checked: true })).toHaveCount(0);
  const cost = page.getByRole("menuitemradio", { name: "Cost", exact: true });
  await expect(cost).toHaveAttribute("aria-disabled", "true");
  await cost.click({ force: true });
  await expect(page.getByRole("status")).toContainText("Routing settings unavailable");
  expect(updates).toBe(0);
  await page.screenshot({ path: testInfo.outputPath("router-unavailable.png"), fullPage: true });
});

test("composer router selects modes with tooltips and keyboard dismissal", async ({ page }, testInfo) => {
  let mode = "balanced";
  const changes: string[] = [];
  await page.route("**/model-router/mode", async (route) => {
    if (route.request().method() === "PUT") {
      mode = route.request().postDataJSON().mode;
      changes.push(mode);
    }
    await route.fulfill({ json: {
      mode, editable: true, propagation_seconds: 300,
      model_subset: ["gpt-4o-mini", "gpt-5.6-sol"],
    } });
  });
  await page.goto("/");
  const trigger = page.getByRole("button", { name: /^Router:/ });
  await expect(page.locator(".ask-form").getByRole("button", { name: /^Router:/ })).toBeVisible();
  await expect(page.getByText("Router models: gpt-4o-mini / gpt-5.6-sol")).toBeVisible();
  await trigger.click();
  await expect(page.getByRole("menuitemradio", { name: "Balanced", exact: true })).toHaveAttribute("aria-checked", "true");
  for (const [label, description] of [
    ["Cost", "Cheapest model that clears a wider quality band"],
    ["Balanced", "Cheapest model within ~1-2% of top quality"],
    ["Quality", "Highest-rated model, cost ignored"],
  ]) {
    await page.getByRole("menuitemradio", { name: label, exact: true }).hover();
    await expect(page.getByRole("tooltip", { name: description, exact: true })).toBeVisible();
  }
  await page.screenshot({ path: testInfo.outputPath("router-open.png"), fullPage: true });
  await page.getByRole("menuitemradio", { name: "Cost", exact: true }).click();
  await expect(trigger).toHaveAccessibleName("Router: cost");
  await expect(page.getByText("Router models: gpt-4o-mini / gpt-5.6-sol")).toBeVisible();
  await expect(page.getByRole("menu")).toHaveCount(0);
  expect(changes).toEqual(["cost"]);
  await expect(page.getByRole("status")).toContainText("5 min");
  await trigger.press("ArrowDown");
  await expect(page.getByRole("menuitemradio", { name: "Cost", exact: true })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitemradio", { name: "Balanced", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await trigger.click();
  await page.getByRole("heading", { name: "Ask about operations" }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("router preserves read-only and failed update states", async ({ page }) => {
  await page.route("**/model-router/mode", (route) => route.fulfill({ json: { mode: "balanced", editable: false } }));
  await page.goto("/");
  await page.getByRole("button", { name: /^Router:/ }).click();
  await expect(page.getByRole("menuitemradio", { name: "Cost", exact: true })).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText("Routing is read-only in this environment.")).toBeVisible();
  await page.unroute("**/model-router/mode");
  await page.route("**/model-router/mode", (route) => route.request().method() === "PUT"
    ? route.fulfill({ status: 500, json: { detail: "Routing update failed" } })
    : route.fulfill({ json: { mode: "balanced", editable: true } }));
  await page.reload();
  await page.getByRole("button", { name: /^Router:/ }).click();
  await page.getByRole("menuitemradio", { name: "Quality", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Routing update failed");
  await expect(page.getByRole("button", { name: /^Router:/ })).toHaveAccessibleName("Router: balanced");
});