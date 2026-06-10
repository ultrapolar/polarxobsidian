import { Plugin, Notice } from "obsidian";

interface PolarConfig {
	clientId: string;
	clientSecret: string;
	accessToken?: string;
	userId?: string;
}

// Replace with a settings tab later for user entry
const DEFAULT_CONFIG: PolarConfig = {
	clientId: "YOUR_CLIENT_ID",
	clientSecret: "YOUR_CLIENT_SECRET",
};

const SYNC_INTERVAL_MS = 24 * 60 * 60 * 1000;

export default class PolarSyncPlugin extends Plugin {
	config: PolarConfig = DEFAULT_CONFIG;

	async onload() {
		this.addCommand({
			id: "polar-sync-manual",
			name: "Sync Polar AccessLink Data",
			callback: () => this.syncPolarData(),
		});

		// Sync once on startup, then every 24h
		this.app.workspace.onLayoutReady(() => this.syncPolarData());
		this.registerInterval(window.setInterval(() => this.syncPolarData(), SYNC_INTERVAL_MS));
	}

	async syncPolarData() {
		const { accessToken, userId } = this.config;
		if (!accessToken) {
			new Notice("Polar Access Token is missing. Connect your account.");
			return;
		}

		const endpoints: Record<string, string> = {
			exercises: "exercises",
			sleep: "users/sleep/",
			recharge: "users/nightly-recharge/",
			user: `users/${userId}`,
		};

		try {
			const entries = await Promise.all(
				Object.entries(endpoints).map(
					async ([section, endpoint]) => [section, await fetchPolar(endpoint, accessToken)] as const
				)
			);

			// ISO timestamps contain colons, which are invalid in filenames on most platforms
			const stamp = new Date().toISOString().replace(/[:.]/g, "-");
			await this.app.vault.create(`PolarData_${stamp}.md`, formatPolarDataMd(Object.fromEntries(entries)));

			new Notice("Polar data synced to vault!");
		} catch (e) {
			console.error(e);
			new Notice("Polar data sync failed.");
		}
	}
}

// Basic data fetch (add OAuth2 handling for full implementation!)
async function fetchPolar(endpoint: string, token: string) {
	const resp = await fetch(`https://www.polaraccesslink.com/v3/${endpoint}`, {
		headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
	});
	if (!resp.ok) throw new Error(`Polar API ${endpoint} responded ${resp.status}`);
	return resp.json();
}

function formatPolarDataMd(data: Record<string, unknown>): string {
	const sections = Object.entries(data).map(
		([section, content]) => `## ${section}\n\n\`\`\`json\n${JSON.stringify(content, null, 2)}\n\`\`\`\n`
	);
	return [`# Polar Data - ${new Date().toLocaleString()}`, ...sections].join("\n");
}
