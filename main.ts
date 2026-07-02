import { Plugin, Notice } from "obsidian";
import { fetchPolar, formatPolarDataMd } from "./lib";

// -- BEGIN CONFIG INTERFACE --
interface PolarConfig {
	clientId: string;
	clientSecret: string;
	accessToken?: string;
	userId?: string;
}

// This config should be replaced with a settings tab later for user entry
const DEFAULT_CONFIG: PolarConfig = {
	clientId: "YOUR_CLIENT_ID",
	clientSecret: "YOUR_CLIENT_SECRET",
};
// -- END CONFIG INTERFACE --

export default class PolarSyncPlugin extends Plugin {
	config: PolarConfig = DEFAULT_CONFIG;

	async onload() {
		this.addCommand({
			id: "polar-sync-manual",
			name: "Sync Polar AccessLink Data",
			callback: () => this.syncPolarData()
		});

		// Trigger once the vault has finished opening
		this.app.workspace.onLayoutReady(() => this.syncPolarData());

		// Daily sync (every 24h)
		this.registerInterval(window.setInterval(() => this.syncPolarData(), 1000 * 60 * 60 * 24));
	}

	async syncPolarData() {
		let rawData: Record<string, any> = {};

		if (!this.config.accessToken) {
			new Notice("Polar Access Token is missing. Connect your account.");
			return;
		}

		try {
			rawData['exercises'] = await fetchPolar("exercises", this.config.accessToken);
			rawData['sleep'] = await fetchPolar("users/sleep/", this.config.accessToken);
			rawData['recharge'] = await fetchPolar("users/nightly-recharge/", this.config.accessToken);
			rawData['user'] = await fetchPolar("users/" + this.config.userId, this.config.accessToken);

			const md = formatPolarDataMd(rawData);
			await this.app.vault.create(
				`PolarData_${new Date().toISOString()}.md`,
				md
			);

			new Notice("Polar data synced to vault!");
		} catch (e) {
			console.error(e);
			new Notice("Polar data sync failed.");
		}
	}
}
