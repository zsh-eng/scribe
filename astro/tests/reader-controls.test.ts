import { afterEach, expect, test } from "bun:test";
import { Window, HTMLElement } from "happy-dom";
import { runScript, source } from "./helpers/astro-script";

const windows: Window[] = [];
function dom(html: string, url = "https://example.test/") {
  const window = new Window({ url });
  windows.push(window);
  window.document.body.innerHTML = html;
  return window;
}
afterEach(() => { for (const window of windows.splice(0)) window.happyDOM.abort(); });

test("menu button exposes and updates its controlled menu state", () => {
  const markup = source("components/Navbar.astro").match(/<button[\s\S]*?<\/button>/)![0];
  const window = dom(`${markup}<div id="mobile-menu" class="hidden"></div>`);
  runScript(window, "components/Navbar.astro");
  const button = window.document.querySelector("button")!;
  expect(button.getAttribute("aria-controls")).toBe("mobile-menu");
  expect(button.getAttribute("aria-expanded")).toBe("false");
  button.click();
  expect(button.getAttribute("aria-expanded")).toBe("true");
  expect(window.document.getElementById("mobile-menu")!.classList.contains("hidden")).toBe(false);
  button.click();
  expect(button.getAttribute("aria-expanded")).toBe("false");
});

for (const route of ["members", "ministries"]) {
  test(`${route} period tabs support arrows, wrapping, Home and End`, () => {
    const window = dom(`<div data-parliament-switcher>${["overall", "15", "14"].map((id, i) => `
      <button data-parliament-target="${id}" class="${i === 0 ? "is-active" : ""}">${id}</button>
      <div data-parliament-panel="${id}"></div>`).join("")}</div>`);
    runScript(window, `pages/${route}/[slug].astro`);
    const buttons = [...window.document.querySelectorAll("button")];
    buttons[0].focus();
    const press = (key: string) => window.document.activeElement!.dispatchEvent(new window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    press("ArrowRight");
    expect(window.document.activeElement).toBe(buttons[1]);
    expect(buttons[1].getAttribute("aria-selected")).toBe("true");
    expect(window.document.querySelector('[data-parliament-panel="overall"]')!.hasAttribute("hidden")).toBe(true);
    press("End");
    expect(window.document.activeElement).toBe(buttons[2]);
    press("ArrowRight");
    expect(window.document.activeElement).toBe(buttons[0]);
    press("ArrowLeft");
    expect(window.document.activeElement).toBe(buttons[2]);
    press("Home");
    expect(window.document.activeElement).toBe(buttons[0]);
    expect(buttons.map(b => b.tabIndex)).toEqual([0, -1, -1]);
  });
}

test("MP search applies selected sort before and after broadening a query", async () => {
  const window = dom(`<input id="member-search-input"><button id="member-search-clear"></button><p id="member-search-status"></p>
    <select id="member-sort"><option value="name-asc">Name</option><option value="attendance-desc">Attendance</option></select>
    <div id="parliament-sections"></div><div id="search-results" class="hidden"><div id="search-results-grid">
    <div class="search-member-item" data-name="Alice" data-attendance="50">Alice Match</div>
    <div class="search-member-item" data-name="Bob" data-attendance="90">Bob Match</div>
    <div class="search-member-item" data-name="Carol" data-attendance="70">Carol Match</div></div></div>`);
  runScript(window, "pages/members/index.astro");
  const select = window.document.querySelector("select")!;
  select.value = "attendance-desc";
  select.dispatchEvent(new window.Event("change"));
  const input = window.document.querySelector("input")!;
  const search = async (query: string) => {
    input.value = query;
    input.dispatchEvent(new window.Event("input"));
    await window.happyDOM.waitUntilComplete();
    return [...window.document.querySelectorAll<HTMLElement>(".search-member-item")].filter(item => item.style.display !== "none").map(item => item.dataset.name);
  };
  expect(await search("match")).toEqual(["Bob", "Carol", "Alice"]);
  expect(await search("Alice")).toEqual(["Alice"]);
  expect(await search("match")).toEqual(["Bob", "Carol", "Alice"]);
});

function budgetWindow(query: string) {
  const ids = ["container", "tooltip", "total", "estimate-type", "focus-controls", "focus-back", "focus-label", "hatch-legend"];
  const window = dom(`<div id="budget-treemap-data"></div>${ids.map(id => `<div id="budget-treemap-${id}"></div>`).join("")}`, `https://example.test/budgets?${query}`);
  const sectors = ["Social Development", "Economic Development"].map(name => ({ name, value: 10, x0: 0, y0: 0, x1: 50, y1: 50, ministries: [] }));
  window.document.querySelector<HTMLElement>("#budget-treemap-data")!.dataset.json = JSON.stringify({ defaultYear: 2026, width: 100, height: 100, data: { 2026: { total: 20, estimateType: "Estimated", sectors }, 2025: { total: 20, estimateType: "Revised", sectors } } });
  runScript(window, "components/budgets/BudgetTreemapGraph.astro");
  return window;
}

test("budget restores a valid sector and year without removing them from URL", () => {
  const window = budgetWindow("year=2025&sector=Social+Development");
  expect(window.document.getElementById("budget-treemap-focus-label")!.textContent).toBe("Social Development");
  expect(window.document.querySelectorAll(".tm-sector")).toHaveLength(1);
  expect(new URL(window.location.href).searchParams.get("sector")).toBe("Social Development");
  expect(window.document.getElementById("budget-treemap-estimate-type")!.textContent).toBe("Revised 2025");
  window.document.querySelector<HTMLElement>("#budget-treemap-focus-back")!.click();
  expect(window.document.querySelectorAll(".tm-sector")).toHaveLength(2);
  expect(new URL(window.location.href).searchParams.has("sector")).toBe(false);
});

test("budget rejects unknown sectors and defaults unknown years", () => {
  const window = budgetWindow("year=9999&sector=Missing");
  expect(window.document.querySelectorAll(".tm-sector")).toHaveLength(2);
  expect(new URL(window.location.href).searchParams.get("year")).toBe("2026");
  expect(new URL(window.location.href).searchParams.has("sector")).toBe(false);
});
