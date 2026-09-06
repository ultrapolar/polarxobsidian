// Thin AccessLink v3 client on top of Obsidian's requestUrl (no CORS issues).
import { requestUrl } from "obsidian";
import type { PolarExercise, PolarRecharge, PolarSleepNight } from "./render";

export const API_BASE = "https://www.polaraccesslink.com/v3";

export class PolarApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "PolarApiError";
    this.status = status;
  }

  get needsReconnect(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

async function get<T>(token: string, path: string): Promise<T | null> {
  const response = await requestUrl({
    url: `${API_BASE}${path}`,
    method: "GET",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    throw: false,
  });

  if (response.status === 204 || response.status === 404) return null; // nothing for that range/date
  if (response.status === 401 || response.status === 403) {
    throw new PolarApiError(
      "Polar rejected the access token. Reconnect your Polar account in the plugin settings.",
      response.status
    );
  }
  if (response.status === 429) {
    throw new PolarApiError("Polar AccessLink rate limit hit; try again in a few minutes.", 429);
  }
  if (response.status >= 400) {
    let detail = "";
    try {
      detail = response.text?.slice(0, 200) ?? "";
    } catch {
      /* ignore */
    }
    throw new PolarApiError(`Polar API error ${response.status}${detail ? `: ${detail}` : ""}`, response.status);
  }

  try {
    return response.json as T;
  } catch {
    throw new PolarApiError("Polar API returned a non-JSON body.", response.status);
  }
}

/** Last 28 nights (AccessLink's window). */
export async function fetchSleepNights(token: string): Promise<PolarSleepNight[]> {
  const body = await get<{ nights?: PolarSleepNight[] }>(token, "/users/sleep");
  return body?.nights ?? [];
}

/** Last 28 nights of Nightly Recharge. */
export async function fetchRecharges(token: string): Promise<PolarRecharge[]> {
  const body = await get<{ recharges?: PolarRecharge[] }>(token, "/users/nightly-recharge");
  return body?.recharges ?? [];
}

/** Exercises from the last 30 days (no samples/zones: keeps the payload small). */
export async function fetchExercises(token: string): Promise<PolarExercise[]> {
  const body = await get<PolarExercise[]>(token, "/exercises?samples=false&zones=false&route=false");
  return Array.isArray(body) ? body : [];
}

export interface PolarUserInfo {
  "polar-user-id"?: number;
  "member-id"?: string;
  "registration-date"?: string;
  "first-name"?: string;
  "last-name"?: string;
}

export async function fetchUserInfo(token: string, userId: string): Promise<PolarUserInfo | null> {
  return get<PolarUserInfo>(token, `/users/${encodeURIComponent(userId)}`);
}

/**
 * Register the token's user with AccessLink. Required exactly once per token;
 * 409 means already registered, which is fine.
 */
export async function registerUser(token: string, memberId: string): Promise<void> {
  const response = await requestUrl({
    url: `${API_BASE}/users`,
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ "member-id": memberId }),
    throw: false,
  });
  if (response.status === 409 || (response.status >= 200 && response.status < 300)) return;
  throw new PolarApiError(`Could not register with AccessLink (HTTP ${response.status}).`, response.status);
}

/** Remove the registration so the token stops granting access. Best effort. */
export async function deregisterUser(token: string, userId: string): Promise<void> {
  await requestUrl({
    url: `${API_BASE}/users/${encodeURIComponent(userId)}`,
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
    throw: false,
  });
}
