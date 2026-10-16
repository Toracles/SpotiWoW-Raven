from __future__ import annotations

"""Windows setup wizard for SpotiWoW-Raven.

The installer downloads the latest public GitHub Release portable bundle, installs
only the addon/companion (never the Turtle WoW client or third-party DLLs), writes
config.json, and creates Start Menu/Desktop shortcuts.
"""

import hashlib
import locale
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "SpotiWoW-Raven"
PORTABLE_ASSET_NAMES = {"fr": "SpotiWoW-Raven-Portable-FR.zip", "us": "SpotiWoW-Raven-Portable-US.zip"}
VANILLAFIXES_NAME = "VanillaFixes.exe"
LAUNCHER_NAME = "SpotiWoW-Raven.exe"
ADDON_NAME = "SpotiWoW-Raven"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

DEFAULT_CONFIG = {
    "client_id": "",
    "game_dir": "",
    "language": "fr",
    "lyrics_offset_ms": 0,
    "lyrics_providers": ["Musixmatch", "Lrclib", "NetEase", "Megalobiz"],
    "lyrics_search_timeout_seconds": 18,
    "lyrics_cache_days": 90,
    "lyrics_negative_cache_hours": 6,
}


TEXT = {
    "fr": {
        "window_title": "SpotiWoW-Raven — Installation",
        "language_label": "Langue de l’addon / Add-on language",
        "intro": "Ferme Turtle WoW avant l’installation. L’assistant installe l’addon et le compagnon ; il ne télécharge pas le client WoW ni ses DLL.",
        "game_dir_label": "Dossier du client WoW (VanillaFixes.exe)",
        "browse": "Parcourir…",
        "detect_fail": "Détection automatique non concluante : sélectionne le dossier contenant VanillaFixes.exe.",
        "client_id_label": "Spotify Client ID",
        "client_id_help": "Dans Spotify Developer, crée une application et copie son Client ID. Ajoute le Redirect URI exact http://127.0.0.1:8888/callback. Ne saisis pas de Client Secret.",
        "shortcuts": "Créer un raccourci sur le bureau et dans le menu Démarrer",
        "ready": "Prêt à installer.",
        "install": "Installer",
        "cancel": "Annuler",
        "choose_dir": "Choisir le dossier du client WoW",
        "invalid_game": "Ce dossier ne semble pas contenir le client attendu.\n\nVanillaFixes.exe est introuvable dans :\n{path}",
        "invalid_id": "Le Client ID semble vide ou invalide. Copie le Client ID depuis ton application Spotify Developer.",
        "repo_missing": "Cet installateur n’est pas encore relié au dépôt GitHub du projet.\n\nLe mainteneur doit configurer le dépôt puis publier une Release.",
        "status_release": "Recherche de la dernière version publiée…",
        "status_download": "Téléchargement de {tag}…",
        "status_verify": "Vérification du paquet téléchargé…",
        "status_addon": "Installation de l’addon dans le client WoW…",
        "status_companion": "Installation du compagnon et configuration Spotify…",
        "status_shortcuts": "Création des raccourcis Windows…",
        "unsafe_zip": "Le paquet téléchargé contient un chemin ZIP non sûr.",
        "asset_missing": "La dernière Release ne contient pas {asset}. Vérifie que le workflow de publication a terminé.",
        "bad_hash": "La vérification SHA-256 a échoué. Aucun fichier n’a été installé.",
        "incomplete": "Le paquet est incomplet : addon, lanceur, bridge ou icône manquant.",
        "done_title": "Installation terminée",
        "done_message": "Installation terminée !\n\nAddon : {addon}\nCompagnon : {companion}\nLangue : {language}\n\nLance SpotiWoW-Raven depuis le raccourci. Le premier lancement peut ouvrir le navigateur pour autoriser Spotify.",
        "http_error": "GitHub a répondu HTTP {code}. Vérifie que le dépôt est public et qu’une Release est publiée.",
        "failed": "L’installation a échoué :\n\n{error}",
        "busy_close": "L’installation est en cours. Attends sa fin avant de fermer cette fenêtre.",
        "interrupted": "Installation interrompue.",
    },
    "us": {
        "window_title": "SpotiWoW-Raven — Setup",
        "language_label": "Add-on language / Langue de l’addon",
        "intro": "Close Turtle WoW before installing. Setup installs the add-on and companion; it does not download the WoW client or its DLLs.",
        "game_dir_label": "WoW client folder (VanillaFixes.exe)",
        "browse": "Browse…",
        "detect_fail": "Automatic detection did not find the client. Select the folder containing VanillaFixes.exe.",
        "client_id_label": "Spotify Client ID",
        "client_id_help": "Create an app in Spotify Developer and copy its Client ID. Add the exact Redirect URI http://127.0.0.1:8888/callback. Do not enter a Client Secret.",
        "shortcuts": "Create a desktop and Start Menu shortcut",
        "ready": "Ready to install.",
        "install": "Install",
        "cancel": "Cancel",
        "choose_dir": "Choose the WoW client folder",
        "invalid_game": "This folder does not appear to contain the expected client.\n\nVanillaFixes.exe was not found in:\n{path}",
        "invalid_id": "The Client ID looks empty or invalid. Copy the Client ID from your Spotify Developer app.",
        "repo_missing": "This setup has not been connected to the project's GitHub repository yet.\n\nThe maintainer must configure the repository and publish a Release.",
        "status_release": "Checking the latest published release…",
        "status_download": "Downloading {tag}…",
        "status_verify": "Verifying downloaded package…",
        "status_addon": "Installing the add-on into the WoW client…",
        "status_companion": "Installing the companion and configuring Spotify…",
        "status_shortcuts": "Creating Windows shortcuts…",
        "unsafe_zip": "The downloaded package contains an unsafe ZIP path.",
        "asset_missing": "The latest Release does not contain {asset}. Make sure the release workflow completed.",
        "bad_hash": "SHA-256 verification failed. No files were installed.",
        "incomplete": "The package is incomplete: add-on, launcher, bridge, or icon is missing.",
        "done_title": "Installation complete",
        "done_message": "Installation complete!\n\nAdd-on: {addon}\nCompanion: {companion}\nLanguage: {language}\n\nLaunch SpotiWoW-Raven from the shortcut. The first launch may open a browser to authorize Spotify.",
        "http_error": "GitHub returned HTTP {code}. Check that the repository is public and a Release has been published.",
        "failed": "Installation failed:\n\n{error}",
        "busy_close": "Installation is in progress. Wait for it to finish before closing this window.",
        "interrupted": "Installation interrupted.",
    },
}


def t(lang_code: str, key: str, **kwargs) -> str:
    """Translate a UI string; keep lang_code distinct from template placeholders.

    Some templates legitimately use a {language} placeholder, so the selector
    parameter must not itself be named `language`.
    """
    template = TEXT.get(lang_code, TEXT["fr"]).get(key, key)
    return template.format(**kwargs) if kwargs else template


def resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def read_repository_slug() -> str:
    for candidate in (resource_dir() / "repo.txt", Path(__file__).resolve().parent / "repo.txt"):
        try:
            value = candidate.read_text(encoding="utf-8").strip()
            if value and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
                return value
        except OSError:
            continue
    env_value = os.environ.get("SPOTIWOW_GITHUB_REPO", "").strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", env_value):
        return env_value
    return ""


def is_game_dir(path: Path) -> bool:
    return path.is_dir() and (path / VANILLAFIXES_NAME).is_file()


def game_candidates() -> list[Path]:
    raw = [
        r"C:\Jeux\World of Warcraft",
        r"C:\Jeux\TurtleWoW",
        r"C:\Games\World of Warcraft",
        r"C:\Games\Turtle WoW",
        r"C:\Games\TurtleWoW",
        r"C:\Turtle WoW",
        r"C:\TurtleWoW",
        str(Path.home() / "Games" / "World of Warcraft"),
        str(Path.home() / "Games" / "Turtle WoW"),
    ]
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_name)
        if base:
            raw += [str(Path(base) / "Turtle WoW"), str(Path(base) / "World of Warcraft")]
    result: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        path = Path(item).expanduser()
        key = os.path.normcase(str(path))
        if key not in seen and is_game_dir(path):
            result.append(path.resolve())
            seen.add(key)
    return result


def safe_extract(bundle: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(bundle, "r") as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError("Unsafe ZIP path in downloaded package / chemin ZIP non sûr dans le paquet téléchargé.") from exc
        archive.extractall(destination)


def powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def create_shortcut(shortcut_path: Path, target_path: Path, working_dir: Path, icon_path: Path) -> None:
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$s = $shell.CreateShortcut('{powershell_quote(str(shortcut_path))}'); "
        f"$s.TargetPath = '{powershell_quote(str(target_path))}'; "
        f"$s.WorkingDirectory = '{powershell_quote(str(working_dir))}'; "
        f"$s.IconLocation = '{powershell_quote(str(icon_path))}'; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=NO_WINDOW,
    )


class SetupApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        try:
            os_locale = locale.getlocale()[0] or ""
        except Exception:
            os_locale = ""
        self.language_code = "fr" if os_locale.casefold().startswith("fr") else "us"
        self.root.title(t(self.language_code, "window_title"))
        self.root.geometry("700x535")
        self.root.minsize(660, 500)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        icon = resource_dir() / "SpotiWoW-Raven.ico"
        if icon.is_file():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self.game_dir_var = tk.StringVar()
        detected = game_candidates()
        if detected:
            self.game_dir_var.set(str(detected[0]))
        self.client_id_var = tk.StringVar()
        self.language_var = tk.StringVar(value="Français (FR)" if self.language_code == "fr" else "English (US)")
        self.create_shortcut_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=t(self.language_code, "ready"))
        self.busy = False

        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="SpotiWoW-Raven", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        self.intro_label = ttk.Label(main, wraplength=650)
        self.intro_label.pack(anchor="w", pady=(4, 12))

        language_row = ttk.Frame(main)
        language_row.pack(fill="x", pady=(0, 10))
        self.language_label = ttk.Label(language_row)
        self.language_label.pack(side="left")
        self.language_combo = ttk.Combobox(
            language_row, textvariable=self.language_var, state="readonly",
            values=("Français (FR)", "English (US)"), width=18,
        )
        self.language_combo.pack(side="left", padx=(8, 0))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        self.game_dir_label = ttk.Label(main, font=("Segoe UI", 10, "bold"))
        self.game_dir_label.pack(anchor="w")
        path_row = ttk.Frame(main)
        path_row.pack(fill="x", pady=(5, 12))
        ttk.Entry(path_row, textvariable=self.game_dir_var).pack(side="left", fill="x", expand=True)
        self.browse_button = ttk.Button(path_row, command=self.browse)
        self.browse_button.pack(side="left", padx=(8, 0))
        self.detect_label = ttk.Label(main, wraplength=650)
        if not detected:
            self.detect_label.pack(anchor="w", pady=(0, 10))

        self.client_id_label = ttk.Label(main, font=("Segoe UI", 10, "bold"))
        self.client_id_label.pack(anchor="w")
        ttk.Entry(main, textvariable=self.client_id_var).pack(fill="x", pady=(5, 4))
        self.client_id_help = ttk.Label(main, wraplength=650, justify="left")
        self.client_id_help.pack(anchor="w", pady=(0, 12))

        self.shortcut_check = ttk.Checkbutton(main, variable=self.create_shortcut_var)
        self.shortcut_check.pack(anchor="w", pady=(0, 10))
        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 7))
        ttk.Label(main, textvariable=self.status_var, wraplength=650).pack(anchor="w")

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", side="bottom", pady=(16, 0))
        self.install_button = ttk.Button(buttons, command=self.install)
        self.install_button.pack(side="right")
        self.cancel_button = ttk.Button(buttons, command=self.close)
        self.cancel_button.pack(side="right", padx=(0, 8))
        self._apply_language()

    def _on_language_change(self, _event=None) -> None:
        self.language_code = "fr" if self.language_var.get().startswith("Français") else "us"
        self._apply_language()

    def _apply_language(self) -> None:
        lang = self.language_code
        self.root.title(t(lang, "window_title"))
        self.intro_label.configure(text=t(lang, "intro"))
        self.language_label.configure(text=t(lang, "language_label"))
        self.game_dir_label.configure(text=t(lang, "game_dir_label"))
        self.browse_button.configure(text=t(lang, "browse"))
        self.detect_label.configure(text=t(lang, "detect_fail"))
        self.client_id_label.configure(text=t(lang, "client_id_label"))
        self.client_id_help.configure(text=t(lang, "client_id_help"))
        self.shortcut_check.configure(text=t(lang, "shortcuts"))
        self.install_button.configure(text=t(lang, "install"))
        self.cancel_button.configure(text=t(lang, "cancel"))
        if not self.busy:
            self.status_var.set(t(lang, "ready"))

    def _t(self, key: str, **kwargs) -> str:
        return t(self.language_code, key, **kwargs)

    def browse(self) -> None:
        start = self.game_dir_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(parent=self.root, title=self._t("choose_dir"), initialdir=start)
        if selected:
            self.game_dir_var.set(selected)

    def set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def install(self) -> None:
        if self.busy:
            return
        game_dir = Path(self.game_dir_var.get().strip().strip('"')).expanduser()
        client_id = self.client_id_var.get().strip()
        if not is_game_dir(game_dir):
            messagebox.showerror(APP_NAME, self._t("invalid_game", path=game_dir), parent=self.root)
            return
        if len(client_id) < 10 or any(ch.isspace() for ch in client_id):
            messagebox.showerror(APP_NAME, self._t("invalid_id"), parent=self.root)
            return
        repo = read_repository_slug()
        if not repo:
            messagebox.showerror(
                APP_NAME,
                self._t("repo_missing"),
                parent=self.root,
            )
            return

        create_shortcuts = bool(self.create_shortcut_var.get())
        self.busy = True
        self.install_button.configure(state="disabled")
        self.language_combo.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.progress.start(12)
        language = self.language_code
        threading.Thread(
            target=self._install_worker,
            args=(repo, game_dir.resolve(), client_id, create_shortcuts, language),
            daemon=True,
        ).start()

    def _install_worker(self, repo: str, game_dir: Path, client_id: str, create_shortcuts: bool, language: str) -> None:
        asset_name = PORTABLE_ASSET_NAMES[language]
        language_label = "Français (FR)" if language == "fr" else "English (US)"
        try:
            self.set_status(t(language, "status_release"))
            request = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/releases/latest",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "SpotiWoW-Raven-Setup",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.loads(response.read().decode("utf-8"))
            asset = next((a for a in release.get("assets", []) if a.get("name") == asset_name), None)
            if not asset or not asset.get("browser_download_url"):
                raise RuntimeError(t(language, "asset_missing", asset=asset_name))

            with tempfile.TemporaryDirectory(prefix="spotiwow_setup_") as temp_name:
                temp = Path(temp_name)
                bundle = temp / asset_name
                self.set_status(t(language, "status_download", tag=release.get('tag_name', 'latest release')))
                download_request = urllib.request.Request(
                    asset["browser_download_url"],
                    headers={"User-Agent": "SpotiWoW-Raven-Setup", "Accept": "application/octet-stream"},
                )
                digest = hashlib.sha256()
                with urllib.request.urlopen(download_request, timeout=60) as response, bundle.open("wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        digest.update(chunk)
                remote_digest = str(asset.get("digest") or "")
                if remote_digest.startswith("sha256:") and digest.hexdigest().casefold() != remote_digest.split(":", 1)[1].casefold():
                    raise RuntimeError(t(language, "bad_hash"))

                self.set_status(t(language, "status_verify"))
                extracted = temp / "extracted"
                extracted.mkdir()
                safe_extract(bundle, extracted)
                addon_src = extracted / "Interface" / "AddOns" / ADDON_NAME
                companion_src = extracted / "companion"
                launcher_src = companion_src / LAUNCHER_NAME
                bridge_src = companion_src / "spotify_bridge.py"
                icon_src = companion_src / "SpotiWoW-Raven.ico"
                if not addon_src.is_dir() or not launcher_src.is_file() or not bridge_src.is_file() or not icon_src.is_file():
                    raise RuntimeError(t(language, "incomplete"))

                self.set_status(t(language, "status_addon"))
                addon_dest = game_dir / "Interface" / "AddOns" / ADDON_NAME
                addon_dest.parent.mkdir(parents=True, exist_ok=True)
                if addon_dest.exists():
                    shutil.rmtree(addon_dest)
                shutil.copytree(addon_src, addon_dest)
                (game_dir / "imports").mkdir(parents=True, exist_ok=True)

                app_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / APP_NAME
                app_root.mkdir(parents=True, exist_ok=True)
                self.set_status(t(language, "status_companion"))
                for src in companion_src.iterdir():
                    if src.is_file() and src.name not in {"config.json", "tokens.json", "lyrics_cache.json"}:
                        shutil.copy2(src, app_root / src.name)

                config_path = app_root / "config.json"
                config = dict(DEFAULT_CONFIG)
                legacy_companion = game_dir / "companion"
                legacy_config = legacy_companion / "config.json"
                if not config_path.is_file() and legacy_config.is_file():
                    try:
                        old = json.loads(legacy_config.read_text(encoding="utf-8"))
                        if isinstance(old, dict):
                            config.update(old)
                    except (OSError, ValueError):
                        pass
                if config_path.is_file():
                    try:
                        old = json.loads(config_path.read_text(encoding="utf-8"))
                        if isinstance(old, dict):
                            config.update(old)
                    except (OSError, ValueError):
                        pass
                # Preserve an older install's OAuth session/cache if the user is migrating
                # from <game_dir>\companion to the per-user application directory.
                for preserved in ("tokens.json", "lyrics_cache.json"):
                    target = app_root / preserved
                    source = legacy_companion / preserved
                    if not target.exists() and source.is_file():
                        shutil.copy2(source, target)
                config["client_id"] = client_id
                config["language"] = language
                config["game_dir"] = str(game_dir).replace("\\", "/")
                config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

                if create_shortcuts:
                    self.set_status(t(language, "status_shortcuts"))
                    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / f"{APP_NAME}.lnk"
                    start_menu = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk"
                    for shortcut in (desktop, start_menu):
                        try:
                            create_shortcut(shortcut, app_root / LAUNCHER_NAME, app_root, app_root / "SpotiWoW-Raven.ico")
                        except Exception:
                            # An unavailable/locked shortcut location shouldn't undo a valid install.
                            pass

                done_message = t(language, "done_message", addon=addon_dest, companion=app_root, language=language_label)
                self.root.after(0, lambda: self._finished(True, done_message, language))
        except urllib.error.HTTPError as exc:
            message = t(language, "http_error", code=exc.code)
            self.root.after(0, lambda: self._finished(False, message, language))
        except Exception as exc:
            message = t(language, "failed", error=f"{type(exc).__name__}: {exc}")
            self.root.after(0, lambda: self._finished(False, message, language))

    def _finished(self, success: bool, message: str, language: str) -> None:
        self.progress.stop()
        self.busy = False
        self.language_combo.configure(state="readonly")
        self.cancel_button.configure(state="normal")
        if success:
            self.status_var.set(t(language, "done_title"))
            messagebox.showinfo(t(language, "done_title"), message, parent=self.root)
            self.root.destroy()
        else:
            self.status_var.set(t(language, "interrupted"))
            self.install_button.configure(state="normal")
            messagebox.showerror(APP_NAME, message, parent=self.root)

    def close(self) -> None:
        if self.busy:
            messagebox.showinfo(APP_NAME, self._t("busy_close"), parent=self.root)
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    SetupApp().run()
