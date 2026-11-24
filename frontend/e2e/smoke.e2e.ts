import { expect, test as base } from "@playwright/test";
import type { Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/* --------------------------------------------------------------------------------------------
 * Real-browser smoke test of the static demonstration build. Expected values come from the
 * generated fixtures in public/demo-data (the same files the page loads), never from literals.
 * ------------------------------------------------------------------------------------------ */

const DATA = path.resolve(HERE, "../public/demo-data");
const SHOTS = path.resolve(HERE, "../../docs/screenshots");
const capture = Boolean(process.env.CAPTURE_SCREENSHOTS);

interface ScenarioInfo { id: string; name: string }
interface Demo {
  scenario: ScenarioInfo;
  analysis: {
    verdict_reason: string;
    events: { message: string; service: string; severity: string }[];
    events_total: number;
    hypotheses: { title: string; evidence: { message: string }[] }[];
  };
}
const read = <T,>(file: string): T => JSON.parse(fs.readFileSync(path.join(DATA, file), "utf8")) as T;
const scenarios = read<ScenarioInfo[]>("scenarios.json");
const demo = (id: string) => read<Demo>(`${id}.json`);

/** Every test records requests and console output and fails on backend calls or console errors. */
const test = base.extend<{ page: Page }>({
  page: async ({ page, baseURL }, use) => {
    const requests: string[] = [];
    const problems: string[] = [];
    page.on("request", (r) => requests.push(r.url()));
    page.on("console", (m) => m.type() === "error" && problems.push(`console.error: ${m.text()}`));
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("requestfailed", (r) => problems.push(`requestfailed: ${r.url()} ${r.failure()?.errorText ?? ""}`));
    await use(page);
    const origin = new URL(baseURL!).origin;
    expect(requests.filter((u) => new URL(u).pathname.includes("/api/")), "no backend API requests").toEqual([]);
    expect(requests.filter((u) => !u.startsWith(origin) && !u.startsWith("data:") && !u.startsWith("blob:")), "no third-party requests").toEqual([]);
    expect(problems, "no browser console errors").toEqual([]);
  },
});

const isMobile = () => test.info().project.name === "mobile";
const shot = async (page: Page, name: string, fullPage = true) => {
  if (!capture) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `${test.info().project.name}-${name}.png`), fullPage });
};

async function open(page: Page, id: string) {
  const info = scenarios.find((s) => s.id === id)!;
  await page.goto("./");
  await page.getByRole("button", { name: new RegExp(info.name) }).click();
  await expect(page.getByRole("heading", { name: "Ranked root-cause hypotheses" })).toBeVisible();
  return demo(id);
}

const matching = async (page: Page) => {
  const text = await page.getByRole("status").filter({ hasText: "matching" }).innerText();
  return Number(/([\d,]+) matching/.exec(text)![1].replace(/,/g, ""));
};

test("loads in static demonstration mode and says so", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "IncidentLens", level: 1 })).toBeVisible();
  await expect(page.getByTestId("static-demo-banner")).toContainText("Static demonstration");
  await expect(page.getByText(/Static demo · v\d+\.\d+\.\d+/)).toBeVisible();
  await expect(page.getByRole("tab", { name: "Upload" })).toBeDisabled();
  await expect(page.getByRole("tab", { name: "Manual entry" })).toBeDisabled();
  await expect(page.getByTestId("static-demo-help")).toContainText("docker compose up");
  for (const s of scenarios) await expect(page.getByRole("button", { name: new RegExp(s.name) })).toBeVisible();
  expect(scenarios).toHaveLength(7);
  await shot(page, "landing", false);
});

test("every scenario can be selected and renders its analysis", async ({ page }) => {
  await page.goto("./");
  for (const s of scenarios) {
    await page.getByRole("button", { name: new RegExp(s.name) }).click();
    await expect(page.getByRole("button", { name: new RegExp(s.name) })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(demo(s.id).analysis.verdict_reason, { exact: false }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Event timeline", exact: false })).toBeVisible();
  }
});

test("charts actually render with data", async ({ page }) => {
  await open(page, "cascading-microservice-failure");
  const surfaces = page.locator("svg.recharts-surface");
  await expect.poll(() => surfaces.count()).toBeGreaterThanOrEqual(3);
  const timeline = page.locator('[aria-label^="Stacked bar timeline"] svg.recharts-surface');
  await expect(timeline).toBeVisible();
  const box = await timeline.boundingBox();
  expect(box!.width).toBeGreaterThan(150);
  expect(box!.height).toBeGreaterThan(80);
  await expect.poll(() => page.locator(".recharts-bar-rectangle").count()).toBeGreaterThan(5);
  await expect.poll(() => page.locator(".recharts-pie-sector").count()).toBeGreaterThan(0);
  await expect(page.locator(".recharts-reference-area").first()).toBeVisible(); // an error spike is highlighted
  await shot(page, "dashboard-cascade");
});

test("hypotheses and their evidence are shown", async ({ page }) => {
  const d = await open(page, "db-pool-exhaustion");
  const top = d.analysis.hypotheses[0];
  const card = page.getByRole("button", { name: new RegExp(top.title) });
  await expect(card).toBeVisible();
  if ((await card.getAttribute("aria-expanded")) !== "true") await card.click();
  await expect(page.getByRole("heading", { name: "Supporting evidence" }).first()).toBeVisible();
  await expect(page.getByText(top.evidence[0].message.slice(0, 40), { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "How the score was computed" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommended diagnostic actions" }).first()).toBeVisible();
  await expect(page.getByRole("meter", { name: "Heuristic evidence score" }).first()).toBeVisible();
  await expect(page.getByText(/heuristic/i).first()).toBeVisible();
  await shot(page, "hypotheses-db-pool");
});

test("log filters and the timeline filter work", async ({ page }) => {
  const d = await open(page, "db-pool-exhaustion");
  const viewer = page.getByRole("region", { name: "Log viewer" });
  await viewer.scrollIntoViewIfNeeded();
  const all = await matching(page);
  expect(all).toBe(d.analysis.events.length);

  // text search
  const word = d.analysis.hypotheses[0].evidence[0].message.split(/\s+/).find((w) => /^[a-z]{5,}$/i.test(w))!;
  await viewer.getByLabel("Search logs").fill(word);
  await expect.poll(() => matching(page)).toBeLessThanOrEqual(all);
  expect(await matching(page)).toBeGreaterThan(0);
  await viewer.getByLabel("Search logs").fill("zz-no-such-text-zz");
  await expect.poll(() => matching(page)).toBe(0);
  await viewer.getByRole("button", { name: "Reset" }).click();
  await expect.poll(() => matching(page)).toBe(all);

  // severity toggle: ERROR off must remove exactly the ERROR events
  const errors = d.analysis.events.filter((e) => e.severity === "ERROR").length;
  expect(errors).toBeGreaterThan(0);
  await viewer.getByRole("button", { name: "ERROR", exact: true }).click();
  await expect.poll(() => matching(page)).toBe(all - errors);
  await viewer.getByRole("button", { name: "Reset" }).click();

  // service filter
  const service = d.analysis.events[0].service;
  await viewer.getByLabel("Filter by service").selectOption(service);
  await expect.poll(() => matching(page)).toBe(d.analysis.events.filter((e) => e.service === service).length);
  await viewer.getByRole("button", { name: "Reset" }).click();

  // timeline click narrows the viewer, "Clear time filter" restores it
  const bars = page.locator('[aria-label^="Stacked bar timeline"] .recharts-bar-rectangle path');
  await expect.poll(() => bars.count()).toBeGreaterThan(0);
  let clicked = false;
  for (let i = 0; i < (await bars.count()) && !clicked; i++) {
    const box = await bars.nth(i).boundingBox();
    if (box && box.height > 3 && box.width > 1) {
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      clicked = true;
    }
  }
  expect(clicked, "found a clickable timeline bar").toBe(true);
  await expect(page.getByRole("button", { name: "Clear time filter" })).toBeVisible();
  const narrowed = await matching(page);
  expect(narrowed).toBeGreaterThan(0);
  expect(narrowed).toBeLessThan(all);
  await page.getByRole("button", { name: "Clear time filter" }).click();
  await expect.poll(() => matching(page)).toBe(all);
});

test("reports download and match the generated fixtures", async ({ page }) => {
  await open(page, "db-pool-exhaustion");
  for (const [label, ext, file] of [
    ["Export Markdown", "md", "db-pool-exhaustion.report.md"],
    ["Export JSON", "json", "db-pool-exhaustion.report.json"],
  ] as const) {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: label }).click()]);
    expect(download.suggestedFilename()).toBe(`incident-report-db-pool-exhaustion.${ext}`);
    const p = await download.path();
    const body = fs.readFileSync(p!, "utf8");
    expect(body).toBe(fs.readFileSync(path.join(DATA, file), "utf8"));
    if (ext === "md") expect(body).toContain("# IncidentLens incident report");
    else expect(JSON.parse(body).verdict).toBeTruthy();
  }
});

test("layout is usable at this viewport", async ({ page }) => {
  await open(page, "cascading-microservice-failure");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "no horizontal page overflow").toBeLessThanOrEqual(1);
  const vp = page.viewportSize()!;
  expect(vp.width).toBe(isMobile() ? 412 : 1440);
  for (const name of ["Ranked root-cause hypotheses", "Recommended investigation steps"]) {
    const h = page.getByRole("heading", { name });
    await h.scrollIntoViewIfNeeded();
    const b = await h.boundingBox();
    expect(b!.x).toBeGreaterThanOrEqual(0);
    expect(b!.x + b!.width).toBeLessThanOrEqual(vp.width + 1);
  }
  await page.getByRole("region", { name: "Log viewer" }).scrollIntoViewIfNeeded();
  await expect(page.getByLabel("Search logs")).toBeVisible();
  // the primary controls are reachable by tap/click at this size
  await page.getByRole("button", { name: "Export Markdown" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Export Markdown" })).toBeEnabled();
  await shot(page, "layout");
});
