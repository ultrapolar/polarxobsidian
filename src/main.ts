import { App, Modal, Notice, Plugin, Setting, TFile, normalizePath } from "obsidian";
import {
  PolarApiError,
  deregisterUser,
  fetchExercises,
  fetchRecharges,
  fetchSleepNights,
  registerUser,
} from "./api";
import { isValidIsoDate, recentDates, toIsoDate } from "./dates";
import { mergeManagedSection, renderFrontmatter } from "./notes";
import {
  buildAuthorizeUrl,
  exchangeCode,
  isLoopbackRedirect,
  randomState,
  waitForCallback,
} from "./oauth";
import { groupByDate, hasAnyData, renderDay, type RenderedDay } from "./render";
import { DEFAULT_SETTINGS, MAX_SYNC_DAYS, PolarSettingTab, type PolarSyncSettings } from "./settings";

export default class PolarSyncPlugin extends Plugin {
  settings: PolarSyncSettings = DEFAULT_SETTINGS;
  private autoSyncTimer: number | null = null;
  private pendingState: string | null = null;
  private cancelCallbackWait: (() => void) | null = null;

  async onload() {
    await this.loadSettings();
    this.addSettingTab(new PolarSettingTab(this.app, this));

    this.addRibbonIcon("activity", "Sync Polar data", () => void this.syncRecent());

    this.addCommand({
      id: "sync-recent",
      name: "Sync recent days",
      callback: () => void this.syncRecent(),
    });
    this.addCommand({
      id: "sync-today",
      name: "Sync today",
      callback: () => void this.syncDates([toIsoDate(new Date())]),
    });
    this.addCommand({
      id: "sync-date",
      name: "Sync a specific date…",
      callback: () => new SyncDateModal(this.app, (date) => void this.syncDates([date])).open(),
    });
    this.addCommand({
      id: "connect",
      name: "Connect Polar account",
      callback: () => void this.connect(),
    });

    if (this.settings.syncOnStartup) {
      this.app.workspace.onLayoutReady(() => void this.syncRecent({ quiet: true }));
    }
    this.rescheduleAutoSync();
  }

  onunload() {
    this.cancelCallbackWait?.();
    if (this.autoSyncTimer !== null) window.clearInterval(this.autoSyncTimer);
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  rescheduleAutoSync() {
    if (this.autoSyncTimer !== null) {
      window.clearInterval(this.autoSyncTimer);
      this.autoSyncTimer = null;
    }
    const hours = this.settings.autoSyncHours;
    if (hours > 0) {
      this.autoSyncTimer = window.setInterval(
        () => void this.syncRecent({ quiet: true }),
        hours * 60 * 60 * 1000
      );
      this.registerInterval(this.autoSyncTimer);
    }
  }

  // ---- OAuth ----

  private checkClientConfigured(): boolean {
    if (!this.settings.clientId || !this.settings.clientSecret) {
      new Notice("Polar Sync: enter your AccessLink client ID and secret in the plugin settings first.");
      return false;
    }
    return true;
  }

  /**
   * Start the authorization flow. With a localhost redirect URI this completes
   * on its own; otherwise it opens the consent page and expects the code to be
   * pasted via "Paste authorization code…".
   */
  async connect(): Promise<void> {
    if (!this.checkClientConfigured()) return;
    this.cancelCallbackWait?.();

    const state = randomState();
    this.pendingState = state;
    const url = buildAuthorizeUrl(this.settings.clientId, this.settings.redirectUri, state);

    if (!isLoopbackRedirect(this.settings.redirectUri)) {
      window.open(url);
      new Notice("Polar Sync: approve in the browser, then use “Paste authorization code…” in settings.", 10000);
      return;
    }

    let waiter;
    try {
      waiter = waitForCallback(this.settings.redirectUri, state);
    } catch (error) {
      new Notice(error instanceof Error ? error.message : String(error));
      return;
    }
    this.cancelCallbackWait = waiter.cancel;
    window.open(url);
    new Notice("Polar Sync: approve the request in your browser…", 8000);

    try {
      const code = await waiter.promise;
      await this.finishConnect(code);
    } catch (error) {
      console.error("Polar Sync: connect failed", error);
      new Notice(error instanceof Error ? error.message : String(error), 10000);
    } finally {
      this.cancelCallbackWait = null;
    }
  }

  /** Exchange an authorization code, register with AccessLink, and persist the token. */
  async finishConnect(code: string): Promise<void> {
    if (!this.checkClientConfigured()) return;
    const token = await exchangeCode(
      this.settings.clientId,
      this.settings.clientSecret,
      code,
      this.settings.redirectUri
    );
    const userId = String(token.x_user_id);
    const memberId = this.settings.memberId || `obsidian-${userId}`;
    await registerUser(token.access_token, memberId);

    this.settings.accessToken = token.access_token;
    this.settings.polarUserId = userId;
    this.settings.memberId = memberId;
    this.settings.connectedAt = new Date().toISOString();
    this.pendingState = null;
    await this.saveSettings();
    new Notice(`Polar Sync: connected as Polar user ${userId}.`);
    void this.syncRecent({ quiet: true });
  }

  async disconnect(): Promise<void> {
    const { accessToken, polarUserId } = this.settings;
    if (accessToken && polarUserId) {
      try {
        await deregisterUser(accessToken, polarUserId);
      } catch (error) {
        console.warn("Polar Sync: deregister failed (token cleared locally anyway)", error);
      }
    }
    this.settings.accessToken = "";
    this.settings.polarUserId = "";
    this.settings.connectedAt = "";
    await this.saveSettings();
    new Notice("Polar Sync: disconnected.");
  }

  // ---- Sync ----

  private checkConnected(): boolean {
    if (!this.settings.accessToken) {
      new Notice("Polar Sync: connect your Polar account in the plugin settings first.");
      return false;
    }
    return true;
  }

  async syncRecent(options: { quiet?: boolean } = {}) {
    const days = Math.min(Math.max(1, this.settings.syncDaysBack), MAX_SYNC_DAYS);
    await this.syncDates(recentDates(days), options);
  }

  async syncDates(dates: string[], options: { quiet?: boolean } = {}) {
    if (!this.checkConnected()) return;
    const token = this.settings.accessToken;

    let days;
    try {
      // The three endpoints are windowed (28 nights / 30 days), not per-date,
      // so one round of requests covers every date being synced.
      const [nights, recharges, exercises] = await Promise.all([
        fetchSleepNights(token),
        fetchRecharges(token),
        fetchExercises(token),
      ]);
      days = groupByDate(dates, nights, recharges, exercises);
    } catch (error) {
      console.error("Polar Sync: fetch failed", error);
      const message =
        error instanceof PolarApiError
          ? error.message
          : "Polar Sync: could not reach the Polar API. See the developer console for details.";
      new Notice(message, 10000);
      return;
    }

    let written = 0;
    let empty = 0;
    for (const day of days) {
      if (!hasAnyData(day)) {
        empty++;
        continue;
      }
      try {
        await this.writeNote(day.date, renderDay(day));
        written++;
      } catch (error) {
        console.error(`Polar Sync: failed to write ${day.date}`, error);
        new Notice(`Polar Sync: failed to write the note for ${day.date}.`);
      }
    }

    if (!options.quiet) {
      new Notice(
        written === 0
          ? `Polar Sync: no Polar data for ${dates.length === 1 ? dates[0] : "those days"} yet.`
          : `Polar Sync: updated ${written} day(s)${empty ? `, ${empty} without data` : ""}.`
      );
    }
  }

  /**
   * Write a day's data to `<folder>/<date>.md`. New files get frontmatter plus
   * the managed section; existing files only have the managed section replaced
   * and their frontmatter keys updated, so notes around it are preserved.
   */
  private async writeNote(date: string, rendered: RenderedDay) {
    const folder = normalizePath(this.settings.folder || "Polar");
    const path = normalizePath(`${folder}/${date}.md`);

    if (!this.app.vault.getAbstractFileByPath(folder)) {
      await this.app.vault.createFolder(folder).catch(() => {
        /* may already exist; a real failure surfaces on write */
      });
    }

    const existing = this.app.vault.getAbstractFileByPath(path);
    if (existing instanceof TFile) {
      await this.app.vault.process(existing, (content) => mergeManagedSection(content, rendered.markdown));
      await this.app.fileManager.processFrontMatter(existing, (fm) => {
        for (const [key, value] of Object.entries(rendered.frontmatter)) {
          if (value === null) delete fm[key];
          else fm[key] = value;
        }
      });
      return;
    }

    const content = [renderFrontmatter(rendered.frontmatter), "", rendered.markdown, ""].join("\n");
    const file = await this.app.vault.create(path, content);
    if (!(file instanceof TFile)) throw new Error(`Could not create note at ${path}`);
  }
}

class SyncDateModal extends Modal {
  private onSubmit: (date: string) => void;

  constructor(app: App, onSubmit: (date: string) => void) {
    super(app);
    this.onSubmit = onSubmit;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.createEl("h3", { text: "Sync a specific date" });
    let value = toIsoDate(new Date());
    new Setting(contentEl).setName("Date (YYYY-MM-DD)").addText((text) => {
      text.setValue(value).onChange((v) => (value = v.trim()));
    });
    new Setting(contentEl).addButton((btn) =>
      btn
        .setButtonText("Sync")
        .setCta()
        .onClick(() => {
          if (!isValidIsoDate(value)) {
            new Notice("Enter a date as YYYY-MM-DD.");
            return;
          }
          this.close();
          this.onSubmit(value);
        })
    );
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
