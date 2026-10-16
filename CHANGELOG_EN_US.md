## 1.4.6
- The bridge checks Spotify every 10 seconds to refresh track metadata.
- Long track titles scroll in the add-on interface so the full title can be read.

## 1.4.5
- When the WoW client closes, the bridge stops and SpotiWoW-Raven also exits the system tray automatically.
- Added a log entry for this automatic shutdown.

# Changelog

## v1.4.4
- Removed the three retired root-level maintainer guides and their obsolete README links. `.gitignore` now prevents them from being reintroduced accidentally.
- Retains the v1.4.3 fix that monitors the actual `WoW.exe` process to stop the bridge after Alt+F4.

## v1.4.3
- Fixed automatic bridge shutdown by monitoring the actual `WoW.exe` client instead of every executable in the game folder. This prevents a leftover helper process from keeping the bridge running after Alt+F4.
- Added diagnostic logging for the tracked client PID and session closure.


## v1.4.2
- Fixed the setup installer crash when formatting the completion message: the language selector no longer conflicts with the template’s `{language}` placeholder.

## v1.4.1
- Fixed the GitHub Actions release workflow by passing absolute icon and script paths to PyInstaller, preventing it from looking for the icon under `build/launcher`.
- Updated GitHub Actions to Node.js 24-compatible major versions to address the Node.js 20 deprecation warning.

## v1.4.0
- Added full French (FR) and US English add-on variants.
- Official add-on author: CloudNine_Ex.
- Localized local system messages, help, tooltips, and now-playing announcements.
- Ctrl+Alt+L still works without typing a command into the in-game chat. ON/OFF status is shown only in the local chat frame.
- The installer lets users choose a language and downloads the matching package.
- Technical identifiers and existing SavedVariables are retained for compatibility.
