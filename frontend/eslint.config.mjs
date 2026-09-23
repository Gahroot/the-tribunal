import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import eslintConfigPrettier from "eslint-config-prettier";
import boundaries from "eslint-plugin-boundaries";
import jsxA11y from "eslint-plugin-jsx-a11y";
import unusedImports from "eslint-plugin-unused-imports";

// ---------------------------------------------------------------------------
// Module-boundary enforcement (eslint-plugin-boundaries)
// ---------------------------------------------------------------------------
// Each `src/components/<block>` folder is a feature "block". Blocks may import
// shared layers (ui / shared / lib / providers / types) and themselves, but
// importing another block is only allowed when that edge is declared below.
// The embeddable widget (`src/widget`) must stay standalone-embeddable: it may
// only touch the widget-safe `src/lib/embed` contract, never dashboard app code.
//
// Declared cross-block edges are seeded from docs/blocks/registry.json
// `depends_on`, mapped to the frontend component folders each block owns.
// Undeclared cross-block imports are reported as warnings (not errors) so the
// build keeps passing while the coupling is tracked in
// docs/blocks/frontend-boundary-violations.md and decoupled over time.
//
// Enforced as ERRORS (must stay green): widget isolation and the one-way
// shared-layer rule. Enforced as WARNINGS: genuine cross-block violations.
const BLOCK_CROSS_DEPENDENCIES = {
  // <block folder>: [...allowed cross-block target folders]
  // agent-brain → appointments, hitl, knowledge, messaging, offers, voice
  agents: [
    "calendar",
    "pending-actions",
    "nudges",
    "knowledge",
    "campaigns",
    "offers",
    "calls",
  ],
  experiments: [
    "calendar",
    "pending-actions",
    "nudges",
    "knowledge",
    "campaigns",
    "offers",
    "calls",
  ],
  // appointments → contacts, messaging, voice, reviews
  calendar: [
    "contacts",
    "segments",
    "tags",
    "filters",
    "campaigns",
    "calls",
    "reviews",
    "appointments",
  ],
  // contacts → agent-brain, voice
  contacts: ["agents", "experiments", "calls"],
  // conversations → thread composer/feed, contact context panel
  conversations: ["conversation", "contacts"],
  segments: ["agents", "experiments", "calls"],
  tags: ["agents", "experiments", "calls"],
  filters: ["agents", "experiments", "calls"],
  // hitl → agent-brain, appointments, contacts, messaging, voice
  "pending-actions": [
    "agents",
    "experiments",
    "calendar",
    "contacts",
    "segments",
    "tags",
    "filters",
    "campaigns",
    "calls",
  ],
  nudges: [
    "agents",
    "experiments",
    "calendar",
    "contacts",
    "segments",
    "tags",
    "filters",
    "campaigns",
    "calls",
  ],
  // knowledge → agent-brain, offers
  knowledge: ["agents", "experiments", "offers"],
  // lead-capture → voice, agent-brain, offers, contacts, messaging
  "lead-magnets": [
    "calls",
    "agents",
    "experiments",
    "offers",
    "contacts",
    "segments",
    "tags",
    "filters",
    "campaigns",
  ],
  // messaging → contacts, agent-brain, voice, offers, hitl
  campaigns: [
    "contacts",
    "segments",
    "tags",
    "filters",
    "agents",
    "experiments",
    "calls",
    "offers",
    "pending-actions",
    "nudges",
  ],
  // offers → agent-brain, lead-capture, contacts
  offers: [
    "agents",
    "experiments",
    "lead-magnets",
    "contacts",
    "segments",
    "tags",
    "filters",
  ],
  // reviews → voice, agent-brain, appointments
  reviews: ["calls", "agents", "experiments", "calendar"],
  // voice → agent-brain, contacts, messaging, hitl
  calls: [
    "agents",
    "experiments",
    "contacts",
    "segments",
    "tags",
    "filters",
    "campaigns",
    "pending-actions",
    "nudges",
  ],
};

// Shared layers every block is allowed to import.
const SHARED_ELEMENT_TYPES = [
  "ui",
  "shared",
  "lib",
  "lib-embed",
  "providers",
  "types",
];

// Allow rules for the declared cross-block edges above.
const crossBlockAllowRules = Object.entries(BLOCK_CROSS_DEPENDENCIES).map(
  ([block, deps]) => ({
    from: [["block", { block }]],
    allow: deps.map((dep) => ["block", { block: dep }]),
  }),
);

const boundariesElements = [
  // Order matters: more specific shared folders before the generic block glob.
  { type: "ui", pattern: "src/components/ui", mode: "folder" },
  { type: "shared", pattern: "src/components/shared", mode: "folder" },
  {
    type: "block",
    pattern: "src/components/*",
    mode: "folder",
    capture: ["block"],
  },
  { type: "widget", pattern: "src/widget", mode: "folder" },
  // Widget-safe embed contract — must be listed before the generic `lib`.
  { type: "lib-embed", pattern: "src/lib/embed", mode: "folder" },
  { type: "lib", pattern: "src/lib", mode: "folder" },
  { type: "providers", pattern: "src/providers", mode: "folder" },
  { type: "types", pattern: "src/types", mode: "folder" },
];

// `eslint-config-next` already registers the `import` and `jsx-a11y` plugins.
// Re-registering them in a flat config errors with "Cannot redefine plugin",
// so we only register plugins it doesn't ship (unused-imports) and merge the
// recommended jsx-a11y rules in directly.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    plugins: {
      "unused-imports": unusedImports,
    },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
    },
  },
  // Register the boundaries plugin + element model once, for all files.
  {
    plugins: { boundaries },
    settings: {
      "boundaries/include": ["src/**/*.{ts,tsx}"],
      // Tests/fixtures are not production coupling — keep them out of the graph
      // so the violations report reflects real shipped imports only.
      "boundaries/ignore": [
        "**/*.test.{ts,tsx}",
        "**/*.spec.{ts,tsx}",
        "src/test/**",
      ],
      "boundaries/elements": boundariesElements,
    },
  },
  // ERROR: the embeddable widget must stay standalone. It may only import the
  // widget-safe `src/lib/embed` contract — never dashboard components or other
  // app-level lib code — so the embed bundle has no dashboard dependencies.
  {
    files: ["src/widget/**/*.{ts,tsx}"],
    rules: {
      "boundaries/element-types": [
        "error",
        {
          default: "allow",
          rules: [
            {
              from: ["widget"],
              disallow: ["block", "ui", "shared", "lib", "providers", "types"],
              message:
                "The embeddable widget (src/widget) must stay standalone: it may not import dashboard app code from src/components/** or src/lib/** (only the widget-safe src/lib/embed contract is allowed).",
            },
          ],
        },
      ],
    },
  },
  // ERROR: shared layers are one-way. ui / shared / lib / providers / types may
  // not import from feature blocks or the widget — blocks depend on shared, never
  // the reverse.
  {
    files: [
      "src/components/ui/**/*.{ts,tsx}",
      "src/components/shared/**/*.{ts,tsx}",
      "src/lib/**/*.{ts,tsx}",
      "src/providers/**/*.{ts,tsx}",
      "src/types/**/*.{ts,tsx}",
    ],
    rules: {
      "boundaries/element-types": [
        "error",
        {
          default: "allow",
          rules: [
            {
              from: ["ui", "shared", "lib", "lib-embed", "providers", "types"],
              disallow: ["block", "widget"],
              message:
                "Shared layers (ui/shared/lib/providers/types) must not import from feature blocks (src/components/<block>) or the widget. Dependencies are one-way: blocks depend on shared, never the reverse.",
            },
          ],
        },
      ],
    },
  },
  // WARN: a feature block may import shared layers, itself, and any cross-block
  // edge declared in BLOCK_CROSS_DEPENDENCIES (seeded from registry.json). Any
  // other cross-block import is flagged as a warning (tracked in
  // docs/blocks/frontend-boundary-violations.md) so the build still passes while
  // the coupling is decoupled. Promote to "error" once a block is clean.
  {
    files: ["src/components/**/*.{ts,tsx}"],
    ignores: [
      "src/components/ui/**/*.{ts,tsx}",
      "src/components/shared/**/*.{ts,tsx}",
    ],
    rules: {
      "boundaries/element-types": [
        "warn",
        {
          default: "disallow",
          message:
            "Cross-block import: block '${file.block}' may not import block '${dependency.block}'. Route shared logic through ui/shared/lib, or declare the edge in eslint.config.mjs BLOCK_CROSS_DEPENDENCIES (seeded from docs/blocks/registry.json). TODO(decouple): tracked in docs/blocks/frontend-boundary-violations.md.",
          rules: [
            { from: ["block"], allow: SHARED_ELEMENT_TYPES },
            ...crossBlockAllowRules,
          ],
        },
      ],
    },
  },
  {
    settings: {
      // Help eslint-plugin-import resolve TS path aliases (e.g. "@/...").
      "import/resolver": {
        typescript: {
          alwaysTryTypes: true,
          project: "./tsconfig.json",
        },
        node: true,
      },
    },
    rules: {
      // Project rules

      "no-console": ["warn", { allow: ["warn", "error"] }],
      "@typescript-eslint/no-explicit-any": "error",
      "@next/next/no-img-element": "error",
      "@next/next/no-html-link-for-pages": "error",

      // The following react-hooks/react-compiler rules ship as errors in their
      // current versions but flag common, correct patterns (syncing media queries,
      // initializing form state from props, hooks that return non-memoizable
      // values). Downgraded to warnings so the signal stays visible in CI logs
      // without blocking builds. Re-tighten as patterns are migrated.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
      "react-hooks/incompatible-library": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/error-boundaries": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/immutability": "warn",
      "react-hooks/globals": "warn",
      "react-hooks/component-hook-factories": "warn",
      "react-hooks/unsupported-syntax": "warn",
      "react-hooks/use-memo": "warn",
      "react-hooks/config": "warn",

      // Drop unused imports automatically (autofixable).
      "unused-imports/no-unused-imports": "error",

      // Enforce a consistent, alphabetized import order grouped by origin.
      "import/order": [
        "error",
        {
          groups: [
            "builtin",
            "external",
            "internal",
            "parent",
            "sibling",
            "index",
          ],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true },
          pathGroups: [
            { pattern: "@/**", group: "internal", position: "before" },
          ],
          pathGroupsExcludedImportTypes: ["builtin"],
        },
      ],

      // Require an accessible label on interactive controls. Icon-only buttons
      // must supply `aria-label` (or wrap a labelled child like an <a aria-label>)
      // so screen readers can announce them.
      "jsx-a11y/control-has-associated-label": [
        "error",
        {
          labelAttributes: ["aria-label", "aria-labelledby", "title"],
          controlComponents: ["Button"],
          ignoreElements: [
            "audio",
            "canvas",
            "embed",
            "input",
            "textarea",
            "tr",
            "video",
          ],
          ignoreRoles: [
            "grid",
            "listbox",
            "menu",
            "menubar",
            "radiogroup",
            "row",
            "tablist",
            "toolbar",
            "tree",
            "treegrid",
          ],
          depth: 5,
        },
      ],
      // Forbid inline string-tuple React Query keys. All query keys must be
      // produced by `queryKeys.<resource>.<scope>(...)` from `@/lib/query-keys`
      // so that invalidation, prefetch, and cache reads share one source of truth.
      "no-restricted-syntax": [
        "error",
        {
          selector: "Property[key.name='queryKey'] > ArrayExpression",
          message:
            "Inline `queryKey: [...]` literals are not allowed. Use `queryKeys.<resource>.<scope>(...)` from '@/lib/query-keys' instead. Add a new builder there if needed.",
        },
        {
          selector:
            "ImportDeclaration[source.value='react'] > ImportNamespaceSpecifier",
          message:
            "Use named imports from 'react' (e.g. `import { useState, type ReactNode } from 'react'`) instead of `import * as React from 'react'`. React 19 + the new JSX transform make the namespace import unnecessary.",
        },
      ],
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "date-fns",
              message:
                "Import date helpers from '@/lib/utils/date' instead. The date.ts wrapper is the only file allowed to depend on date-fns directly.",
            },
          ],
          patterns: [
            {
              group: ["date-fns/*"],
              message:
                "Import date helpers from '@/lib/utils/date' instead of date-fns submodules.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/lib/utils/date.ts"],
    rules: {
      "no-restricted-imports": "off",
    },
  },
  {
    // The factory file itself is the canonical source of literal query keys.
    files: ["src/lib/query-keys.ts"],
    rules: {
      "no-restricted-syntax": "off",
    },
  },
  {
    // shadcn/ui primitives are vendored from upstream and follow shadcn's
    // `import * as React` convention. Keep them on the upstream style so future
    // `npx shadcn add` runs don't fight our lint rule.
    files: ["src/components/ui/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Property[key.name='queryKey'] > ArrayExpression",
          message:
            "Inline `queryKey: [...]` literals are not allowed. Use `queryKeys.<resource>.<scope>(...)` from '@/lib/query-keys' instead. Add a new builder there if needed.",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Auto-generated by `npm run codegen` from backend/openapi.json.
    "src/lib/api/_generated.ts",
  ]),
  // Must come last: disables ESLint rules that conflict with Prettier formatting.
  eslintConfigPrettier,
]);

export default eslintConfig;
