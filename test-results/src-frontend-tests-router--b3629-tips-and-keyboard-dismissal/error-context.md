# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: src\frontend\tests\router-control.spec.ts >> composer router selects modes with tooltips and keyboard dismissal
- Location: src\frontend\tests\router-control.spec.ts:3:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | test("composer router selects modes with tooltips and keyboard dismissal", async ({ page }, testInfo) => {
  4  |   let mode = "balanced";
  5  |   const changes: string[] = [];
  6  |   await page.route("**/model-router/mode", async (route) => {
  7  |     if (route.request().method() === "PUT") {
  8  |       mode = route.request().postDataJSON().mode;
  9  |       changes.push(mode);
  10 |     }
  11 |     await route.fulfill({ json: { mode, editable: true, propagation_seconds: 300 } });
  12 |   });
> 13 |   await page.goto("/");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  14 |   const trigger = page.getByRole("button", { name: /^Router:/ });
  15 |   await expect(page.locator(".ask-form").getByRole("button", { name: /^Router:/ })).toBeVisible();
  16 |   await trigger.click();
  17 |   await expect(page.getByRole("menuitemradio", { name: "Balanced", exact: true })).toHaveAttribute("aria-checked", "true");
  18 |   for (const [label, description] of [
  19 |     ["Cost", "Cheapest model that clears a wider quality band"],
  20 |     ["Balanced", "Cheapest model within ~1-2% of top quality"],
  21 |     ["Quality", "Highest-rated model, cost ignored"],
  22 |   ]) {
  23 |     await page.getByRole("menuitemradio", { name: label, exact: true }).hover();
  24 |     await expect(page.getByRole("tooltip", { name: description, exact: true })).toBeVisible();
  25 |   }
  26 |   await page.screenshot({ path: testInfo.outputPath("router-open.png"), fullPage: true });
  27 |   await page.getByRole("menuitemradio", { name: "Cost", exact: true }).click();
  28 |   await expect(trigger).toHaveAccessibleName("Router: cost");
  29 |   await expect(page.getByRole("menu")).toHaveCount(0);
  30 |   expect(changes).toEqual(["cost"]);
  31 |   await expect(page.getByRole("status")).toContainText("5 min");
  32 |   await trigger.press("ArrowDown");
  33 |   await expect(page.getByRole("menuitemradio", { name: "Cost", exact: true })).toBeFocused();
  34 |   await page.keyboard.press("ArrowDown");
  35 |   await expect(page.getByRole("menuitemradio", { name: "Balanced", exact: true })).toBeFocused();
  36 |   await page.keyboard.press("Escape");
  37 |   await expect(trigger).toBeFocused();
  38 |   await expect(page.getByRole("menu")).toHaveCount(0);
  39 |   await trigger.click();
  40 |   await page.getByRole("textbox", { name: "Building question" }).click();
  41 |   await expect(page.getByRole("menu")).toHaveCount(0);
  42 |   expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  43 | });
  44 | 
  45 | test("router preserves read-only and failed update states", async ({ page }) => {
  46 |   await page.route("**/model-router/mode", (route) => route.fulfill({ json: { mode: "balanced", editable: false } }));
  47 |   await page.goto("/");
  48 |   await page.getByRole("button", { name: /^Router:/ }).click();
  49 |   await expect(page.getByRole("menuitemradio", { name: "Cost", exact: true })).toHaveAttribute("aria-disabled", "true");
  50 |   await expect(page.getByText("Routing is read-only in this environment.")).toBeVisible();
  51 |   await page.unroute("**/model-router/mode");
  52 |   await page.route("**/model-router/mode", (route) => route.request().method() === "PUT"
  53 |     ? route.fulfill({ status: 500, json: { detail: "Routing update failed" } })
  54 |     : route.fulfill({ json: { mode: "balanced", editable: true } }));
  55 |   await page.reload();
  56 |   await page.getByRole("button", { name: /^Router:/ }).click();
  57 |   await page.getByRole("menuitemradio", { name: "Quality", exact: true }).click();
  58 |   await expect(page.getByRole("status")).toContainText("Routing update failed");
  59 |   await expect(page.getByRole("button", { name: /^Router:/ })).toHaveAccessibleName("Router: balanced");
  60 | });
```