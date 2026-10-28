import { defineConfig } from "astro/config";

const rawBase = process.env.ASTRO_BASE || "/";
const base = rawBase === "/" ? "/" : `/${rawBase.replace(/^\/+|\/+$/g, "")}`;

export default defineConfig({
  site: process.env.ASTRO_SITE || "https://example.com",
  base,
  output: "static",
  trailingSlash: "always",
  build: {
    assets: "assets",
  },
});

