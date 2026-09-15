import { expect, test } from "@playwright/test";

test("security view preserves credential selection and correlated errors", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/security/access-requests", (route) => route.fulfill({
    status: 500,
    json: { detail: { message: "Access service unavailable.", incident_id: "SEC-TEST" } },
  }));
  await page.goto("/");
  await page.getByRole("button", { name: "Security & access", exact: true }).click();
  await page.getByRole("button", { name: "Mobile", exact: true }).click();
  const request = page.waitForRequest((value) => value.url().endsWith("/security/access-requests"));
  await page.getByRole("button", { name: "Request access", exact: true }).click();
  expect((await request).postDataJSON()).toMatchObject({
    method: "mobile", credential_id: "MOB-2048",
  });
  await expect(page.getByRole("alert")).toContainText("SEC-TEST");
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(page.getByRole("button", { name: "Agents", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "AI Gateway", exact: true })).toBeVisible();
});
