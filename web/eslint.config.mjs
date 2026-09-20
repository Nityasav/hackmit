import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // Vendored third-party components are kept byte-for-byte as published, so
    // their lint exceptions live here rather than as edits inside the files.
    files: ["src/components/ui/kanban.tsx", "src/components/ui/line-graph-statistics.tsx"],
    rules: {
      // KanbanOverlay measures the dragged node in an effect to size the ghost;
      // line-graph-statistics resets its animation phase the same way.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
