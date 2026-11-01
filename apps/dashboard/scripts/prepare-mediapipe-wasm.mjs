// Copy MediaPipe's npm-provided WASM assets to a same-origin, gitignored
// Vite public path. No external CDN or downloaded model is ever embedded.
import { copyFile, mkdir, stat } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const source = resolve(root, "node_modules/@mediapipe/tasks-vision/wasm");
const target = resolve(root, "public/vendor/mediapipe/wasm");
const required = [
  "vision_wasm_internal.js", "vision_wasm_internal.wasm",
  "vision_wasm_nosimd_internal.js", "vision_wasm_nosimd_internal.wasm",
];
await mkdir(target, { recursive: true });
for (const name of required) {
  const sourcePath = resolve(source, name);
  const size = (await stat(sourcePath)).size;
  if (size < 1000 || size > 32 * 1024 * 1024) {
    throw new Error("Unexpected installed MediaPipe WASM asset size");
  }
  await copyFile(sourcePath, resolve(target, name));
}
console.log("Prepared bundled local MediaPipe WASM assets (no CDN; no pose model).");
