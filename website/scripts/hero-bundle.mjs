import { build, context } from "esbuild";
import { fileURLToPath } from "node:url";

const options = {
  entryPoints: [fileURLToPath(new URL("../src/hero-surface.js", import.meta.url))],
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
  legalComments: "eof",
  logLevel: "warning",
};

export function buildHero(outfile) {
  return build({ ...options, outfile });
}

export async function watchHero() {
  let content;
  const session = await context({
    ...options,
    write: false,
    plugins: [{
      name: "hero-preview",
      setup(builder) {
        builder.onEnd(result => {
          if (!result.errors.length) content = result.outputFiles[0].contents;
        });
      },
    }],
  });
  await session.rebuild();
  await session.watch();
  return { content: () => content, dispose: () => session.dispose() };
}
