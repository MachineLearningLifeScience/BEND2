import fs from "node:fs/promises";
import { buildHero } from "./hero-bundle.mjs";
import { buildLeaderboardData } from "./leaderboard-data.mjs";
buildLeaderboardData();

// Social crawlers need absolute URLs; the local authoring site has no public
// origin. Pages supplies its actual base URL, including any project subpath.
let siteURL;
if (process.env.SITE_URL) {
  siteURL = new URL(process.env.SITE_URL);
  if (!["https:", "http:"].includes(siteURL.protocol) || siteURL.username || siteURL.password || siteURL.search || siteURL.hash)
    throw new Error("SITE_URL must be a public HTTP(S) base URL without credentials, query or fragment.");
  if (!siteURL.pathname.endsWith("/")) siteURL.pathname += "/";
}
await fs.rm("dist", { recursive: true, force: true });
await fs.mkdir("dist", { recursive: true });
for (const name of ["index.html", "src", "assets", "provenance"]) {
  await fs.cp(name, `dist/${name}`, { recursive: true });
}
if (siteURL) {
  const attribute = value => value.replaceAll("&", "&amp;").replaceAll('"', "&quot;");
  const imageURL = new URL("assets/social-preview.png", siteURL).href;
  let html = await fs.readFile("dist/index.html", "utf8");
  html = html.replaceAll('content="./assets/social-preview.png"', `content="${attribute(imageURL)}"`);
  html = html.replace('    <meta property="og:type"',
    `    <link rel="canonical" href="${attribute(siteURL.href)}" />\n    <meta property="og:url" content="${attribute(siteURL.href)}" />\n    <meta property="og:type"`);
  await fs.writeFile("dist/index.html", html);
}
await buildHero("dist/src/hero-surface.js");
await fs.mkdir("dist/data", { recursive: true });
for (const name of ["benchmark.json", "sources.md", "evaluation-updates.json"])
  await fs.copyFile(`data/${name}`, `dist/data/${name}`);
await fs.writeFile("dist/.nojekyll", "");
console.log("Built a self-contained static website in dist/.");
