import { afterEach, describe, expect, test } from "bun:test";
import { Window, HTMLButtonElement } from "happy-dom";
import { deferred, runScript, source } from "./helpers/astro-script";

type Results = { results: { data: () => Promise<{ meta: { id: string } }> }[] };
const results = (...ids: string[]): Results => ({ results: ids.map(id => ({ data: async () => ({ meta: { id } }) })) });
const windows: Window[] = [];
afterEach(() => { for (const window of windows.splice(0)) window.happyDOM.abort(); });
const settle = () => new Promise(resolve => setTimeout(resolve, 120));

for (const [route, kind, filter] of [["members", "member", "speaker"], ["ministries", "ministry", "ministry"]]) {
  describe(`${kind} profile search`, () => {
    function setup(search: (query: string, options?: unknown) => Promise<Results>, unavailable = false) {
      const window = new Window({ url: `https://example.test/${route}/one` });
      windows.push(window);
      // Read shipped retry markup so a missing action fails the test.
      const retry = source(`pages/${route}/[slug].astro`).match(new RegExp(`<button\\s[^>]*id="${kind}-search-retry"[\\s\\S]*?<\\/button>`))?.[0] || "";
      window.document.body.innerHTML = `<div data-${kind}-name="Test Person"><input id="${kind}-search-input"><button id="${kind}-search-clear"></button><p id="${kind}-search-status" class="hidden"></p>${retry}</div><section><div id="motions-list"><div class="motion-item" data-search-id="one">Housing one</div><div class="motion-item" data-search-id="two">Education two</div></div></section>`;
      (window as unknown as { __loadPagefind: () => Promise<unknown> }).__loadPagefind = async () => {
        if (unavailable) throw new Error("Index unavailable");
        return { search };
      };
      runScript(window, `pages/${route}/[slug].astro`);
      const input = window.document.querySelector("input")!;
      const status = window.document.getElementById(`${kind}-search-status`)!;
      const inputText = (query: string) => { input.value = query; input.dispatchEvent(new window.Event("input")); };
      const visible = () => [...window.document.querySelectorAll(".motion-item")].filter(item => !item.hasAttribute("data-search-hidden")).map(item => item.getAttribute("data-search-id"));
      return { window, input, status, inputText, visible, retry: () => window.document.querySelector<HTMLButtonElement>(`#${kind}-search-retry`)! };
    }

    for (const failure of ["query", "fragment"]) {
      test(`${failure} failure shows feedback, keeps last results, and retries current query`, async () => {
        let fail = false;
        const calls: unknown[][] = [];
        const view = setup(async (query, options) => {
          calls.push([query, options]);
          if (fail && failure === "query") throw new Error("Query failed");
          if (fail) return { results: [{ data: async () => { throw new Error("Fragment failed"); } }] };
          return query === "housing" ? results("one") : results("two");
        });
        view.inputText("housing");
        await settle();
        expect(view.visible()).toEqual(["one"]);
        fail = true;
        view.inputText("education");
        await settle();
        expect(view.status.textContent).toContain("Search failed");
        expect(view.status.textContent).toContain("Previous results");
        expect(view.retry().classList.contains("hidden")).toBe(false);
        expect(view.visible()).toEqual(["one"]);
        fail = false;
        view.retry().click();
        await settle();
        expect(view.status.textContent).toBe("Found 1 result");
        expect(view.retry().classList.contains("hidden")).toBe(true);
        expect(view.visible()).toEqual(["two"]);
        expect(calls.at(-1)).toEqual(["education", { filters: { [filter]: "Test Person" } }]);
      });
    }

    test("new input invalidates old results before the debounce expires", async () => {
      const old = deferred<Results>();
      const view = setup(async query => query === "old" ? old.promise : results("two"));
      view.inputText("old");
      await settle();
      view.inputText("new");
      old.resolve(results("one"));
      await new Promise(resolve => setTimeout(resolve, 0));
      expect(view.visible()).toEqual(["one", "two"]);
      await settle();
      expect(view.visible()).toEqual(["two"]);
    });

    test("a stale failure cannot replace the latest success", async () => {
      const old = deferred<Results>();
      const view = setup(async query => query === "old" ? old.promise : results("two"));
      view.inputText("old");
      await settle();
      view.inputText("new");
      await settle();
      old.reject(new Error("Stale failure"));
      await new Promise(resolve => setTimeout(resolve, 0));
      expect(view.status.textContent).toBe("Found 1 result");
      expect(view.visible()).toEqual(["two"]);
      expect(view.retry().classList.contains("hidden")).toBe(true);
    });

    test("clear cancels pending input and ignores a pending fragment", async () => {
      const fragment = deferred<{ meta: { id: string } }>();
      const view = setup(async () => ({ results: [{ data: () => fragment.promise }] }));
      view.inputText("housing");
      await settle();
      view.window.document.querySelector<HTMLButtonElement>(`#${kind}-search-clear`)!.click();
      fragment.resolve({ meta: { id: "one" } });
      await settle();
      expect(view.input.value).toBe("");
      expect(view.visible()).toEqual(["one", "two"]);
      expect(view.status.classList.contains("hidden")).toBe(true);
      expect(view.retry().classList.contains("hidden")).toBe(true);
    });

    test("unavailable index retains local text fallback", async () => {
      const view = setup(async () => results(), true);
      view.inputText("housing");
      await settle();
      expect(view.visible()).toEqual(["one"]);
      expect(view.status.textContent).toBe("Found 1 result");
    });
  });
}
