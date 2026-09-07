import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { transform } from "@astrojs/compiler";
import { experimental_AstroContainer } from "astro/container";
import { Window } from "happy-dom";
import { slugify } from "../src/lib/slugify";
const source = (path: string) =>
  Bun.file(new URL(`../src/${path}`, import.meta.url)).text();
// Compile the real server template. The client script is tested separately below.
async function transcript(props: Record<string, unknown>) {
  const compiled = await transform(
    (await source("components/TranscriptDialogue.astro"))
      .replace(/<script>[\s\S]*?<\/script>/, "")
      .replace(/<style[^>]*>[\s\S]*?<\/style>/, ""),
    {
      filename: "TranscriptDialogue.astro",
      normalizedFilename: "TranscriptDialogue.astro",
      astroGlobalArgs: "undefined",
      internalURL: import.meta.resolve("astro/compiler-runtime"),
      resultScopedSlot: true,
      renderScript: true,
    },
  );
  // The compiler emits legacy metadata that the container runtime does not use.
  const code = new Bun.Transpiler({ loader: "ts" }).transformSync(
    compiled.code
      .replace(/,\s*createMetadata as \$\$createMetadata/, "")
      .replace(/^export const \$\$metadata = .*;$/gm, ""),
  );
  const directory = await mkdtemp(join(tmpdir(), "scribe-render-"));
  try {
    const file = join(directory, "component.mjs");
    await Bun.write(file, code);
    const module = await import(file);
    const container = await experimental_AstroContainer.create();
    return await container.renderToString(module.default, {
      props: { instanceId: "fixture", ...props },
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
test("transcript renders plain text unchanged, escapes markup, and prefers HTML", async () => {
  const window = new Window();
  const plain = "  First line\n\nSecond <script>literal</script>  ";
  window.document.body.innerHTML = await transcript({ contentPlain: plain });
  const body = window.document.body.querySelector(".whitespace-pre-wrap")!;
  expect(body.textContent).toBe(plain);
  expect(body.querySelector("script")).toBeNull();
  window.document.body.innerHTML = await transcript({
    contentHtml: "<p>HTML wins</p>",
    contentPlain: plain,
  });
  expect(
    window.document.body.querySelector("[data-transcript-source]")?.textContent,
  ).toBe("HTML wins");
  expect(window.document.body.querySelector(".whitespace-pre-wrap")).toBeNull();
  expect(await transcript({})).toContain("Transcript not available.");
});
test("transcript enhancement preserves text around speaker paragraphs in source order", async () => {
  const window = new Window();
  window.document.body.innerHTML =
    '<div data-transcript-shell data-transcript-id="fixture"><div data-transcript-source>Before text<p><strong>Mr Example:</strong> Spoken text</p>Between text<p>Continuation</p><p><strong>Ms Other</strong>: Next speech</p>After text</div></div>';
  const script = (await source("components/TranscriptDialogue.astro")).match(
    /<script>([\s\S]*?)<\/script>/,
  )![1];
  const names = ["document", "HTMLElement", "HTMLParagraphElement", "Node"];
  new Function(
    ...names,
    new Bun.Transpiler({ loader: "ts" }).transformSync(script),
  )(...names.map((name) => (window as any)[name]));
  window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  const element = window.document.querySelector("[data-transcript-source]")!;
  expect(element.classList.contains("transcript-source--enhanced")).toBe(true);
  expect(element.textContent).toBe(
    "Before textMr Example Spoken textBetween textContinuationMs OtherNext speechAfter text",
  );
  expect(
    Array.from(element.querySelectorAll(".transcript-dialogue__speaker")).map(
      (node) => node.textContent,
    ),
  ).toEqual(["Mr Example", "Ms Other"]);
});
test("statement paths supplement detail routes without changing questions or classified routes", async () => {
  const db = new Database(":memory:");
  db.exec(`CREATE TABLE sections(id TEXT, sitting_id TEXT, section_title TEXT, section_type TEXT, category TEXT, content_plain TEXT, section_order INTEGER, source_url TEXT, summary TEXT, ministry_id TEXT);
  CREATE TABLE sittings(id TEXT,date TEXT,sitting_no INTEGER); CREATE TABLE ministries(id TEXT,name TEXT); CREATE TABLE section_speakers(section_id TEXT,member_id TEXT,constituency TEXT,designation TEXT); CREATE TABLE members(id TEXT,name TEXT);
  INSERT INTO sittings VALUES ('s','2026-01-01',1);`);
  for (const [id, type, category] of [
    ["q", "OA", null],
    ["oral", "OS", null],
    ["written", "WS", "other"],
    ["motion", "OS", "motion"],
    ["adjournment", "WS", "adjournment_motion"],
    ["clarification", "OS", "clarification"],
    ["bill", "BP", null],
  ])
    db.prepare(
      "INSERT INTO sections(id,sitting_id,section_title,section_type,category) VALUES (?,'s',?,?,?)",
    ).run(id, id, type, category);
  const code = new Bun.Transpiler({ loader: "ts" }).transformSync(
    (await source("lib/queries/sections.ts"))
      .replace(/^import .*$/gm, "")
      .replaceAll("export function", "function"),
  );
  const queries = new Function(
    "db",
    `${code};return {getQuestions,getQuestionCount,getStatementDetailPaths};`,
  )(db);
  expect(queries.getStatementDetailPaths().map((s: any) => s.id)).toEqual([
    "oral",
    "written",
  ]);
  expect(queries.getQuestions().map((s: any) => s.id)).toEqual(["q"]);
  expect(queries.getQuestionCount()).toBe(1);
  const page = await source("pages/questions/[slug].astro");
  const pathsCode = page.match(
    /export async function getStaticPaths\(\) \{([\s\S]*?)\n\}/,
  )![1];
  const paths = new Function(
    "getQuestions",
    "getStatementDetailPaths",
    "slugify",
    pathsCode,
  )(queries.getQuestions, queries.getStatementDetailPaths, slugify);
  expect(paths.map((p: any) => p.props.id)).toEqual(["q", "oral", "written"]);
  db.close();
});
test("both bill reading slots pass available plain text to the renderer", async () => {
  const page = await source("pages/bills/[slug].astro");
  const slots = [...page.matchAll(/<TranscriptDialogue\s+([\s\S]*?)\/>/g)];
  expect(slots.length).toBe(2);
  for (const slot of slots) {
    const props: Record<string, unknown> = {};
    for (const attribute of slot[1].matchAll(
      /(contentHtml|contentPlain)=\{([^}]+)\}/g,
    )) {
      props[attribute[1]] = new Function(
        "firstReadings",
        "section",
        `return ${attribute[2]}`,
      )([{ contentHtml: null, contentPlain: "First\n reading" }], {
        contentHtml: null,
        contentPlain: "Second\n reading",
      });
    }
    const html = await transcript(props);
    expect(html).toContain("whitespace-pre-wrap");
    expect(html).not.toContain("Transcript not available.");
  }
});
test("statement detail labels retain oral/written type and use a separate search type", async () => {
  const page = await source("pages/questions/[slug].astro");
  const frontmatter = page
    .split("---")[1]
    .replace(/^import .*$/gm, "")
    .replace(/export async function getStaticPaths\(\) \{[\s\S]*?\n\}/, "");
  for (const [sectionType, label, indexType] of [
    ["OS", "Oral Statement", "type:statement"],
    ["WS", "Written Statement", "type:statement"],
    ["OA", "Oral Answer", "type:question"],
  ]) {
    const values = new Function(
      "Astro",
      "getSection",
      new Bun.Transpiler({ loader: "ts" }).transformSync(
        `${frontmatter};return {typeLabel,isStatement};`,
      ),
    )({ props: { id: "fixture" } }, () => ({
      id: "fixture",
      sectionType,
      category: sectionType === "OA" ? null : "statement",
    }));
    expect(values.typeLabel).toBe(label);
    const filter = page.match(/data-pagefind-filter=\{([^}]+)\}/)![1];
    expect(
      new Function("isStatement", `return ${filter}`)(values.isStatement),
    ).toBe(indexType);
  }
});
