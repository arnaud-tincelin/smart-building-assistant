import { expect, test } from "@playwright/test";

const ROUTER_STATE = { mode: "balanced", editable: false, explicitly_set: false };

test.describe("Assistant chat transcript", () => {
  test("AC1: chronological multi-turn history keeps earlier turns intact", async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({ json: ROUTER_STATE }));
    let turn = 0;
    await page.route("**/ask", (route) => {
      turn += 1;
      return route.fulfill({
        json: { answer: `Answer number ${turn}.`, citations: [], execution: null },
      });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });

    for (let i = 1; i <= 3; i += 1) {
      await question.fill(`Question number ${i}?`);
      await ask.click();
      await expect(page.getByText(`Answer number ${i}.`, { exact: true })).toBeVisible();
    }

    const messages = page.locator(".chat-message");
    await expect(messages).toHaveCount(6);
    for (let i = 0; i < 3; i += 1) {
      await expect(messages.nth(i * 2)).toHaveClass(/chat-message--user/);
      await expect(messages.nth(i * 2)).toContainText(`Question number ${i + 1}?`);
      await expect(messages.nth(i * 2 + 1)).toHaveClass(/chat-message--agent/);
      await expect(messages.nth(i * 2 + 1)).toContainText(`Answer number ${i + 1}.`);
    }
    // Earlier turns remain available without being overwritten.
    await expect(page.getByText("Answer number 1.", { exact: true })).toBeVisible();
    await expect(page.getByText("Answer number 2.", { exact: true })).toBeVisible();
  });

  test("AC2: the transcript scrolls vertically without overflowing the document horizontally", async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({ json: ROUTER_STATE }));
    let turn = 0;
    await page.route("**/ask", (route) => {
      turn += 1;
      return route.fulfill({
        json: {
          answer: `Long operational update number ${turn} covering floor sensors, alerts, and maintenance notes so this reply takes up real vertical space in the transcript.`,
          citations: [],
          execution: null,
        },
      });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });
    for (let i = 1; i <= 10; i += 1) {
      await question.fill(`Question ${i}?`);
      await ask.click();
      await expect(page.getByText(`Long operational update number ${i}`)).toBeVisible();
    }

    const transcript = page.locator(".chat-transcript");
    const overflow = await transcript.evaluate((el) => el.scrollHeight > el.clientHeight);
    expect(overflow).toBe(true);

    await transcript.evaluate((el) => {
      el.scrollTop = 0;
    });
    await expect(page.getByText("Question 1?", { exact: true })).toBeInViewport();

    await transcript.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(page.getByText("Question 10?", { exact: true })).toBeInViewport();

    // The composer stays reachable and usable after scrolling the history.
    await question.fill("One more question?");
    await expect(question).toHaveValue("One more question?");
    await expect(ask).toBeEnabled();

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("AC3/AC4: each reply keeps its own model attribution, including when it is unavailable", async ({ page }) => {
    let mode = "balanced";
    await page.route("**/model-router/mode", (route) => {
      if (route.request().method() === "PUT") mode = route.request().postDataJSON().mode;
      return route.fulfill({ json: { mode, editable: true } });
    });
    const executions = [
      { selected_model: "gpt-5-mini-2025-08-07", routing_mode: "cost", latency_ms: 1200, response_id: "resp_1" },
      null,
      { selected_model: "gpt-5-2025-08-07", routing_mode: "quality", latency_ms: 2400, response_id: "resp_3" },
    ];
    let turn = 0;
    await page.route("**/ask", (route) => {
      const execution = executions[turn];
      turn += 1;
      return route.fulfill({ json: { answer: `Reply ${turn}.`, citations: [], execution } });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });

    await question.fill("First question?");
    await ask.click();
    await expect(page.getByRole("heading", { name: "gpt-5-mini-2025-08-07" })).toBeVisible();

    // Changing the router setting must not relabel the completed reply above.
    await page.getByRole("button", { name: /^Router:/ }).click();
    await page.getByRole("menuitemradio", { name: "Quality", exact: true }).click();
    await expect(page.getByRole("heading", { name: "gpt-5-mini-2025-08-07" })).toBeVisible();

    await question.fill("Second question?");
    await ask.click();
    await expect(page.getByText("Model attribution is not disclosed for this reply.")).toBeVisible();
    // The unavailable reply never substitutes the requested router mode as the model.
    await expect(page.getByText("quality", { exact: true })).toHaveCount(0);

    await question.fill("Third question?");
    await ask.click();
    await expect(page.getByRole("heading", { name: "gpt-5-2025-08-07" })).toBeVisible();

    // All three attributions coexist and are unchanged by later turns.
    await expect(page.getByRole("heading", { name: "gpt-5-mini-2025-08-07" })).toBeVisible();
    await expect(page.getByText("Model attribution is not disclosed for this reply.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "gpt-5-2025-08-07" })).toBeVisible();
  });

  test("AC5: markdown renders for every reply and later replies keep earlier formatting", async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({ json: ROUTER_STATE }));
    const answers = [
      "## Floor 3 status\n\n**Energy use** is elevated. See [the dashboard](https://example.com/dashboard).",
      "- Sensor A online\n- Sensor B offline\n\n```js\nconsole.log('reading sensor data');\n```",
      "| Zone | Alert |\n| --- | --- |\n| A | None |\n| B | Ventilation |",
    ];
    let turn = 0;
    await page.route("**/ask", (route) => {
      const answer = answers[turn];
      turn += 1;
      return route.fulfill({ json: { answer, citations: [], execution: null } });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });

    await question.fill("What is happening on floor 3?");
    await ask.click();
    await expect(page.getByRole("heading", { name: "Floor 3 status", level: 2 })).toBeVisible();
    await expect(page.locator(".markdown-body strong", { hasText: "Energy use" })).toBeVisible();
    const link = page.getByRole("link", { name: "the dashboard" });
    await expect(link).toHaveAttribute("href", "https://example.com/dashboard");

    await question.fill("What do the sensors show?");
    await ask.click();
    await expect(page.getByText("Sensor A online", { exact: true })).toBeVisible();
    await expect(page.locator(".markdown-body pre code")).toContainText("console.log");
    // Earlier reply's markdown is still rendered after a new turn.
    await expect(page.getByRole("heading", { name: "Floor 3 status", level: 2 })).toBeVisible();

    await question.fill("Which zones have alerts?");
    await ask.click();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("cell", { name: "Ventilation" })).toBeVisible();

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("AC6: sources and execution details stay bound to the reply that produced them", async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({ json: ROUTER_STATE }));
    const fixtures = [
      {
        answer: "Paris HQ has an open work order.",
        citations: [{ title: "Work order log", url: "https://example.com/wo-1", snippet: "Ticket WO-101" }],
        execution: { selected_model: "gpt-5-mini-2025-08-07", routing_mode: "cost", response_id: "resp_a" },
      },
      {
        answer: "Lyon site energy usage is nominal.",
        citations: [{ title: "Energy report", url: "https://example.com/energy-2", snippet: "Report EN-202" }],
        execution: { selected_model: "gpt-5-2025-08-07", routing_mode: "quality", response_id: "resp_b" },
      },
    ];
    let turn = 0;
    await page.route("**/ask", (route) => {
      const body = fixtures[turn];
      turn += 1;
      return route.fulfill({ json: body });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });

    await question.fill("Paris question?");
    await ask.click();
    await expect(page.getByRole("link", { name: "Work order log" })).toBeVisible();

    await question.fill("Lyon question?");
    await ask.click();
    await expect(page.getByRole("link", { name: "Energy report" })).toBeVisible();

    const replies = page.locator(".chat-message--agent");
    await expect(replies).toHaveCount(2);
    const first = replies.nth(0);
    const second = replies.nth(1);

    // Execution measurements remain collapsed by default for both replies.
    await expect(first.getByText("Response ID", { exact: true })).toBeHidden();
    await expect(second.getByText("Response ID", { exact: true })).toBeHidden();

    await first.getByText("Show more details", { exact: true }).click();
    await expect(first.getByText("resp_a", { exact: true })).toBeVisible();
    // Opening the first reply's details does not affect the second reply.
    await expect(second.getByText("Response ID", { exact: true })).toBeHidden();
    await expect(second).toContainText("Lyon site energy usage is nominal.");
    await expect(first).toContainText("Work order log");
    await expect(second).toContainText("Energy report");
  });

  test("AC7: a pending and then failed request never erases or fakes history", async ({ page }) => {
    await page.route("**/model-router/mode", (route) => route.fulfill({ json: ROUTER_STATE }));
    let call = 0;
    await page.route("**/ask", async (route) => {
      call += 1;
      if (call === 1) {
        return route.fulfill({ json: { answer: "Completed answer.", citations: [], execution: null } });
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
      return route.fulfill({ status: 502, json: { detail: "Building operations unavailable: timeout." } });
    });
    await page.goto("/");

    const question = page.getByRole("textbox", { name: "Building question" });
    const ask = page.getByRole("button", { name: "Ask", exact: true });

    await question.fill("First question?");
    await ask.click();
    await expect(page.getByText("Completed answer.", { exact: true })).toBeVisible();

    await question.fill("Second question?");
    await ask.click();
    await expect(page.getByText("Asking the building agent…", { exact: true })).toBeVisible();
    // The already-completed exchange remains visible while the next one is pending.
    await expect(page.getByText("Completed answer.", { exact: true })).toBeVisible();

    await expect(page.getByRole("alert")).toHaveText("Building operations unavailable: timeout.");
    // The failure is not presented as a successful agent reply.
    await expect(page.getByText("Asking the building agent…", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Completed answer.", { exact: true })).toBeVisible();

    // The user can submit another request afterward.
    call = 0;
    await question.fill("Third question?");
    await ask.click();
    await expect(page.getByText("Completed answer.", { exact: true }).last()).toBeVisible();
  });
});
