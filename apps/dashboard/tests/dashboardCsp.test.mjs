import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// Baseline only: runtime Chrome CDP smoke proves the meta policy is active
// and separately checks external SDK logging calls are CSP-blocked.
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

test("dashboard disallows outbound SDK telemetry at the document boundary", () => {
  const meta = html.match(/<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"/);
  assert.ok(meta, "CSP must appear before the dashboard's client JS loads");
  const policy = meta[1];
  assert.match(policy, /connect-src 'self'/);
  assert.match(policy, /ws:\/\/127\.0\.0\.1:\*/);
  assert.match(policy, /ws:\/\/localhost:\*/);
  assert.match(policy, /form-action 'self'/);
  for (const broadEscape of ["https:", "http:", "data:", "blob:", "'unsafe-inline'"]) {
    assert.ok(!policy.includes(broadEscape),
      "CSP connect-src must not broadly authorize off-device egress");
  }
  // Port wildcards restricted to loopback hosts are acceptable. A bare
  // wildcard source would allow arbitrary outbound network connections.
  assert.equal(/(?:^|[\s;])\*(?:$|[\s;])/.test(policy), false);
  const cspPos = html.indexOf('http-equiv="Content-Security-Policy"');
  const scriptPos = html.indexOf('<script type="module"');
  assert.ok(cspPos >= 0 && scriptPos > cspPos);
});
