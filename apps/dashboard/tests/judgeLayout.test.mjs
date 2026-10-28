import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const root = new URL("../src/", import.meta.url);
const view = readFileSync(new URL("JudgeDemoView.tsx", root), "utf8");
const css = readFileSync(new URL("judge.css", root), "utf8");
const required = [
  "judge-page", "judge-heading", "judge-offline", "judge-important",
  "judge-layout", "judge-scenario", "judge-walkthrough", "judge-muted",
  "judge-tabs", "judge-case", "judge-facts", "judge-section-title",
  "judge-stage-list", "judge-stage", "judge-stage-index", "judge-stage-name",
  "judge-stage-state", "judge-focus", "judge-focus-top", "judge-evidence",
  "judge-navigation", "judge-takeaway", "judge-explain", "judge-bottom",
];

test("each structural Judge Walkthrough class is used in JSX and styled in CSS", () => {
  for (const name of required) {
    assert.match(view, new RegExp("\\b" + name + "\\b"),
      "Missing JSX class " + name);
    assert.ok(css.includes("." + name), "Missing CSS selector " + name);
  }
});
test("responsive Judge and shared mobile navigation use explicit grid layouts", () => {
  assert.match(css, /\.judge-layout\s*\{\s*display:grid/);
  assert.match(css, /@media\(max-width:700px\)\s*\{\s*\.sidebar\s*\{display:grid/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});
