import { afterEach, expect, test } from "bun:test";
import { Window } from "happy-dom";
import { render } from "preact";
import { act } from "preact/test-utils";
import PaginatedList from "../src/components/islands/PaginatedList";
import {
  createListLoader,
  clampPage,
} from "../src/components/islands/list-loader";
import type { ListItem } from "../src/lib/types";
const items = Array.from(
  { length: 6 },
  (_, i) =>
    ({
      id: String(i),
      title: `housing ${i}`,
      date: "2026-01-01",
      slug: String(i),
      speakers: [],
    }) as ListItem,
);
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
};
const request = { query: "housing", from: "", to: "", page: 2 };
test("filtered page restoration, bounds, and data retry", async () => {
  let fail = true;
  const load = createListLoader({
    initialItems: items.slice(0, 2),
    total: 6,
    size: 2,
    type: "question",
    fetchData: async () => {
      if (fail) throw Error("offline");
      return items;
    },
    loadIndex: async () => null,
  });
  await expect(load(request)).rejects.toThrow("offline");
  fail = false;
  expect((await load(request)).items.map((i) => i.id)).toEqual(["2", "3"]);
  expect((await load({ ...request, query: "", from: "2026-01-01" })).page).toBe(
    2,
  );
  expect((await load({ ...request, page: 999 })).page).toBe(3);
  for (const page of [0, -1, 1.5, NaN, Infinity])
    expect(clampPage(page, 6, 2)).toBe(1);
});
test("visible page waits for an existing prefetch", async () => {
  const pending = deferred<{ meta: { id: string } }>();
  let calls = 0;
  const load = createListLoader({
    initialItems: [],
    total: 6,
    size: 2,
    type: "question",
    fetchData: async () => items,
    loadIndex: async () => ({
      search: async () => ({
        results: items.map((item, i) => ({
          data: () => {
            if (i === 2) {
              calls++;
              return pending.promise;
            }
            return Promise.resolve({ meta: { id: item.id } });
          },
        })),
      }),
    }),
  });
  await load({ ...request, page: 1 });
  let settled = false;
  const next = load(request).then((v) => {
    settled = true;
    return v;
  });
  await new Promise((r) => setTimeout(r, 0));
  expect(settled).toBe(false);
  expect(calls).toBe(1);
  pending.resolve({ meta: { id: "2" } });
  expect((await next).items.map((i) => i.id)).toEqual(["2", "3"]);
});
let root: HTMLElement | undefined;
const replacedGlobals = ["window", "document", "HTMLElement", "fetch"] as const;
let originalGlobals: Map<string, PropertyDescriptor | undefined> | undefined;
afterEach(() => {
  if (root) act(() => render(null, root!));
  root = undefined;
  if (originalGlobals) {
    for (const [key, descriptor] of originalGlobals) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
    originalGlobals = undefined;
  }
});
async function mount(
  search = "",
  fetcher: typeof fetch = (async () =>
    new Response(JSON.stringify({ items }))) as unknown as typeof fetch,
) {
  originalGlobals = new Map(
    replacedGlobals.map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  const window = new Window({ url: `https://example.com/questions${search}` });
  Object.assign(globalThis, {
    window,
    document: window.document,
    HTMLElement: window.HTMLElement,
  });
  globalThis.fetch = fetcher;
  root = document.createElement("div");
  document.body.append(root);
  await act(async () =>
    render(
      <PaginatedList
        contentType="question"
        dataUrl="/data/questions.json"
        totalCount={6}
        pageSize={2}
        initialItems={items.slice(0, 2)}
      />,
      root!,
    ),
  );
  return root!;
}
const settle = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });
test("mounted error retry preserves date page and exposes accessible status", async () => {
  let fail = true;
  const el = await mount("?from=2026-01-01&page=2", (async () =>
    fail
      ? new Response("", { status: 503 })
      : new Response(JSON.stringify({ items }))) as unknown as typeof fetch);
  await settle();
  expect(el.textContent).toContain("Could not load results");
  expect(el.textContent).not.toContain("No results found");
  fail = false;
  await act(async () =>
    Array.from(el.querySelectorAll("button"))
      .find((b) => b.textContent === "Retry")!
      .click(),
  );
  await settle();
  expect(el.textContent).toContain("housing 2");
  expect(window.location.search).toContain("page=2");
  expect(
    el.querySelector("input[type=text]")?.getAttribute("aria-label"),
  ).toBeTruthy();
  expect(el.querySelector("[role=status]")).toBeTruthy();
});
test("Escape cancels debounce and an old page completion cannot replace restored browse", async () => {
  const pending = deferred<Response>();
  const el = await mount(
    "",
    (() => pending.promise) as unknown as typeof fetch,
  );
  const input = el.querySelector("input[type=text]") as HTMLInputElement;
  await act(async () => {
    input.value = "housing";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await act(async () => {
    input.dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    );
  });
  await act(async () => {
    await new Promise((r) => setTimeout(r, 180));
  });
  expect(input.value).toBe("");
  expect(window.location.search).toBe("");
  await act(async () =>
    Array.from(el.querySelectorAll("button"))
      .find((b) => b.textContent?.includes("Next"))!
      .click(),
  );
  await act(async () => {
    window.history.replaceState({}, "", "/questions");
    window.dispatchEvent(new window.PopStateEvent("popstate"));
  });
  pending.resolve(new Response(JSON.stringify({ items })));
  await settle();
  expect(el.textContent).toContain("housing 0");
  expect(el.textContent).not.toContain("housing 2");
  expect(window.location.search).toBe("");
});
test("index query and fragment failures reject and can retry", async () => {
  let queryFails = true,
    fragmentFails = true;
  const index = {
    search: async () => {
      if (queryFails) throw Error("index");
      return {
        results: items.map((item) => ({
          data: async () => {
            if (fragmentFails) throw Error("fragment");
            return { meta: { id: item.id } };
          },
        })),
      };
    },
  };
  const load = createListLoader({
    initialItems: [],
    total: 6,
    size: 2,
    type: "question",
    fetchData: async () => items,
    loadIndex: async () => index,
  });
  await expect(load(request)).rejects.toThrow("index");
  queryFails = false;
  await expect(load({ ...request, from: "2026-01-01" })).rejects.toThrow(
    "fragment",
  );
  fragmentFails = false;
  expect(
    (await load({ ...request, from: "2026-01-01" })).items.map((i) => i.id),
  ).toEqual(["2", "3"]);
});
test("rapid page requests settle on the last page, and clear cancels pending text", async () => {
  const pending = deferred<Response>();
  const el = await mount(
    "",
    (() => pending.promise) as unknown as typeof fetch,
  );
  const next = () =>
    Array.from(el.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Next"),
    )!;
  await act(async () => next().click());
  expect(el.textContent).toContain("Page 2 of 3");
  await act(async () => next().click());
  expect(el.textContent).toContain("Page 3 of 3");
  pending.resolve(new Response(JSON.stringify({ items })));
  await settle();
  expect(el.textContent).toContain("housing 4");
  expect(el.textContent).not.toContain("housing 2");
  const input = el.querySelector("input[type=text]") as HTMLInputElement;
  await act(async () => {
    input.value = "housing";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await act(async () =>
    el.querySelector<HTMLButtonElement>('[aria-label="Clear search"]')!.click(),
  );
  await act(async () => {
    await new Promise((r) => setTimeout(r, 180));
  });
  expect(input.value).toBe("");
  expect(window.location.search).toBe("");
});
test("unmount cancels pending input and prevents URL updates from active requests", async () => {
  const pending = deferred<Response>();
  const el = await mount(
    "?page=2",
    (() => pending.promise) as unknown as typeof fetch,
  );
  await act(async () => render(null, el));
  pending.resolve(new Response(JSON.stringify({ items })));
  await settle();
  expect(window.location.search).toBe("?page=2");
});
test("mounted fallback restores query page and date controls preserve the query", async () => {
  const el = await mount("?q=housing&page=2");
  await settle();
  expect(el.textContent).toContain("housing 2");
  expect(window.location.search).toContain("page=2");
  const from = el.querySelector("#date-from") as HTMLInputElement;
  const to = el.querySelector("#date-to") as HTMLInputElement;
  await act(async () => {
    from.value = "2026-01-01";
    from.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await settle();
  await act(async () => {
    to.value = "2026-01-01";
    to.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await settle();
  expect(window.location.search).toContain("q=housing");
  expect(window.location.search).toContain("to=2026-01-01");
  expect(el.textContent).toContain("housing 0");
  await act(async () =>
    Array.from(el.querySelectorAll("button"))
      .find((button) => button.textContent === "Clear dates")!
      .click(),
  );
  await settle();
  expect(window.location.search).toBe("?q=housing");
});
