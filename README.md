# SpotiWoW-Raven

**Author: CloudNine_Ex**

A Spotify companion for Turtle WoW / RavenCraft clients based on 1.12.1 with SuperWoW. The project ships both French (FR) and US English add-on variants.

- French end-user readme: `README_FR.md`
- US English end-user readme: `README_EN_US.md`

## For players
Use the latest GitHub Release and download `SpotiWoW-Raven-Setup.exe`. The installer asks for the add-on language, game folder and Spotify Client ID, then downloads the matching release bundle.
/spn help for all commands.

## For maintainers
The shared Lua behavior is in `Interface/AddOns/SpotiWoW-Raven/SpotiWoW-Raven.lua`. French locale and metadata are in that add-on folder. US English locale and metadata are under `variants/US`. Publishing a GitHub Release triggers `.github/workflows/release.yml` to build the tray launcher, installer, and both language bundles.

## Compatibility and privacy
- Requires Turtle WoW / RavenCraft, SuperWoW file functions `ImportFile` and `ExportFile`, and `VanillaFixes.exe`.
- Does not distribute the game client or any third-party game DLLs.
- Each user supplies their own Spotify Client ID. Do not commit `config.json`, `tokens.json`, or `lyrics_cache.json`.
- The hotkey's Lyrics ON/OFF status is local-only (`DEFAULT_CHAT_FRAME:AddMessage`), not a chat message sent to other players.
