// @ts-check
import tailwind from "@astrojs/tailwind";
import pagefind from "astro-pagefind";
import { defineConfig } from "astro/config";

// https://astro.build/config
export default defineConfig({
  output: "static",
  build: {
    format: "file",
  },
  integrations: [tailwind(), pagefind()],
});
