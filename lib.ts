// Pure/support functions for the Polar Sync plugin, kept free of any
// Obsidian imports so they can be unit-tested in a plain Node environment.

const POLAR_API_BASE = "https://www.polaraccesslink.com/v3";

// Very basic data fetch function (add OAuth2 handling for full implementation!)
export async function fetchPolar(endpoint: string, token: string): Promise<unknown> {
	const url = `${POLAR_API_BASE}/${endpoint}`;
	const resp = await fetch(url, {
		headers: {
			Authorization: `Bearer ${token}`,
			Accept: "application/json",
		},
	});
	if (resp.status === 204) {
		// Polar AccessLink returns 204 No Content when there is no data.
		return null;
	}
	if (!resp.ok) {
		throw new Error(
			`Polar AccessLink request to "${endpoint}" failed: ${resp.status} ${resp.statusText}`
		);
	}
	return resp.json();
}

// Markdown formatter for the fetched data
export function formatPolarDataMd(data: Record<string, unknown>): string {
	let md = `# Polar Data - ${new Date().toLocaleString()}\n`;
	for (const [section, content] of Object.entries(data)) {
		md += `## ${section}\n\n`;
		md += "```json\n" + JSON.stringify(content, null, 2) + "\n```\n";
	}
	return md;
}
