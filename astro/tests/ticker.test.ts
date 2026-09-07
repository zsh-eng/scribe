import { afterEach, expect, test } from "bun:test";
import { Window } from "happy-dom";
import { source } from "./helpers/astro-script";

const windows: Window[] = [];
afterEach(() => { for (const window of windows.splice(0)) window.happyDOM.abort(); });
function ticker(reducedMotion = false) {
  const window = new Window({ settings: { device: { prefersReducedMotion: reducedMotion ? "reduce" : "no-preference" } } });
  windows.push(window);
  const duplicate = source("pages/index.astro").split("<!-- Duplicate for seamless loop -->")[1].split("    </div>\n  </div>")[0];
  // Keep the shipped duplicate container and link attributes, with fixture text.
  const openingTag = duplicate.match(/<div[^>]+>/)![0];
  const links = [...duplicate.matchAll(/<a\b[\s\S]*?>/g)].map(match => `${match[0]}Duplicate</a>`).join("");
  window.document.body.innerHTML = `<style>${source("styles/global.css")}</style><div class="ticker-container"><div class="ticker"><div class="ticker-content"><a href="/bills/one">One</a><a href="/bills/two">Two</a></div>${openingTag}${links}</div></div></div>`;
  return window;
}

test("ticker duplicate links are excluded from keyboard navigation", () => {
  const window = ticker();
  const duplicate = window.document.querySelector('[aria-hidden="true"]')!;
  for (const link of duplicate.querySelectorAll("a")) expect(link.tabIndex).toBe(-1);
  expect(window.document.querySelector("a")!.tabIndex).toBe(0);
});

// Keyboard focus styles need a browser check: happy-dom does not support :focus-within.

test("reduced motion keeps original ticker links static and scrollable", () => {
  const window = ticker(true);
  expect(window.getComputedStyle(window.document.querySelector(".ticker")!).animation).toBe("none");
  expect(window.getComputedStyle(window.document.querySelector(".ticker-container")!).overflowX).toBe("auto");
  expect(window.getComputedStyle(window.document.querySelector('[aria-hidden="true"]')!).display).toBe("none");
});
