import { App, Modal, Notice, PluginSettingTab, Setting } from "obsidian";
import type PolarSyncPlugin from "./main";
import { DEFAULT_REDIRECT_URI, isLoopbackRedirect } from "./oauth";

export interface PolarSyncSettings {
  clientId: string;
  clientSecret: string;
  /** Must match the redirect URI registered for the client in Polar's admin. */
  redirectUri: string;
  /** Vault folder where daily Polar notes are created. */
  folder: string;
  /** How many past days (including today) a sync covers. Max 28 (AccessLink window). */
  syncDaysBack: number;
  syncOnStartup: boolean;
  /** Hours between automatic syncs while Obsidian is open; 0 disables. */
  autoSyncHours: number;

  // Filled in by the OAuth flow.
  accessToken: string;
  polarUserId: string;
  memberId: string;
  connectedAt: string;
}

export const DEFAULT_SETTINGS: PolarSyncSettings = {
  clientId: "",
  clientSecret: "",
  redirectUri: DEFAULT_REDIRECT_URI,
  folder: "Polar",
  syncDaysBack: 7,
  syncOnStartup: false,
  autoSyncHours: 6,
  accessToken: "",
  polarUserId: "",
  memberId: "",
  connectedAt: "",
};

export const MAX_SYNC_DAYS = 28;

export class PolarSettingTab extends PluginSettingTab {
  plugin: PolarSyncPlugin;

  constructor(app: App, plugin: PolarSyncPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    const s = this.plugin.settings;
    const save = () => this.plugin.saveSettings();

    new Setting(containerEl).setName("Polar AccessLink client").setHeading();

    const help = containerEl.createEl("p", { cls: "setting-item-description" });
    help.append(
      "Create a client at ",
      createLink("https://admin.polaraccesslink.com", "admin.polaraccesslink.com"),
      " and give it the redirect URI below (exactly). Then paste the client ID and secret here."
    );

    new Setting(containerEl)
      .setName("Client ID")
      .addText((text) =>
        text.setValue(s.clientId).onChange(async (value) => {
          s.clientId = value.trim();
          await save();
        })
      );

    new Setting(containerEl)
      .setName("Client secret")
      .addText((text) => {
        text.setValue(s.clientSecret).onChange(async (value) => {
          s.clientSecret = value.trim();
          await save();
        });
        text.inputEl.type = "password";
      });

    new Setting(containerEl)
      .setName("Redirect URI")
      .setDesc(
        "Registered with the client in Polar's admin. A localhost address lets the plugin catch the redirect itself; " +
          "anything else means pasting the code by hand."
      )
      .addText((text) =>
        text.setValue(s.redirectUri).onChange(async (value) => {
          s.redirectUri = value.trim() || DEFAULT_REDIRECT_URI;
          await save();
        })
      );

    // ---- Connection ----
    new Setting(containerEl).setName("Connection").setHeading();

    const connected = Boolean(s.accessToken);
    const status = new Setting(containerEl)
      .setName(connected ? "Connected" : "Not connected")
      .setDesc(
        connected
          ? `Polar user ${s.polarUserId}, connected ${s.connectedAt ? new Date(s.connectedAt).toLocaleString() : ""}.`
          : "Authorize this plugin with your Polar Flow account."
      );

    if (!connected) {
      status.addButton((btn) =>
        btn
          .setButtonText(isLoopbackRedirect(s.redirectUri) ? "Connect Polar account" : "Open Polar authorization")
          .setCta()
          .onClick(async () => {
            btn.setDisabled(true);
            try {
              await this.plugin.connect();
            } finally {
              this.display();
            }
          })
      );
      status.addButton((btn) =>
        btn.setButtonText("Paste authorization code…").onClick(() => {
          new PasteCodeModal(this.app, async (code) => {
            await this.plugin.finishConnect(code);
            this.display();
          }).open();
        })
      );
    } else {
      status.addButton((btn) =>
        btn
          .setButtonText("Sync now")
          .setCta()
          .onClick(() => void this.plugin.syncRecent())
      );
      status.addButton((btn) =>
        btn
          .setButtonText("Disconnect")
          .setWarning()
          .onClick(async () => {
            await this.plugin.disconnect();
            this.display();
          })
      );
    }

    // ---- Output ----
    new Setting(containerEl).setName("Notes").setHeading();

    new Setting(containerEl)
      .setName("Notes folder")
      .setDesc("Vault folder where one note per day is written.")
      .addText((text) =>
        text
          .setPlaceholder("Polar")
          .setValue(s.folder)
          .onChange(async (value) => {
            s.folder = value.trim().replace(/^\/+|\/+$/g, "") || "Polar";
            await save();
          })
      );

    new Setting(containerEl)
      .setName("Days to sync")
      .setDesc(`How many past days (including today) each sync covers. AccessLink keeps ${MAX_SYNC_DAYS} nights.`)
      .addText((text) =>
        text.setValue(String(s.syncDaysBack)).onChange(async (value) => {
          const n = parseInt(value, 10);
          if (Number.isFinite(n) && n >= 1 && n <= MAX_SYNC_DAYS) {
            s.syncDaysBack = n;
            await save();
          }
        })
      );

    new Setting(containerEl)
      .setName("Sync on startup")
      .setDesc("Sync recent days when Obsidian starts.")
      .addToggle((toggle) =>
        toggle.setValue(s.syncOnStartup).onChange(async (value) => {
          s.syncOnStartup = value;
          await save();
        })
      );

    new Setting(containerEl)
      .setName("Auto-sync interval (hours)")
      .setDesc("Sync again this often while Obsidian is open. 0 disables.")
      .addText((text) =>
        text.setValue(String(s.autoSyncHours)).onChange(async (value) => {
          const n = parseFloat(value);
          if (Number.isFinite(n) && n >= 0) {
            s.autoSyncHours = n;
            await save();
            this.plugin.rescheduleAutoSync();
          }
        })
      );
  }
}

function createLink(href: string, text: string): HTMLAnchorElement {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = text;
  return a;
}

class PasteCodeModal extends Modal {
  private onSubmit: (code: string) => Promise<void>;

  constructor(app: App, onSubmit: (code: string) => Promise<void>) {
    super(app);
    this.onSubmit = onSubmit;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.createEl("h3", { text: "Paste the Polar authorization code" });
    contentEl.createEl("p", {
      text:
        "After approving in the browser, Polar redirects to your redirect URI with ?code=… in the address bar. " +
        "Copy that value here.",
    });
    let code = "";
    new Setting(contentEl).setName("Code").addText((text) => {
      text.onChange((v) => (code = v.trim()));
      text.inputEl.style.width = "100%";
    });
    new Setting(contentEl).addButton((btn) =>
      btn
        .setButtonText("Connect")
        .setCta()
        .onClick(async () => {
          if (!code) {
            new Notice("Paste the code first.");
            return;
          }
          btn.setDisabled(true);
          try {
            await this.onSubmit(code);
            this.close();
          } catch (error) {
            new Notice(error instanceof Error ? error.message : String(error));
            btn.setDisabled(false);
          }
        })
    );
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
