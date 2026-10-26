import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export function buildLeaderboardData() {
  const script = fileURLToPath(new URL("./build_leaderboard.py", import.meta.url));
  const python = process.env.BEND2_PYTHON || "python3";
  const result = spawnSync(python, [script], { stdio: "inherit" });
  if (result.error || result.status !== 0) {
    throw new Error(`Leaderboard data build failed. Install the benchmark package and activate its environment, or set BEND2_PYTHON to that environment's Python. ${result.error?.message || ""}`);
  }
}
