import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      "no-console": ["error", { allow: ["warn", "error"] }],
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
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
