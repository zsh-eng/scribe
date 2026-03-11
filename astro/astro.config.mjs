// @ts-check
import preact from "@astrojs/preact";
import tailwind from "@astrojs/tailwind";
import pagefind from "astro-pagefind";
import { defineConfig } from "astro/config";

// https://astro.build/config
export default defineConfig({
  output: "static",
  prefetch: {
    prefetchAll: true,
    defaultStrategy: "tap",
  },
  build: {
    format: "file",
  },
  integrations: [tailwind(), pagefind(), preact()],
});
