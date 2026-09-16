import { expect, test, type Page } from "@playwright/test";
import type { AskResponse, ModelExecution, RoutingMode } from "../src/api";

const history = (page: Page) => page.getByRole("log", { name: "Conversation history" });
const replies = (page: Page) => history(page).getByRole("article", { name: "Assistant reply", exact: true });
const users = (page: Page) => history(page).getByRole("article", { name: "User message", exact: true });
const prompt = (page: Page) => page.getByRole("textbox", { name: "Building question" });
const ask = (page: Page) => page.getByRole("button", { name: "Ask", exact: true });

function execution(index: number, routingMode: RoutingMode = "balanced"): ModelExecution {
  return {
    mode: "agents", requested_model: "model-router",
    reported_model: `reported-model-${index}`, selected_model: `reported-model-${index}`,
    routing_mode: routingMode, latency_ms: 1000 + index, response_id: `response-${index}`,
    usage: { input_tokens: index, output_tokens: 10, total_tokens: 10 + index,
      reasoning_tokens: 0, cached_tokens: 0, cache_write_tokens: 0 },
    tools_used: [`operations-tool-${index}`], routing_explanation: `Routing explanation ${index}.`,
  };
}

function response(index: number, routingMode?: RoutingMode): AskResponse {
  return {
    answer: `Answer ${index}.`,
    citations: [{
      title: `Source ${index}`, url: `https://example.com/source-${index}`, snippet: `Evidence ${index}.`,
    }],
    execution: execution(index, routingMode),
  };
}

async function setupRouter(page: Page) {
  let mode = "balanced";
  await page.route("**/model-router/mode", (route) => {
    if (route.request().method() === "PUT") mode = route.request().postDataJSON().mode;
    return route.fulfill({ json: { mode, editable: true } });
  });
}

async function submit(page: Page, question: string, replyCount: number) {
  await prompt(page).fill(question);
  const request = page.waitForRequest((value) => value.url().endsWith("/ask") && value.method() === "POST");
  await ask(page).click();
  expect((await request).postDataJSON()).toEqual({ question, mode: "agents" });
  await expect(replies(page)).toHaveCount(replyCount);
  await expect(prompt(page)).toHaveValue(question);
}

test.beforeEach(async ({ page }) => {
  await setupRouter(page);
});

test("three exchanges retain chronological messages, immutable model attribution, citations and collapsed details", async ({ page }) => {
  let count = 0;
  await page.route("**/ask", (route) => route.fulfill({
    json: response(++count, count === 1 ? "balanced" : "quality"),
  }));
  await page.goto("/");
  await submit(page, "Question 1?", 1);
  await page.getByRole("button", { name: "Router: balanced", exact: true }).click();
  await page.getByRole("menuitemradio", { name: "Quality", exact: true }).click();
  await expect(page.getByRole("button", { name: "Router: quality", exact: true })).toBeVisible();
  await submit(page, "Question 2?", 2);
  await submit(page, "Question 3?", 3);

  await expect(history(page)).toHaveAttribute("tabindex", "0");
  await expect(history(page).getByRole("article")).toHaveCount(6);
  expect(await history(page).getByRole("article").evaluateAll((articles) =>
    articles.map((article) => ({
      role: article.getAttribute("aria-label"),
      speaker: article.querySelector("h3")?.textContent,
      text: article.querySelector(".answer-body")?.textContent,
    })),
  )).toEqual(Array.from({ length: 3 }, (_, index) => [
    { role: "User message", speaker: "You", text: undefined },
    { role: "Assistant reply", speaker: "Assistant", text: `Answer ${index + 1}.` },
  ]).flat());

  for (let index = 1; index <= 3; index += 1) {
    const reply = replies(page).nth(index - 1);
    await expect(users(page).nth(index - 1)).toContainText(`Question ${index}?`);
    await expect(reply.getByRole("heading", { name: `reported-model-${index}`, exact: true })).toBeVisible();
    await expect(reply.locator(".routing-mode")).toHaveText(index === 1 ? "balanced" : "quality");
    await expect(reply.getByRole("link", { name: `Source ${index}`, exact: true }))
      .toHaveAttribute("href", `https://example.com/source-${index}`);
    await expect(reply.getByText(`Evidence ${index}.`, { exact: true })).toBeVisible();
    await expect(reply.locator(".routing-details")).not.toHaveAttribute("open", "");
    await expect(reply.getByText(`response-${index}`, { exact: true })).toBeHidden();
    await reply.getByText("Show more details", { exact: true }).click();
    await expect(reply.getByText(`response-${index}`, { exact: true })).toBeVisible();
    await expect(reply.getByText(`operations-tool-${index}`, { exact: true })).toBeVisible();
    await expect(reply.getByText(`Routing explanation ${index}.`, { exact: true })).toBeVisible();
    const tokens = reply.locator(".execution-metrics > div").filter({
      has: page.getByText("Response tokens", { exact: true }),
    });
    await expect(tokens.locator("dd")).toHaveText(String(10 + index));
    await expect(replies(page).filter({ has: page.locator("details[open]") })).toHaveCount(1);
    await reply.getByText("Show more details", { exact: true }).click();
  }
});

test("missing execution and undisclosed models never inherit attribution from another reply or router setting", async ({ page }) => {
  const answers: AskResponse[] = [
    response(1),
    { answer: "No metadata.", citations: [] },
    { answer: "No selected model.", citations: [], execution: {
      ...execution(3), selected_model: null, reported_model: "model-router", routing_mode: null,
    } },
  ];
  let count = 0;
  await page.route("**/ask", (route) => route.fulfill({ json: answers[count++] }));
  await page.goto("/");
  for (let index = 1; index <= answers.length; index += 1) {
    await submit(page, `Question ${index}?`, index);
  }
  await expect(replies(page).nth(0).getByRole("heading", { name: "reported-model-1", exact: true })).toBeVisible();
  const missing = replies(page).nth(1);
  await expect(missing.getByText("Model details were not reported for this answer.", { exact: true })).toBeVisible();
  await expect(missing.getByRole("region", { name: "Model execution" })).toHaveCount(0);
  const undisclosed = replies(page).nth(2);
  await expect(undisclosed.getByRole("heading", { name: "Model not disclosed", exact: true })).toBeVisible();
  await expect(undisclosed.locator(".routing-mode")).toHaveText("Router mode unavailable");
  await expect(undisclosed.getByRole("heading", { name: /model-router|reported-model/ })).toHaveCount(0);
  await expect(history(page).getByRole("heading", { name: "reported-model-1", exact: true })).toHaveCount(1);
});

test("retained replies render Markdown safely including headings, lists, code, links and wrapped tables", async ({ page }) => {
  let count = 0;
  await page.route("**/ask", (route) => route.fulfill({ json: {
    ...response(++count),
    answer: [
      `## Report ${count}`, "", "- **Critical** alert", "- *Routine* maintenance", "",
      "1. Inspect equipment", "2. Record findings", "",
      "[Safe reference](https://example.com/manual)", "",
      "`inline command`", "", "```text", "status --building paris-hq", "```", "",
      "| Building | Alert |", "|---|---|", "| Paris HQ | Ventilation |", "",
      '<script>window.__unsafeExecuted = true</script>', "",
      '<img src="invalid" onerror="window.__unsafeExecuted = true">', "",
      '<a href="javascript:window.__unsafeExecuted=true">Unsafe raw link</a>', "",
      "[Unsafe Markdown link](javascript:window.__unsafeExecuted=true)",
    ].join("\n"),
  } }));
  await page.addInitScript(() => { Object.assign(window, { __unsafeExecuted: false }); });
  await page.goto("/");
  await submit(page, "Show report one", 1);
  await submit(page, "Show report two", 2);
  for (let index = 0; index < 2; index += 1) {
    const body = replies(page).nth(index).locator(".answer-body");
    await expect(body.getByRole("heading", { name: `Report ${index + 1}`, exact: true })).toBeVisible();
    await expect(body.locator("ul > li")).toHaveCount(2);
    await expect(body.locator("ol > li")).toHaveCount(2);
    await expect(body.locator("strong")).toHaveText("Critical");
    await expect(body.locator("em")).toHaveText("Routine");
    await expect(body.locator("p > code")).toHaveText("inline command");
    await expect(body.locator("pre > code")).toHaveText("status --building paris-hq\n");
    await expect(body.getByRole("link", { name: "Safe reference", exact: true }))
      .toHaveAttribute("href", "https://example.com/manual");
    const table = body.getByRole("region", { name: "Answer table" });
    await expect(table).toHaveAttribute("tabindex", "0");
    await expect(table.getByRole("table").getByRole("columnheader")).toHaveCount(2);
    await expect(table.getByRole("cell", { name: "Paris HQ", exact: true })).toBeVisible();
    await expect(body.locator("script, img, [onerror], a[href^='javascript:']")).toHaveCount(0);
    const unsafeLink = body.getByText("Unsafe Markdown link", { exact: true });
    await expect(unsafeLink).not.toHaveAttribute("href", /javascript:/i);
    expect(await page.evaluate(() => Reflect.get(window, "__unsafeExecuted"))).toBe(false);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("wide Markdown and unsafe citations stay contained in their original replies", async ({ page }) => {
  const columns = Array.from({ length: 60 }, (_, index) => `Column ${index}`);
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: [
      "```text", "building-status ".repeat(100), "```", "",
      `| ${columns.join(" | ")} |`,
      `| ${columns.map(() => "---").join(" | ")} |`,
      `| ${columns.map(() => "Building measurement").join(" | ")} |`,
    ].join("\n"),
    citations: [{ title: "Unsafe source", url: "javascript:alert(1)", snippet: "Source evidence" }],
  } }));
  await page.goto("/");
  await submit(page, "Wide report", 1);
  await submit(page, "Another wide report", 2);
  for (let index = 0; index < 2; index += 1) {
    const reply = replies(page).nth(index);
    for (const region of [reply.locator("pre"), reply.getByRole("region", { name: "Answer table" })]) {
      await expect.poll(() => region.evaluate((element) =>
        element.scrollWidth - element.clientWidth,
      )).toBeGreaterThan(100);
      await region.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
      expect(await region.evaluate((element) => element.scrollLeft)).toBeGreaterThan(100);
    }
    await expect(reply.getByText("Unsafe source", { exact: true })).toBeVisible();
    await expect(reply.getByRole("link", { name: "Unsafe source" })).toHaveCount(0);
    await expect(reply.getByText("Source evidence", { exact: true })).toBeVisible();
  }
  expect(await history(page).evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("empty and short conversations do not require vertical scrolling", async ({ page }) => {
  await page.route("**/ask", (route) => route.fulfill({ json: { answer: "OK", citations: [] } }));
  await page.goto("/");
  const log = history(page);
  expect(await log.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
  await submit(page, "Hi", 1);
  expect(await log.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
});

test("delayed and failed requests retain previous exchanges and prompts and allow recovery without fake replies", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  let count = 0;
  await page.route("**/ask", async (route) => {
    count += 1;
    if (count === 2) {
      await held;
      await route.fulfill({ status: 503, json: { detail: "Operations temporarily unavailable." } });
    } else {
      await route.fulfill({ json: response(count) });
    }
  });
  await page.goto("/");
  await submit(page, "Successful question", 1);
  await prompt(page).fill("Delayed question");
  await ask(page).click();
  await expect(history(page).getByRole("status")).toHaveText("Asking…");
  await expect(users(page)).toHaveCount(2);
  await expect(users(page).last()).toContainText("Delayed question");
  await expect(replies(page)).toHaveCount(1);
  await expect(replies(page).first()).toContainText("Answer 1.");
  await expect(page.getByRole("button", { name: "Asking…", exact: true })).toBeDisabled();
  await expect(prompt(page)).toHaveValue("Delayed question");
  release();
  await expect(history(page).getByRole("alert")).toContainText("Operations temporarily unavailable.");
  await expect(history(page).getByRole("status")).toHaveCount(0);
  await expect(replies(page)).toHaveCount(1);
  await expect(history(page).getByRole("region", { name: "Model execution" })).toHaveCount(1);
  await expect(prompt(page)).toHaveValue("Delayed question");
  await expect(ask(page)).toBeEnabled();
  await submit(page, "Recovery question", 2);
  await expect(users(page)).toHaveCount(3);
  await expect(replies(page).first()).toContainText("Answer 1.");
  await expect(replies(page).last()).toContainText("Answer 3.");
  await expect(history(page).getByRole("alert")).toContainText("Operations temporarily unavailable.");
});

test("each mode retains its own history across app tabs and reload clears both session-only conversations", async ({ page }) => {
  await page.route("**/ask", (route) => route.fulfill({ json: {
    answer: `${route.request().postDataJSON().mode} session answer`, citations: [],
  } }));
  await page.goto("/");
  await submit(page, "Agents session question", 1);
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(replies(page)).toHaveCount(0);
  await prompt(page).fill("Gateway session question");
  await ask(page).click();
  await expect(replies(page)).toContainText("gateway session answer");
  await expect(users(page)).toContainText("Gateway session question");
  await expect(page.getByText("agents session answer", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Security & access", exact: true }).click();
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(replies(page)).toContainText("gateway session answer");
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(replies(page)).toContainText("agents session answer");
  await expect(users(page)).toContainText("Agents session question");
  await expect(page.getByText("gateway session answer", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Security & access", exact: true }).click();
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(replies(page)).toContainText("agents session answer");
  await page.reload();
  await expect(history(page).getByRole("article")).toHaveCount(0);
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(history(page).getByRole("article")).toHaveCount(0);
});

test("overflowing history supports keyboard navigation, conditional auto-scroll and a reachable composer", async ({ page }) => {
  let count = 0;
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/ask", async (route) => {
    count += 1;
    if (count === 4) await held;
    await route.fulfill({ json: {
      ...response(count),
      answer: `Answer ${count}.\n\n` + Array.from({ length: 14 }, (_, index) =>
        `Paragraph ${index + 1}: Inspect the ventilation equipment and record the building status.`,
      ).join("\n\n"),
    } });
  });
  await page.goto("/");
  for (let index = 1; index <= 3; index += 1) await submit(page, `Question ${index}?`, index);
  const log = history(page);
  await expect.poll(() => log.evaluate((element) => element.scrollHeight - element.clientHeight)).toBeGreaterThan(500);
  await expect.poll(() => log.evaluate((element) =>
    element.scrollHeight - element.clientHeight - element.scrollTop,
  )).toBeLessThan(5);

  await log.focus();
  await expect(log).toBeFocused();
  await page.keyboard.press("Control+Home");
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBeLessThan(5);
  await expect(users(page).first()).toBeInViewport();
  await page.keyboard.press("Control+End");
  await expect.poll(() => log.evaluate((element) =>
    element.scrollHeight - element.clientHeight - element.scrollTop,
  )).toBeLessThan(5);
  await expect(replies(page).last().getByRole("link", { name: "Source 3", exact: true })).toBeInViewport();

  await prompt(page).fill("Question 4?");
  await ask(page).click();
  await expect(log.getByRole("status")).toHaveText("Asking…");
  await log.focus();
  await page.keyboard.press("Control+Home");
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBeLessThan(5);
  const oldScroll = await log.evaluate((element) => element.scrollTop);
  release();
  await expect(replies(page)).toHaveCount(4);
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBeLessThan(oldScroll + 5);
  await expect(users(page).first()).toBeInViewport();
  await expect(prompt(page)).toBeInViewport();
  await expect(ask(page)).toBeInViewport();
  expect(await log.evaluate((element) => {
    const composer = document.querySelector(".ask-form")!;
    return composer.getBoundingClientRect().top >= element.getBoundingClientRect().bottom;
  })).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await prompt(page).fill("Question 5?");
  await ask(page).click();
  await expect(replies(page)).toHaveCount(5);
  await expect(users(page).first()).toBeInViewport();
  await expect(prompt(page)).toHaveValue("Question 5?");
  await expect(ask(page)).toBeEnabled();
});

test("reading position survives mode and tab switches and a reply received on another tab", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  let count = 0;
  await page.route("**/ask", async (route) => {
    const index = ++count;
    if (index === 3) await held;
    await route.fulfill({ json: {
      ...response(index),
      answer: `Answer ${index}.\n\n` + "Building status paragraph.\n\n".repeat(40),
    } });
  });
  await page.goto("/");
  await submit(page, "First question", 1);
  await submit(page, "Second question", 2);
  const log = history(page);
  const firstDetails = replies(page).first().locator(".routing-details");
  await firstDetails.getByText("Show more details", { exact: true }).click();
  await expect(firstDetails).toHaveAttribute("open", "");
  const savedScroll = await log.evaluate((element) => {
    element.scrollTop = element.scrollHeight - element.clientHeight - 100;
    return element.scrollTop;
  });
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBe(savedScroll);
  await page.getByRole("button", { name: "AI Gateway", exact: true }).click();
  await expect(log.getByRole("article")).toHaveCount(0);
  await page.getByRole("button", { name: "Agents", exact: true }).click();
  await expect(firstDetails).toHaveAttribute("open", "");
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBe(savedScroll);
  await page.getByRole("button", { name: "Security & access", exact: true }).click();
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(firstDetails).toHaveAttribute("open", "");
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBe(savedScroll);
  await prompt(page).fill("Third question");
  await ask(page).click();
  await expect(log.getByRole("status")).toHaveText("Asking…");
  await page.getByRole("button", { name: "Security & access", exact: true }).click();
  const completed = page.waitForResponse((value) => value.url().endsWith("/ask"));
  release();
  await completed;
  await page.getByRole("button", { name: "Assistant", exact: true }).click();
  await expect(replies(page)).toHaveCount(3);
  await expect(firstDetails).toHaveAttribute("open", "");
  await expect.poll(() => log.evaluate((element) => element.scrollTop)).toBe(savedScroll);
  await expect(replies(page).last()).toContainText("Answer 3.");
  await expect(ask(page)).toBeEnabled();
});
