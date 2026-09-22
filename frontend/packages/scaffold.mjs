#!/usr/bin/env node
// Scaffold an extractable block package under frontend/packages/<id>/.
//
// Usage (run from frontend/):
//   node packages/scaffold.mjs <block-id>
//
// Creates packages/<id>/ with package.json (@tribunal/<id>), tsconfig.json
// (extends the root), src/index.ts, and a README stub. It does NOT move any
// block source — that happens in per-block extraction tasks.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PACKAGES_DIR = __dirname;
const FRONTEND_DIR = resolve(__dirname, "..");
const REGISTRY_PATH = resolve(FRONTEND_DIR, "../docs/blocks/registry.json");

function fail(message) {
  console.error(`✖ ${message}`);
  process.exit(1);
}

const rawId = process.argv[2];
if (!rawId) {
  fail("Usage: node packages/scaffold.mjs <block-id>");
}

const id = rawId.trim();
if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(id)) {
  fail(
    `Invalid block id "${id}". Use a kebab-case slug, e.g. "lead-capture".`,
  );
}

// Validate against the block registry when it is available.
if (existsSync(REGISTRY_PATH)) {
  try {
    const registry = JSON.parse(readFileSync(REGISTRY_PATH, "utf8"));
    const ids = Array.isArray(registry)
      ? registry.map((b) => b?.id).filter(Boolean)
      : [];
    if (ids.length > 0 && !ids.includes(id)) {
      fail(
        `"${id}" is not a known block id in docs/blocks/registry.json.\n` +
          `  Known ids: ${ids.join(", ")}`,
      );
    }
  } catch (err) {
    console.warn(`! Could not parse registry (${err.message}); skipping check.`);
  }
}

const pkgDir = join(PACKAGES_DIR, id);
if (existsSync(pkgDir)) {
  fail(`packages/${id}/ already exists — refusing to overwrite.`);
}

const pkgName = `@tribunal/${id}`;

const packageJson = {
  name: pkgName,
  version: "0.1.0",
  private: false,
  license: "LicenseRef-Proprietary",
  type: "module",
  main: "./dist/index.js",
  module: "./dist/index.js",
  types: "./dist/index.d.ts",
  exports: {
    ".": {
      types: "./dist/index.d.ts",
      import: "./dist/index.js",
    },
  },
  files: ["dist"],
  scripts: {
    build: "tsup src/index.ts --format esm --dts --clean",
    dev: "tsup src/index.ts --format esm --dts --watch",
    typecheck: "tsc --noEmit",
    clean: "rm -rf dist",
  },
  peerDependencies: {
    react: ">=19",
    "react-dom": ">=19",
  },
};

const tsconfigJson = {
  extends: "../../tsconfig.json",
  compilerOptions: {
    noEmit: false,
    outDir: "dist",
    rootDir: "src",
    declaration: true,
    plugins: [],
    paths: {},
  },
  include: ["src"],
  exclude: ["node_modules", "dist"],
};

const indexTs = `// Public entry for ${pkgName}.
// Re-export the block public_api from docs/blocks/${id}/BLOCK.md here.
// Placeholder export keeps the module valid until block code is moved in.
export const blockId = ${JSON.stringify(id)} as const;
`;

const readmeMd = `# ${pkgName}

Extracted package for the **${id}** block.

> Public API mirrors \`docs/blocks/${id}/BLOCK.md\` (\`public_api\`). Fill this in
> as the block's source is moved into \`src/\` during extraction.

## Install

\`\`\`bash
npm install ${pkgName}
\`\`\`

## Public API

_TODO: document the exports from \`src/index.ts\`, mirroring the block's
\`public_api\` surface in \`docs/blocks/${id}/BLOCK.md\`._

## Build

\`\`\`bash
npm run build      # tsup -> dist/ (esm + d.ts)
npm run typecheck  # tsc --noEmit
\`\`\`
`;

mkdirSync(join(pkgDir, "src"), { recursive: true });
writeFileSync(
  join(pkgDir, "package.json"),
  JSON.stringify(packageJson, null, 2) + "\n",
);
writeFileSync(
  join(pkgDir, "tsconfig.json"),
  JSON.stringify(tsconfigJson, null, 2) + "\n",
);
writeFileSync(join(pkgDir, "src", "index.ts"), indexTs);
writeFileSync(join(pkgDir, "README.md"), readmeMd);

console.log(`✓ Created packages/${id}/ (${pkgName})`);
console.log("  Next:");
console.log("    1. Run `npm install` from frontend/ to link the workspace.");
console.log(`    2. Move ${id} block source into packages/${id}/src/.`);
console.log("    3. Re-export the block public_api from src/index.ts.");
