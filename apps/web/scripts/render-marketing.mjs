// Renders a pack's marketing sources (HTML + timeline.js) to MP4, PNG and PDF.
//   node scripts/render-marketing.mjs video <html> <out.mp4> <width> <height> [fps]
//   node scripts/render-marketing.mjs still <html> <out.png|jpg> <width> <height> [t]
//   node scripts/render-marketing.mjs pdf   <html> <out.pdf>
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [mode, html, out, w = "1920", h = "1080", extra] = process.argv.slice(2);
const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  proxy,
  args: ["--ignore-certificate-errors"], // the sandbox's proxy re-signs TLS; fonts only
});
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
await page.goto(pathToFileURL(resolve(html)).href, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);

if (mode === "still") {
  await page.evaluate((t) => window.render?.(t), +(extra ?? 0));
  await page.screenshot({ path: out });
} else if (mode === "pdf") {
  await page.pdf({ path: out, printBackground: true, preferCSSPageSize: true });
} else if (mode === "video") {
  const fps = +(extra ?? 30);
  const duration = await page.evaluate(() => window.DURATION);
  const dir = mkdtempSync(join(tmpdir(), "frames-"));
  const frames = Math.round(duration * fps);
  for (let i = 0; i < frames; i++) {
    await page.evaluate((t) => window.render(t), i / fps);
    await page.screenshot({ path: join(dir, `${String(i).padStart(5, "0")}.jpg`), type: "jpeg", quality: 92 });
  }
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(fps), "-i", join(dir, "%05d.jpg"),
    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]);
  rmSync(dir, { recursive: true });
  console.log(`${out}: ${frames} frames, ${duration}s`);
}
await browser.close();
