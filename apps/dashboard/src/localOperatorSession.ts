/** Local-only operator login, never the Hikvision camera password.
 * The HttpOnly cookie cannot be read from JavaScript. No local storage,
 * URL token, console logging, retry loop or credential persistence. */
export async function loginLocalOperator(password: string): Promise<void> {
  if (!password || password.length > 256) {
    throw new Error("Enter the separate local operator password");
  }
  const res = await fetch("/api/v1/operator/login", {
    method: "POST", credentials: "same-origin", mode: "same-origin",
    cache: "no-store", redirect: "error",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    throw new Error(res.status === 401 || res.status === 429
      ? "Local operator sign-in denied"
      : "Local operator bridge is not available");
  }
  // Never parse or store session credentials in browser memory.
}

export async function logoutLocalOperator(): Promise<void> {
  try {
    await fetch("/api/v1/operator/logout", {
      method: "POST", credentials: "same-origin", mode: "same-origin",
      cache: "no-store", redirect: "error",
    });
  } catch {
    // UI always drops signed-in metadata regardless of network outcome.
  }
}
