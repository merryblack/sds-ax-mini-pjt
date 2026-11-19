// T05: analyzer contract tests. Run with `npm test` (node:test, no extra deps).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), "analyze.mjs");

function analyze(code, args) {
  const r = spawnSync(process.execPath, [SCRIPT, ...args], { input: code, encoding: "utf8" });
  return { status: r.status, out: r.stdout ? JSON.parse(r.stdout) : null, err: r.stderr };
}

const ruleIds = (out) => out.findings.map((f) => f.rule_id).sort();

test("Scenario A: clickable div is reported with element name", () => {
  const code = 'export default function SaveButton() {\n  return <div onClick={() => alert("saved")}>저장</div>;\n}\n';
  const { status, out } = analyze(code, ["--type", "jsx"]);
  assert.equal(status, 0);
  assert.equal(out.parse_ok, true);
  assert.deepEqual(ruleIds(out), [
    "jsx-a11y/click-events-have-key-events",
    "jsx-a11y/no-static-element-interactions",
  ]);
  for (const f of out.findings) {
    assert.equal(f.tool, "eslint-jsx-a11y");
    assert.equal(f.element, "div");
    assert.equal(f.line, 2);
    assert.deepEqual(f.wcag_refs, []);
  }
});

test("clean button has no findings", () => {
  const { out } = analyze('export const B = () => <button type="button" onClick={() => 1}>저장</button>;', ["--type", "jsx"]);
  assert.equal(out.parse_ok, true);
  assert.equal(out.findings.length, 0);
});

test("TSX parses with the TS parser and generics are not elements", () => {
  const code = 'interface P { label: string }\nexport function B({ label }: P) {\n  const [x] = useState<boolean>(false);\n  return <img src="a.png" />;\n}\n';
  const { out } = analyze(code, ["--type", "tsx"]);
  assert.equal(out.parse_ok, true);
  assert.deepEqual(ruleIds(out), ["jsx-a11y/alt-text"]);
  assert.equal(out.findings[0].element, "img");
});

test("TSX code analyzed as jsx is a parse failure", () => {
  const { status, out } = analyze("interface P { a: string }\nexport const C = (p: P) => <p />;", ["--type", "jsx"]);
  assert.equal(status, 0);
  assert.equal(out.parse_ok, false);
  assert.match(out.parse_error, /\(\d+:\d+\)$/);
  assert.equal(out.findings.length, 0);
});

test("broken code is a parse failure, not a crash", () => {
  const { status, out } = analyze("export function A() { return <div onClick=>; }", ["--type", "jsx"]);
  assert.equal(status, 0);
  assert.equal(out.parse_ok, false);
});

test("component mapping makes custom components behave like native elements", () => {
  const code = "export const D = () => <div><Link>x</Link></div>;";
  const without = analyze(code, ["--type", "jsx"]).out;
  const withMap = analyze(code, ["--type", "jsx", "--components", '{"Link":"a"}']).out;
  assert.equal(without.findings.length, 0);
  assert.deepEqual(ruleIds(withMap), ["jsx-a11y/anchor-is-valid"]);
  assert.equal(withMap.findings[0].element, "Link");
});

test("Rules of Hooks violations are reported with their own tool name", () => {
  const code = 'import { useEffect } from "react";\nexport function D({ open }) {\n  if (!open) return null;\n  useEffect(() => {}, []);\n  return <p />;\n}\n';
  const { out } = analyze(code, ["--type", "jsx"]);
  assert.deepEqual(ruleIds(out), ["react-hooks/rules-of-hooks"]);
  assert.equal(out.findings[0].tool, "eslint-react-hooks");
  assert.equal(out.findings[0].line, 4);
  assert.equal(out.findings[0].element, null);
});

test("hooks at the top level are fine", () => {
  const code = 'import { useEffect } from "react";\nexport function D({ open }) {\n  useEffect(() => { if (!open) return; }, [open]);\n  if (!open) return null;\n  return <p />;\n}\n';
  assert.equal(analyze(code, ["--type", "jsx"]).out.findings.length, 0);
});

test("analyzer versions are reported", () => {
  const { out } = analyze("export const E = () => <p />;", ["--type", "jsx"]);
  for (const key of ["node", "eslint", "eslint-plugin-jsx-a11y", "eslint-plugin-react-hooks", "@typescript-eslint/parser"]) {
    assert.ok(out.analyzer_versions[key] && out.analyzer_versions[key] !== "unknown", key);
  }
});

test("bad arguments exit with code 2", () => {
  assert.equal(analyze("x", ["--type", "html"]).status, 2);
  assert.equal(analyze("x", ["--type", "jsx", "--components", "not-json"]).status, 2);
});
