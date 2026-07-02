import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPolar, formatPolarDataMd } from "./lib";

describe("formatPolarDataMd", () => {
	it("renders only the header for an empty data object", () => {
		const md = formatPolarDataMd({});
		expect(md).toMatch(/^# Polar Data - .+\n$/);
		expect(md).not.toContain("##");
	});

	it("renders a section heading and fenced JSON block per key, in insertion order", () => {
		const md = formatPolarDataMd({
			exercises: [{ id: 1 }],
			sleep: { score: 80 },
		});

		const exercisesIdx = md.indexOf("## exercises");
		const sleepIdx = md.indexOf("## sleep");
		expect(exercisesIdx).toBeGreaterThan(-1);
		expect(sleepIdx).toBeGreaterThan(exercisesIdx);

		expect(md).toContain('## exercises\n\n```json\n[\n  {\n    "id": 1\n  }\n]\n```\n');
		expect(md).toContain('## sleep\n\n```json\n{\n  "score": 80\n}\n```\n');
	});

	it("pretty-prints nested objects with 2-space indentation", () => {
		const md = formatPolarDataMd({ user: { profile: { weight: 70 } } });
		expect(md).toContain('{\n  "profile": {\n    "weight": 70\n  }\n}');
	});

	it("renders null content as the literal null", () => {
		const md = formatPolarDataMd({ recharge: null });
		expect(md).toContain("## recharge\n\n```json\nnull\n```\n");
	});

	it("renders undefined content without breaking the fence structure", () => {
		// JSON.stringify(undefined) returns undefined, which stringifies as "undefined"
		// in the concatenation; documented here so a change in behavior is deliberate.
		const md = formatPolarDataMd({ user: undefined });
		expect(md).toContain("## user\n\n```json\nundefined\n```\n");
	});

	it("produces balanced code fences (one opening and one closing per section)", () => {
		const md = formatPolarDataMd({ a: 1, b: 2, c: 3 });
		const fences = md.match(/^```/gm) ?? [];
		expect(fences).toHaveLength(6);
	});
});

describe("fetchPolar", () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	function stubFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
		const mock = vi.fn().mockResolvedValue({
			ok: true,
			status: 200,
			statusText: "OK",
			json: async () => ({}),
			...response,
		});
		vi.stubGlobal("fetch", mock);
		return mock;
	}

	it("requests the endpoint under the AccessLink v3 base URL with auth headers", async () => {
		const mock = stubFetch({ json: async () => ({ data: [] }) });

		await fetchPolar("exercises", "my-token");

		expect(mock).toHaveBeenCalledOnce();
		const [url, init] = mock.mock.calls[0];
		expect(url).toBe("https://www.polaraccesslink.com/v3/exercises");
		expect(init.headers).toEqual({
			Authorization: "Bearer my-token",
			Accept: "application/json",
		});
	});

	it("returns the parsed JSON body on success", async () => {
		stubFetch({ json: async () => ({ "polar-user": "https://x" }) });

		await expect(fetchPolar("users/123", "t")).resolves.toEqual({
			"polar-user": "https://x",
		});
	});

	it("returns null on 204 No Content instead of parsing an empty body", async () => {
		const mock = stubFetch({
			status: 204,
			statusText: "No Content",
			json: async () => {
				throw new Error("no body to parse");
			},
		});

		await expect(fetchPolar("users/sleep/", "t")).resolves.toBeNull();
		expect(mock).toHaveBeenCalledOnce();
	});

	it("throws a descriptive error on 401 instead of parsing the error body", async () => {
		stubFetch({
			ok: false,
			status: 401,
			statusText: "Unauthorized",
			json: async () => ({ error: "invalid_token" }),
		});

		await expect(fetchPolar("exercises", "bad-token")).rejects.toThrow(
			'Polar AccessLink request to "exercises" failed: 401 Unauthorized'
		);
	});

	it("throws a descriptive error on 429 rate limiting", async () => {
		stubFetch({ ok: false, status: 429, statusText: "Too Many Requests" });

		await expect(fetchPolar("exercises", "t")).rejects.toThrow(
			'Polar AccessLink request to "exercises" failed: 429 Too Many Requests'
		);
	});

	it("propagates network failures from fetch", async () => {
		vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

		await expect(fetchPolar("exercises", "t")).rejects.toThrow("fetch failed");
	});
});
