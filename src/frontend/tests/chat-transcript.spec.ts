import { expect, test } from "@playwright/test";

test("transcript retains multi-turn history in chronological order with per-response model labels", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  let call = 0;
  await page.route("**/ask", (route) => {
    call += 1;
    if (call === 1) {
      return route.fulfill({ json: {
        answer: "Floor 3 has an active ventilation alert.",
        citations: [],
        execution: {
          mode: "agents", requested_model: "model-router",
          reported_model: "gpt-4o-mini-2024-07-18", selected_model: "gpt-4o-mini-2024-07-18",
          routing_mode: "balanced", latency_ms: 800, response_id: "resp-1",
          usage: null, tools_used: [], routing_explanation: "First response.",
        },
      } });
    }
    return route.fulfill({ json: {
      answer: "Building HQ energy usage is stable.",
      citations: [],
      execution: {
        mode: "agents", requested_model: "model-router",
        reported_model: "gpt-4.1-2025-04-14", selected_model: "gpt-4.1-2025-04-14",
        routing_mode: "balanced", latency_ms: 650, response_id: "resp-2",
        usage: null, tools_used: [], routing_explanation: "Second response.",
      },
    } });
  });
  await page.goto("/");

  const question = page.getByRole("textbox", { name: "Building question" });
  const history = page.getByRole("log", { name: "Conversation history" });

  await question.fill("Why is Floor 3 alerting?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Floor 3 has an active ventilation alert.")).toBeVisible();

  await question.fill("What is the energy usage at HQ?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Building HQ energy usage is stable.")).toBeVisible();

  // AC1: both prompts and both responses remain, in chronological order.
  const exchanges = history.locator(".chat-exchange");
  await expect(exchanges).toHaveCount(2);
  await expect(page.getByText("Why is Floor 3 alerting?")).toBeVisible();
  await expect(page.getByText("What is the energy usage at HQ?")).toBeVisible();

  const bodyText = await history.innerText();
  expect(bodyText.indexOf("Why is Floor 3 alerting?"))
    .toBeLessThan(bodyText.indexOf("What is the energy usage at HQ?"));
  expect(bodyText.indexOf("Floor 3 has an active ventilation alert."))
    .toBeLessThan(bodyText.indexOf("Building HQ energy usage is stable."));

  // AC2: each response shows the model reported for that specific response.
  await expect(page.getByRole("heading", { name: "gpt-4o-mini-2024-07-18" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "gpt-4.1-2025-04-14" })).toBeVisible();
});

test("Markdown constructs render as semantic HTML and unsafe HTML never executes", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: [
      "## Ventilation summary",
      "",
      "This is **important** and *notable*.",
      "",
      "- Floor 3 alert active",
      "- Floor 1 nominal",
      "",
      "See [the ops dashboard](https://example.com/ops) for details.",
      "",
      "```js",
      "console.log('trace');",
      "```",
      "",
      "| Floor | Status |",
      "|---|---|",
      "| 3 | Alert |",
      "| 1 | Nominal |",
      "",
      "<img src=x onerror=\"window.__xss = true\">",
      "<script>window.__xss = true;</script>",
    ].join("\n"),
    citations: [],
    execution: null,
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Ventilation summary", level: 2 })).toBeVisible();
  await expect(page.locator(".chat-message--assistant strong", { hasText: "important" })).toBeVisible();
  await expect(page.locator(".chat-message--assistant em", { hasText: "notable" })).toBeVisible();
  await expect(page.locator(".chat-message--assistant li", { hasText: "Floor 3 alert active" })).toBeVisible();
  await expect(page.getByRole("link", { name: "the ops dashboard" })).toHaveAttribute("href", "https://example.com/ops");
  await expect(page.locator(".chat-message--assistant pre code")).toContainText("console.log('trace');");
  const table = page.getByRole("region", { name: "Answer table" }).getByRole("table");
  await expect(table.getByRole("row")).toHaveCount(3);

  // AC4: raw markdown source text is not shown, and no HTML/script executes.
  await expect(page.getByText("## Ventilation summary", { exact: true })).toHaveCount(0);
  await expect(page.locator("script", { hasText: "__xss" })).toHaveCount(0);
  const executed = await page.evaluate(() => (window as unknown as { __xss?: boolean }).__xss);
  expect(executed).toBeUndefined();
});

test("conversation history scrolls vertically without causing horizontal page overflow", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: "Answer text ".repeat(40),
    citations: [],
    execution: null,
  } }));
  await page.goto("/");

  const question = page.getByRole("textbox", { name: "Building question" });
  const history = page.getByRole("log", { name: "Conversation history" });

  for (let i = 0; i < 6; i += 1) {
    await question.fill(`Question number ${i}`);
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await expect(page.getByText(`Question number ${i}`)).toBeVisible();
  }

  const overflow = await history.evaluate((node) => node.scrollHeight > node.clientHeight);
  expect(overflow).toBe(true);

  await history.evaluate((node) => { node.scrollTop = 0; });
  await expect(page.getByText("Question number 0")).toBeVisible();

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("a later failed request does not remove the earlier successful exchange", async ({ page }) => {
  await page.route("**/model-router/mode", (route) =>
    route.fulfill({ json: { mode: "balanced", editable: false } }),
  );
  let call = 0;
  await page.route("**/ask", (route) => {
    call += 1;
    if (call === 1) {
      return route.fulfill({ json: { answer: "First answer.", citations: [], execution: null } });
    }
    return route.fulfill({ status: 500, json: { detail: "Second request failed." } });
  });
  await page.goto("/");

  const question = page.getByRole("textbox", { name: "Building question" });
  await question.fill("First question");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("First answer.", { exact: true })).toBeVisible();

  await question.fill("Second question");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Second request failed.");

  // AC6: the earlier exchange remains visible alongside the later error.
  await expect(page.getByText("First answer.", { exact: true })).toBeVisible();
  await expect(page.getByText("First question", { exact: true })).toBeVisible();
  await expect(page.getByText("Second question", { exact: true })).toBeVisible();

  // Retry after failure keeps existing behavior working.
  call = 0;
  await page.unroute("**/ask");
  await page.route("**/ask", (route) =>
    route.fulfill({ json: { answer: "Recovered answer.", citations: [], execution: null } }));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Recovered answer.", { exact: true })).toBeVisible();
  await expect(page.getByText("First answer.", { exact: true })).toBeVisible();
});
