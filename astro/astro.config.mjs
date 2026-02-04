// @ts-check
import { defineConfig } from "astro/config";
import cloudflare from "@astrojs/cloudflare";
import tailwind from "@astrojs/tailwind";
import pagefind from "astro-pagefind";

// https://astro.build/config
export default defineConfig({
  output: "static",
  build: {
    format: "file",
  },
  adapter: cloudflare(),
  integrations: [tailwind(), pagefind()],
});
