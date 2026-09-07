import { readFileSync } from "node:fs";
import { Window } from "happy-dom";

export function source(path: string) {
  return readFileSync(new URL(`../../src/${path}`, import.meta.url), "utf8");
}

// Execute the shipped client script against a DOM fixture. Only the external
// Pagefind module boundary is replaced, so events and async guards are real.
export function runScript(window: Window, path: string) {
  const script = source(path).match(/<script>([\s\S]*?)<\/script>/)?.[1];
  if (!script) throw new Error(`No client script in ${path}`);
  const code = script
    .replaceAll("import.meta.env.BASE_URL", '"/"')
    .replace("import(/* @vite-ignore */ pagefindPath)", "window.__loadPagefind()");
  const execute = new Function("window", "document", "CustomEvent", "setTimeout", "clearTimeout", new Bun.Transpiler({ loader: "ts" }).transformSync(code));
  execute(window, window.document, window.CustomEvent, window.setTimeout.bind(window), window.clearTimeout.bind(window));
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
