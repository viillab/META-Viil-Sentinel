/**
 * Automated smoke of the actual React webcam page with Chromium's fake camera.
 * No personal camera, cloud, screenshots, video storage, or Playwright.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const cwd = fileURLToPath(new URL("../", import.meta.url));
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function chromeBinary() {
  const candidates = [
    process.env.VIIL_TEST_BROWSER,
    process.platform === "win32" && "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    process.platform === "win32" && "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    process.platform === "win32" && "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  ].filter(Boolean);
  const found = candidates.find(existsSync);
  if (!found) throw new Error("Chrome or Edge missing; set VIIL_TEST_BROWSER");
  return found;
}
async function freePort() {
  return new Promise((resolve, reject) => {
    const s = createServer();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const port = s.address().port;
      s.close(() => resolve(port));
    });
  });
}
async function until(check, label, timeout = 12_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try { const result = await check(); if (result) return result; }
    catch { /* Chrome startup / transient DOM delay */ }
    await wait(180);
  }
  throw new Error("Timed out: " + label);
}
async function connectCdp(url) {
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let sequence = 0;
  const promises = new Map();
  const networkMethods = [];
  ws.addEventListener("message", e => {
    const event = JSON.parse(String(e.data));
    if (event.method === "Network.requestWillBeSent")
      networkMethods.push(event.params.request.method);
    if (event.id === undefined) return;
    const callback = promises.get(event.id);
    if (!callback) return;
    promises.delete(event.id);
    event.error ? callback.reject(new Error(event.error.message)) : callback.resolve(event.result);
  });
  return {
    networkMethods,
    send(method, params = {}) {
      const id = ++sequence;
      const response = new Promise((resolve, reject) => promises.set(id, { resolve, reject }));
      ws.send(JSON.stringify({ id, method, params }));
      return response;
    },
    close() { ws.close(); },
  };
}

async function main() {
  const executable = chromeBinary();
  const vitePort = await freePort();
  const cdpPort = await freePort();
  const profile = await mkdtemp(join(tmpdir(), "viil-fake-webcam-"));
  let vite, chrome, cdp;
  try {
    vite = spawn(process.execPath, [
      join(cwd, "node_modules", "vite", "bin", "vite.js"),
      "--host", "127.0.0.1", "--port", String(vitePort), "--strictPort",
    ], { cwd, stdio: "ignore", windowsHide: true });
    const url = "http://127.0.0.1:" + vitePort + "/";
    await until(async () => {
      const r = await fetch(url, { signal: AbortSignal.timeout(700) });
      return r.ok;
    }, "local Vite server");
    chrome = spawn(executable, [
      "--headless=new", "--no-first-run", "--no-default-browser-check",
      "--disable-extensions", "--disable-background-networking",
      // The page's getUserMedia is replaced with canvas.captureStream before Start.
      // No browser device permission is preapproved and no real device is used.
      ...(process.env.CI === "true" && process.platform !== "win32"
        ? ["--no-sandbox", "--disable-dev-shm-usage"] : []),
      "--remote-allow-origins=*",
      "--remote-debugging-address=127.0.0.1",
      "--remote-debugging-port=" + cdpPort, "--user-data-dir=" + profile, url,
    ], { cwd, stdio: "ignore", windowsHide: true });
    const page = await until(async () => {
      const response = await fetch("http://127.0.0.1:" + cdpPort + "/json/list",
        { signal: AbortSignal.timeout(700) });
      const targets = await response.json();
      return targets.find(t => t.type === "page" && t.url.startsWith(url));
    }, "isolated Chromium test page");
    cdp = await connectCdp(page.webSocketDebuggerUrl);
    await cdp.send("Runtime.enable");
    await cdp.send("Network.enable");
    async function evaluate(expression) {
      const reply = await cdp.send("Runtime.evaluate", {
        expression, awaitPromise: true, returnByValue: true,
      });
      if (reply.exceptionDetails) throw new Error("Unexpected browser script exception");
      return reply.result.value;
    }
    function clickButton(name) {
      const code = "(() => { const b = [...document.querySelectorAll('button')]" +
        ".find(e => e.textContent.includes(" + JSON.stringify(name) + "));" +
        "if (!b || b.disabled) return false; b.click(); return true; })()";
      return evaluate(code);
    }
    assert.equal(await until(() => clickButton("Integration center"), "navigation"), true);
    await until(() => evaluate(
      "document.querySelector('[aria-label=\"Laptop webcam demo\"]') !== null"
    ), "React webcam view");
    // Replace only this isolated test page's getUserMedia with a moving
    // synthetic canvas stream. The real camera permission is never requested.
    await evaluate("(() => { window.__viilFakeTrace=[];" +
      "navigator.mediaDevices.getUserMedia=async (constraints)=> {" +
      "if (constraints.audio !== false) throw Error('audio forbidden');" +
      "const c=document.createElement('canvas');c.width=640;c.height=360;" +
      "const ctx=c.getContext('2d');let count=0;" +
      "const draw=()=>{count++;ctx.fillStyle=count%2?'#123456':'#654321';" +
      "ctx.fillRect(0,0,640,360);ctx.fillStyle='#ffffff';" +
      "ctx.fillRect((count*19)%600,45,40,40);};draw();" +
      "window.__viilFakeRenderTimer=setInterval(draw,65);" +
      "const s=c.captureStream(15);window.__viilFakeTrack=s.getVideoTracks()[0];" +
      "window.__viilFakeTrace.push('canvas-stream-granted');" +
      "for(const t of s.getTracks()) {const original=t.stop.bind(t);" +
      "t.stop=()=>{window.__viilFakeTrace.push('track-stop-call');return original();};" +
      "t.addEventListener('ended',()=>window.__viilFakeTrace.push('track-ended'));}" +
      "return s;};return true;})()");
    assert.equal(await clickButton("Start laptop webcam demo"), true);
    let lastSnapshot = null;
    const snapshot = await until(async () => {
      const state = await evaluate("(() => {" +
        "const s = document.querySelector('.laptop-webcam-status')?.innerText || '';" +
        "const v = document.querySelector('[aria-label=\"Laptop webcam demo\"] video');" +
        "const frames = [...document.querySelectorAll('.laptop-pose-feedback span')]" +
          ".find(e => e.textContent.includes('Preview frame callbacks observed:'));" +
        "const n = Number(frames?.textContent.match(/(\\d+)\\s*$/)?.[1] || 0);" +
        "const root=document.querySelector('[aria-label=\"Laptop webcam demo\"]');" +
        "const warning=[...root.querySelectorAll('[role=\"alert\"],[role=\"status\"]')].map(x=>x.innerText?.slice(0,140)).filter(Boolean).slice(-4);" +
        "return { count:n, status:s, live:v?.srcObject?.getVideoTracks()?.[0]?.readyState, warning," +
        "visibility:document.visibilityState, trace:window.__viilFakeTrace };" +
      "})()");
      lastSnapshot = state;
      return state?.count >= 15 && state?.live === "live" ? state : null;
    }, "fresh fake video frame count", 16_000).catch(error => {
      throw new Error(error.message + " (synthetic browser state: " +
        JSON.stringify(lastSnapshot) + ")");
    });
    assert.match(snapshot.status, /FRESH FRAMES OBSERVED/);
    assert.equal(await clickButton("Stop webcam"), true);
    const result = await until(async () => {
      const data = await evaluate("(() => {" +
        "const v=document.querySelector('[aria-label=\"Laptop webcam demo\"] video');" +
        "return { released: v?.srcObject === null," +
        "trackEnded: window.__viilFakeTrack?.readyState === 'ended'," +
        "report:document.querySelector('[aria-label=\"Local webcam technical smoke report\"]')?.innerText || '' };" +
      "})()");
      return data?.released && data?.trackEnded && data.report.includes("manual") ? data : null;
    }, "released stream and local operator report");
    assert.match(result.report, /OPERATOR REVIEW REQUIRED/);
    assert.match(result.report, /Locally analyzed:\s*0/);
    assert.ok((await evaluate("window.__viilFakeTrace.filter(e=>e==='track-stop-call').length")) >= 1,
      "Local StreamTrack.stop() must be called during manual shutdown");
    await evaluate("clearInterval(window.__viilFakeRenderTimer)");

    // A second capture in the same mounted React component checks restart
    // after Stop, and verifies browser visibility revocation fails closed.
    assert.equal(await clickButton("Start laptop webcam demo"), true);
    await until(() => evaluate("(() => { const v=document.querySelector(" +
      "'[aria-label=\"Laptop webcam demo\"] video');" +
      "return v?.srcObject?.getVideoTracks()?.[0]?.readyState === 'live'" +
      " && document.querySelector('.laptop-webcam-status')?.innerText" +
      ".includes('FRESH FRAMES OBSERVED'); })()"), "restarted fake camera");
    await evaluate("(() => {" +
      "Object.defineProperty(document,'visibilityState'," +
      "{configurable:true,get:()=> 'hidden'});" +
      "document.dispatchEvent(new Event('visibilitychange'));" +
      "delete document.visibilityState;return true;})()");
    const hidden = await until(() => evaluate("(() => {" +
      "const v=document.querySelector('[aria-label=\"Laptop webcam demo\"] video');" +
      "const report=document.querySelector('[aria-label=\"Local webcam technical smoke report\"]');" +
      "return v?.srcObject===null && window.__viilFakeTrack?.readyState==='ended'" +
      " && report?.innerText.includes('hidden');})()"), "visibility cleanup");
    assert.equal(hidden, true);
    await evaluate("clearInterval(window.__viilFakeRenderTimer)");

    // Stop drawing but keep the synthetic MediaStream track live. The
    // existing watchdog must halt a frozen preview without human action.
    assert.equal(await clickButton("Start laptop webcam demo"), true);
    await until(() => evaluate("(() => {const v=document.querySelector(" +
      "'[aria-label=\"Laptop webcam demo\"] video');" +
      "return v?.srcObject?.getVideoTracks()?.[0]?.readyState==='live'" +
      " && document.querySelector('.laptop-webcam-status')?.innerText" +
      ".includes('FRESH FRAMES OBSERVED');})()"), "third synthetic session");
    await evaluate("clearInterval(window.__viilFakeRenderTimer)");
    const stall = await until(() => evaluate("(() => {" +
      "const v=document.querySelector('[aria-label=\"Laptop webcam demo\"] video');" +
      "const report=document.querySelector('[aria-label=\"Local webcam technical smoke report\"]');" +
      "return v?.srcObject===null && window.__viilFakeTrack?.readyState==='ended'" +
      " && report?.innerText.includes('frame stalled');})()"),
      "frozen synthetic frame fail-closed", 11_000);
    assert.equal(stall, true);

    // A permission prompt resolving after the user clicks Stop must never
    // reopen a preview or leak the late synthetic MediaStream.
    await evaluate("(() => {" +
      "const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);" +
      "window.__viilPermissionResolve=null;" +
      "navigator.mediaDevices.getUserMedia=()=> new Promise(resolve=>{" +
      "window.__viilPermissionResolve=()=>resolve(original({audio:false}));" +
      "});return true;})()");
    assert.equal(await clickButton("Start laptop webcam demo"), true);
    await until(() => evaluate("typeof window.__viilPermissionResolve==='function'"),
      "pending synthetic permission");
    assert.equal(await clickButton("Stop webcam"), true);
    assert.equal(await evaluate("window.__viilPermissionResolve();true"), true);
    const late = await until(() => evaluate("(() => {" +
      "const v=document.querySelector('[aria-label=\"Laptop webcam demo\"] video');" +
      "return window.__viilFakeTrack?.readyState==='ended' && v?.srcObject===null;})()"),
      "late camera permission cleanup");
    assert.equal(late, true);
    await evaluate("clearInterval(window.__viilFakeRenderTimer)");

    // Browser permission denial must show a redacted status, never native
    // error details (paths, camera labels) or any kind of retry.
    await evaluate("(() => {" +
      "navigator.mediaDevices.getUserMedia=async ()=> {" +
      "throw new DOMException('private device information', 'NotAllowedError');" +
      "};return true;})()");
    assert.equal(await clickButton("Start laptop webcam demo"), true);
    const denied = await until(() => evaluate("(() => {" +
      "const root=document.querySelector('[aria-label=\"Laptop webcam demo\"]');" +
      "return root.querySelector('[role=\"alert\"]')?.innerText || '';})()"),
      "denied synthetic permission");
    assert.match(denied, /permission denied/i);
    assert.doesNotMatch(denied, /private device information/i);

    assert.equal(cdp.networkMethods.filter(m => !["GET", "OPTIONS"].includes(m)).length,
      0, "Browser must not upload frames or POST demo incidents");
    console.log("FAKE WEBCAM BROWSER PASS: rendered=" + snapshot.count +
      "; manual/hidden/stall/late-permission cleanup=verified; " +
      "permission-denied=redacted; local report=shown; " +
      "inference=none; POST=0; real hardware=NOT tested");
  } finally {
    cdp?.close();
    chrome?.kill();
    vite?.kill();
    await wait(500);
    try { await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 250 }); }
    catch { /* Chrome sometimes releases test-only profile files slowly */ }
  }
}
await main();
