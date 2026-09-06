# Polar Sync for Obsidian

Sync your [Polar Flow](https://flow.polar.com) data — sleep, Nightly Recharge™ (resting HR, HRV, breathing rate, ANS charge) and exercises — into your Obsidian vault as one note per day, via the [Polar AccessLink API](https://www.polar.com/accesslink-api/).

## How it works

Each sync fetches the last 28 nights of sleep and Nightly Recharge and the last 30 days of exercises (the windows AccessLink keeps), then writes `<folder>/<YYYY-MM-DD>.md` for each requested day (default folder: `Polar`). Each note gets:

- **Frontmatter** with flat values (`polar_sleep_score`, `polar_sleep_min`, `polar_hrv_avg`, `polar_exercise_km`, …) for Dataview, Bases and charts.
- A **managed section** between `%% polar:start %%` and `%% polar:end %%` with readable sleep, recharge and exercise tables. Re-syncing replaces only that section; anything you write elsewhere in the note stays.

Days with no Polar data are skipped rather than written empty.

## Setup

1. **Create an AccessLink client** at [admin.polaraccesslink.com](https://admin.polaraccesslink.com) (log in with your Polar account). Set its **redirect URI** to exactly `http://localhost:8123/callback` (or whatever you enter in the plugin — they must match). Copy the client ID and secret.
2. Install the plugin (below) and enable it under **Settings → Community plugins**.
3. In **Settings → Polar Sync**, paste the **client ID** and **client secret**, check the redirect URI, and click **Connect Polar account**. Your browser opens Polar's consent page; approve it and the plugin catches the redirect, exchanges the code for a token and registers you with AccessLink.

   If your redirect URI is not on `localhost`, the plugin opens the consent page but cannot catch the redirect. After approving, copy the `code=` value from the address bar and use **Paste authorization code…** instead.
4. The first sync runs right after connecting. Use the ribbon icon or the commands after that.

Polar tokens are long-lived and have no refresh token, so this is a one-time step. If Polar ever rejects the token, **Disconnect** and connect again.

## Usage

| Command | What it does |
| --- | --- |
| `Polar Sync: Sync recent days` | Writes the last *N* days (setting, default 7, max 28) |
| `Polar Sync: Sync today` | Today only |
| `Polar Sync: Sync a specific date…` | Any day within AccessLink's window |
| `Polar Sync: Connect Polar account` | Starts the authorization flow |

**Sync on startup** and **Auto-sync interval** (default every 6 hours while Obsidian is open) are in the settings.

### Example Dataview query

```dataview
TABLE polar_sleep_score AS "Sleep", polar_hrv_avg AS "HRV", polar_hr_avg AS "RHR", polar_exercise_min AS "Exercise (min)"
FROM "Polar"
SORT file.name DESC
LIMIT 14
```

## Installing

### Manual install

1. Run a build (below) or download `main.js` and `manifest.json` from a release.
2. Copy `main.js` and `manifest.json` into `<your vault>/.obsidian/plugins/polar-sync/`.
3. Reload Obsidian and enable **Polar Sync** under Community plugins.

### Building from source

```bash
npm install
npm run build   # type-checks and produces main.js
npm run dev     # watch mode
npm test        # node tests for the rendering / grouping / date logic
```

## Notes & limitations

- **Desktop only.** Catching the OAuth redirect needs a local HTTP listener, which Obsidian mobile does not provide. Notes sync and read fine everywhere.
- **Windowed data.** AccessLink serves the last 28 nights and 30 days of exercises. Older days cannot be backfilled through this API.
- **Daily activity / steps are not synced.** AccessLink exposes them only through one-shot "transactions" that delete the data once read, which does not fit a re-runnable sync. Sleep, Nightly Recharge and exercises are all re-fetchable.
- **Field names are from Polar's documentation** and should match real payloads; if a value shows as `—` that you can see in Flow, open an issue with the raw response (`console.log` it from the developer console).
- The access token is stored in the plugin's `data.json` inside your vault; treat that file as sensitive. **Disconnect** removes the AccessLink registration and clears it.

## License

MIT
