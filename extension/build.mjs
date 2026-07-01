import * as esbuild from "esbuild";
import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dir = dirname(fileURLToPath(import.meta.url));
const dist = join(__dir, "dist");
const watch = process.argv.includes("--watch");

mkdirSync(join(dist, "icons"), { recursive: true });

// Copy real icon assets (generated in extension/icons/)
for (const size of [16, 48, 128]) {
  cpSync(join(__dir, "icons", `icon${size}.png`), join(dist, "icons", `icon${size}.png`));
}

cpSync(join(__dir, "manifest.json"), join(dist, "manifest.json"));
cpSync(join(__dir, "src/popup/popup.html"), join(dist, "popup.html"));
cpSync(join(__dir, "src/popup/popup.css"), join(dist, "popup.css"));

const ctx = await esbuild.context({
  entryPoints: {
    background: join(__dir, "src/background/service-worker.ts"),
    content: join(__dir, "src/content/content-script.ts"),
    popup: join(__dir, "src/popup/popup.ts"),
  },
  bundle: true,
  outdir: dist,
  format: "esm",
  target: "chrome120",
  sourcemap: true,
  logLevel: "info",
});

if (watch) {
  await ctx.watch();
  console.log("Watching extension…");
} else {
  await ctx.rebuild();
  await ctx.dispose();
  console.log("Built → extension/dist/");
}
