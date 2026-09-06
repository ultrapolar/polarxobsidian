// Polar OAuth2 authorization-code flow.
//
// Polar issues long-lived access tokens (no refresh token), so the flow runs
// once: open the Polar consent page, catch the redirect on a loopback HTTP
// server, exchange the code with HTTP Basic client credentials, then register
// the user with AccessLink. When the redirect URI is not on localhost the code
// can be pasted in by hand instead.
import * as http from "http";
import { requestUrl } from "obsidian";

export const AUTHORIZE_URL = "https://flow.polar.com/oauth2/authorization";
export const TOKEN_URL = "https://polarremote.com/v2/oauth2/token";
export const SCOPE = "accesslink.read_all";
export const DEFAULT_REDIRECT_URI = "http://localhost:8123/callback";

export interface TokenResponse {
  access_token: string;
  token_type?: string;
  expires_in?: number;
  x_user_id: number | string;
}

export function randomState(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function buildAuthorizeUrl(clientId: string, redirectUri: string, state: string): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: SCOPE,
    state,
  });
  return `${AUTHORIZE_URL}?${params.toString()}`;
}

function basicAuth(clientId: string, clientSecret: string): string {
  const raw = `${clientId}:${clientSecret}`;
  const b64 = typeof btoa === "function" ? btoa(raw) : Buffer.from(raw, "utf8").toString("base64");
  return `Basic ${b64}`;
}

export async function exchangeCode(
  clientId: string,
  clientSecret: string,
  code: string,
  redirectUri: string
): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
  }).toString();

  const response = await requestUrl({
    url: TOKEN_URL,
    method: "POST",
    headers: {
      Authorization: basicAuth(clientId, clientSecret),
      "Content-Type": "application/x-www-form-urlencoded",
      Accept: "application/json;charset=UTF-8",
    },
    body,
    throw: false,
  });

  let json: Partial<TokenResponse> & { error?: string; error_description?: string } = {};
  try {
    json = response.json;
  } catch {
    /* handled below */
  }
  if (response.status >= 400 || !json.access_token) {
    const reason = json.error_description || json.error || `HTTP ${response.status}`;
    throw new Error(`Polar token exchange failed: ${reason}`);
  }
  if (json.x_user_id == null) {
    throw new Error("Polar token response had no x_user_id.");
  }
  return json as TokenResponse;
}

/** True if the redirect URI points at this machine, so we can listen for it. */
export function isLoopbackRedirect(redirectUri: string): boolean {
  try {
    const url = new URL(redirectUri);
    return (
      url.protocol === "http:" &&
      (url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "[::1]")
    );
  } catch {
    return false;
  }
}

const RESPONSE_PAGE = (title: string, body: string) => `<!doctype html>
<html><head><meta charset="utf-8"><title>${title}</title>
<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;color:#222}</style>
</head><body><h1>${title}</h1><p>${body}</p></body></html>`;

/**
 * Listen once on the redirect URI's port for Polar's callback and resolve with
 * the authorization code. Rejects on state mismatch, provider error, or timeout.
 */
export function waitForCallback(
  redirectUri: string,
  expectedState: string,
  timeoutMs = 5 * 60 * 1000
): { promise: Promise<string>; cancel: () => void } {
  const target = new URL(redirectUri);
  const port = Number(target.port || 80);
  let server: http.Server | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const cleanup = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (server) {
      server.close();
      server = null;
    }
  };

  const promise = new Promise<string>((resolve, reject) => {
    server = http.createServer((req, res) => {
      const url = new URL(req.url ?? "/", `http://${target.hostname}`);
      if (url.pathname !== target.pathname) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("not found");
        return;
      }
      const error = url.searchParams.get("error");
      const code = url.searchParams.get("code");
      const state = url.searchParams.get("state");

      if (error) {
        res.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
        res.end(RESPONSE_PAGE("Polar authorization failed", `Polar returned: <code>${error}</code>. You can close this tab.`));
        cleanup();
        reject(new Error(`Polar denied authorization: ${error}`));
        return;
      }
      if (!code || state !== expectedState) {
        res.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
        res.end(RESPONSE_PAGE("Invalid callback", "Missing code or state mismatch. Start the connection again from Obsidian."));
        cleanup();
        reject(new Error("Polar callback had a missing code or a state mismatch."));
        return;
      }
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(RESPONSE_PAGE("Polar connected", "You can close this tab and return to Obsidian."));
      cleanup();
      resolve(code);
    });

    server.on("error", (err) => {
      cleanup();
      reject(new Error(`Could not listen on ${target.host} for the Polar redirect: ${err.message}`));
    });

    server.listen(port, target.hostname === "localhost" ? "127.0.0.1" : target.hostname);

    timer = setTimeout(() => {
      cleanup();
      reject(new Error("Timed out waiting for Polar to redirect back. Start the connection again."));
    }, timeoutMs);
  });

  return { promise, cancel: cleanup };
}
