import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { buildLeaderboardData } from "./leaderboard-data.mjs";
if (!process.argv.includes("--dist")) buildLeaderboardData();
const root = path.resolve(process.argv.includes("--dist") ? "dist" : ".");
const port = Number(process.env.PORT || 4177);
const hero = process.argv.includes("--dist") ? null
  : await (await import("./hero-bundle.mjs")).watchHero();
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".md": "text/plain; charset=utf-8",
  ".png": "image/png",
  ".pdf": "application/pdf",
};
http
  .createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      const target = path.resolve(root, "." + decodeURIComponent(url.pathname));
      if (target !== root && !target.startsWith(root + path.sep)) {
        res.writeHead(403);
        res.end();
        return;
      }
      const stat = await fs.stat(target);
      const file = stat.isDirectory()
        ? path.join(target, "index.html")
        : target;
      const body = hero && file === path.join(root, "src", "hero-surface.js")
        ? hero.content() : await fs.readFile(file);
      res.writeHead(200, {
        "Content-Type": types[path.extname(file)] || "application/octet-stream",
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
      });
      res.end(body);
    } catch {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("Not found");
    }
  })
  .listen(port, "127.0.0.1", () =>
    console.log(`BEND 2.0 preview: http://127.0.0.1:${port}`),
  );

process.once("SIGINT", async () => {
  await hero?.dispose();
  process.exit(0);
});
