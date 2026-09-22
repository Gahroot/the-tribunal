# `frontend/packages/` — extractable block packages

This directory is the npm **workspaces** root for libraries extracted from the
Next.js app. The app itself stays at `frontend/` (package `aicrm`); each library
extracted from a block lives in its own folder here and becomes an independently
installable npm package.

The root `frontend/package.json` declares:

```json
"workspaces": ["packages/*"]
```

so `npm ci` / `npm install` run from `frontend/` install and link every package
under `packages/*` alongside the app. The app's `tsc --noEmit` typecheck
**excludes** `packages/` (see `frontend/tsconfig.json`) — each package
typechecks and builds itself.

## Convention

Each package mirrors exactly one block from `docs/blocks/<block>/BLOCK.md`.

| Aspect          | Rule                                                            |
| --------------- | --------------------------------------------------------------- |
| Folder          | `frontend/packages/<block-id>/`                                 |
| npm name        | `@tribunal/<block-id>`                                          |
| Version         | starts at `0.1.0`                                               |
| `private`       | `false` (these are meant to be publishable)                     |
| Entry           | `src/index.ts` re-exports the block's `public_api` surface      |
| Types           | emitted to `dist/` and referenced via package `exports`/`types` |
| Build           | `tsup` (preferred) or `tsc`                                     |
| `tsconfig.json` | extends the root `../../tsconfig.json`                          |
| `README.md`     | mirrors the block's `BLOCK.md` `public_api`                     |

### Required files per package

```
packages/<block-id>/
  package.json      # name @tribunal/<block-id>, exports/main/types, build script
  tsconfig.json     # extends ../../tsconfig.json, emits to dist/
  src/index.ts      # public entry — re-exports the block public_api
  README.md         # public API doc mirroring docs/blocks/<block-id>/BLOCK.md
```

### `package.json` shape

```json
{
  "name": "@tribunal/<block-id>",
  "version": "0.1.0",
  "private": false,
  "type": "module",
  "main": "./dist/index.js",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "files": ["dist"],
  "scripts": {
    "build": "tsup src/index.ts --format esm --dts --clean",
    "typecheck": "tsc --noEmit"
  }
}
```

## Scaffolding a new package

From `frontend/`:

```bash
node packages/scaffold.mjs <block-id>
```

This creates `packages/<block-id>/` with `package.json`, `tsconfig.json`,
`src/index.ts`, and a `README.md` stub. It refuses to overwrite an existing
package and validates the id against `docs/blocks/registry.json` when present.

After scaffolding, run `npm install` from `frontend/` to link the new workspace,
then move the block's source into `src/` and re-export its `public_api` from
`src/index.ts`.

## Important

- **Do not** put app-only code here. Only block libraries that are meant to be
  extracted/published.
- Moving block code happens in per-block extraction tasks, not when the
  workspace is first introduced.
- Keep React/Next and other shared libs as `peerDependencies` in each package so
  the app and packages resolve a single copy.
