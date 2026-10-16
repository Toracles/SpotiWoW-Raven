# SpotiWoW-Raven v1.4.6 — US English

SpotiWoW-Raven connects Spotify to compatible WoW 1.12.1 client through the SuperWoW file bridge. This package uses the US English interface and in-game messages.

## Easy installation
1. Download `SpotiWoW-Raven-Setup.exe` from the **Releases** page of the official GitHub repository.
2. Close Turtle WoW before installing.
3. Select `English (US)` in the installer, choose the folder containing `VanillaFixes.exe`, and enter your Spotify Client ID.
4. In your Spotify Developer app settings, add the exact Redirect URI `http://127.0.0.1:8888/callback`.
5. Finish the setup and launch **SpotiWoW-Raven** from the shortcut.

The installer never asks for a Client Secret and does not download Turtle WoW, VanillaFixes, SuperWoW, SuperAPI, or their DLLs.

## Requirements
- compatible WoW 1.12.1 client client based on WoW 1.12.1.
- SuperWoW with the `ImportFile` and `ExportFile` functions.
- `VanillaFixes.exe` in the client folder.
- A Spotify Developer app configured with the Redirect URI shown above.

## Features
- `Ctrl+Alt+L` toggles Lyrics from the companion without typing a command into the in-game chat.
- `Lyrics mode: ON/OFF` is displayed locally via `DEFAULT_CHAT_FRAME:AddMessage`. The status message is never sent to other players.
- Mini player and Spotify controls.
- Multi-source search for timestamped lyrics and a local cache.
- Windows notification-area launcher with no visible CMD console.
- Automatically stops the bridge when the actual `WoW.exe` client process exits, including Alt+F4.

Lyrics themselves are still sent to the selected channel when that feature is enabled. Technical identifiers `SpotifyNowDB`, `SpotifyNowState.txt`, and `SpotifyNowCommand.txt` are retained for compatibility.

## Troubleshooting
- Logs: `logs/bridge.log` and `logs/launcher.log` in the companion app folder.
- If auto-detection fails, manually choose the folder that contains `VanillaFixes.exe`.

For an add-on-only update, download `SpotiWoW-Raven-Addon-US.zip` from Releases. The US English version displays system messages in English.
