#!/usr/bin/env node
/**
 * Static accessibility analyzer for React JSX/TSX (SERVICE_MVP.md 5.1).
 *
 * Usage:
 *   node analyze.mjs --type jsx|tsx [--components '{"Button":"button"}'] < Component.jsx
 *
 * Reads code from stdin and writes one AnalyzerResult JSON object to stdout:
 *   { parse_ok, parse_error, findings: [StaticFinding], analyzer_versions }
 *
 * Exit codes: 0 = analysis ran (even with parse errors or findings),
 *             2 = bad arguments or internal error (message on stderr).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import tsParser from "@typescript-eslint/parser";
import { ESLint } from "eslint";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";

const HERE = dirname(fileURLToPath(import.meta.url));

// Rule prefix -> tool name reported in StaticFinding.tool.
// jsx-a11y: accessibility rules (diagnosis + revalidation).
// react-hooks: functional-regression guard for generated code (revalidation only).
const TOOLS = { "jsx-a11y/": "eslint-jsx-a11y", "react-hooks/": "eslint-react-hooks" };

function toolFor(ruleId) {
  const prefix = Object.keys(TOOLS).find((p) => ruleId?.startsWith(p));
  return prefix ? TOOLS[prefix] : null;
}

function fail(message) {
  process.stderr.write(`analyze.mjs: ${message}\n`);
  process.exit(2);
}

function parseArgs(argv) {
  const args = { type: null, components: {} };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--type") {
      args.type = value;
      i++;
    } else if (key === "--components") {
      try {
        args.components = JSON.parse(value ?? "{}");
      } catch {
        fail("--components must be a JSON object");
      }
      i++;
    } else {
      fail(`unknown argument: ${key}`);
    }
  }
  if (args.type !== "jsx" && args.type !== "tsx") fail("--type must be 'jsx' or 'tsx'");
  if (typeof args.components !== "object" || Array.isArray(args.components)) {
    fail("--components must be a JSON object");
  }
  return args;
}

function packageVersion(name) {
  try {
    const pkg = JSON.parse(readFileSync(join(HERE, "node_modules", name, "package.json"), "utf8"));
    return pkg.version;
  } catch {
    return "unknown";
  }
}

function buildConfig(type, components) {
  return [
    {
      files: ["**/*.jsx", "**/*.tsx"],
      plugins: { "jsx-a11y": jsxA11y, "react-hooks": reactHooks },
      languageOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ...(type === "tsx" ? { parser: tsParser } : {}),
        parserOptions: { ecmaFeatures: { jsx: true } },
      },
      settings: { "jsx-a11y": { components } },
      rules: {
        ...jsxA11y.flatConfigs.recommended.rules,
        // only the Rules of Hooks; exhaustive-deps is a noisy warning and stays off
        "react-hooks/rules-of-hooks": "error",
      },
    },
  ];
}

/**
 * Find the JSX element name for a message at (line, column), both 1-based.
 * Most jsx-a11y rules report on the opening element, so the position usually
 * points at "<tag". Otherwise (e.g. reported on an attribute) fall back to the
 * nearest preceding JSX tag. A tag must not follow an identifier character, so
 * TypeScript generics like `useState<boolean>` are not mistaken for elements.
 */
function elementAt(code, line, column) {
  if (!line) return null;
  const lines = code.split("\n");
  let offset = 0;
  for (let i = 0; i < line - 1 && i < lines.length; i++) offset += lines[i].length + 1;
  offset += Math.max(0, (column ?? 1) - 1);

  const here = /^<([A-Za-z][\w.]*)/.exec(code.slice(offset));
  if (here) return here[1];

  const before = code.slice(0, offset);
  const matches = [...before.matchAll(/(?:^|[^\w$.])<([A-Za-z][\w.]*)/g)];
  return matches.length ? matches[matches.length - 1][1] : null;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

async function main() {
  const { type, components } = parseArgs(process.argv.slice(2));
  const code = await readStdin();

  const eslint = new ESLint({
    cwd: HERE,
    overrideConfigFile: true,
    overrideConfig: buildConfig(type, components),
  });
  const [result] = await eslint.lintText(code, { filePath: join(HERE, `input.${type}`) });

  const fatal = result.messages.find((m) => m.fatal);
  const findings = fatal
    ? []
    : result.messages
        .filter((m) => toolFor(m.ruleId))
        .map((m) => ({
          tool: toolFor(m.ruleId),
          rule_id: m.ruleId,
          message: m.message,
          line: m.line ?? null,
          column: m.column ?? null,
          element: m.ruleId.startsWith("jsx-a11y/") ? elementAt(code, m.line, m.column) : null,
          wcag_refs: [],
        }));

  const output = {
    parse_ok: !fatal,
    parse_error: fatal ? `${fatal.message} (${fatal.line}:${fatal.column})` : null,
    findings,
    analyzer_versions: {
      node: process.versions.node,
      eslint: ESLint.version,
      "eslint-plugin-jsx-a11y": packageVersion("eslint-plugin-jsx-a11y"),
      "eslint-plugin-react-hooks": packageVersion("eslint-plugin-react-hooks"),
      "@typescript-eslint/parser": packageVersion("@typescript-eslint/parser"),
    },
  };
  process.stdout.write(JSON.stringify(output));
}

main().catch((err) => fail(err?.stack ?? String(err)));
