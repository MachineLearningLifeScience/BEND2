import fs from "node:fs/promises";
import { buildHero } from "./hero-bundle.mjs";
import { buildLeaderboardData } from "./leaderboard-data.mjs";
buildLeaderboardData();
await fs.rm("dist", { recursive: true, force: true });
await fs.mkdir("dist", { recursive: true });
for (const name of ["index.html", "src", "assets", "provenance"]) {
  await fs.cp(name, `dist/${name}`, { recursive: true });
}
await buildHero("dist/src/hero-surface.js");
await fs.mkdir("dist/data", { recursive: true });
for (const name of ["benchmark.json", "sources.md"])
  await fs.copyFile(`data/${name}`, `dist/data/${name}`);
await fs.writeFile("dist/.nojekyll", "");
console.log("Built a self-contained static website in dist/.");
