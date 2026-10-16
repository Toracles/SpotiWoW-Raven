from __future__ import annotations

import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import uuid
from ctypes import wintypes

import psutil
import pystray
from PIL import Image

APP_NAME = "SpotiWoW-Raven"
DEFAULT_GAME_DIR = Path(r"C:\Jeux\World of Warcraft")
VANILLAFIXES_NAME = "VanillaFixes.exe"
# VanillaFixes is a launcher/injector. The actual Turtle WoW client it starts is WoW.exe.
# Watching every executable in the game directory can accidentally track helpers that
# stay alive after the player presses Alt+F4, leaving the bridge running indefinitely.
GAME_CLIENT_EXE_NAMES = {"wow.exe"}
BRIDGE_NAME = "spotify_bridge.py"
CONFIG_NAME = "config.json"
LOG_DIR_NAME = "logs"
MUTEX_NAME = r"Local\SpotiWoW-Raven-Launcher"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
ERROR_ALREADY_EXISTS = 183
MB_OK = 0x0
MB_ICONERROR = 0x10
MB_ICONWARNING = 0x30
MB_ICONINFORMATION = 0x40


def app_dir() -> Path:
    # In a frozen build sys.executable is the launcher EXE itself. In source mode,
    # this is the directory containing this .py file.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_dir()
BRIDGE_SCRIPT = ROOT / BRIDGE_NAME
CONFIG_FILE = ROOT / CONFIG_NAME
ICON_FILE = ROOT / "SpotiWoW-Raven.ico"


def configured_language() -> str:
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        value = str(cfg.get("language", "fr")).strip().casefold()
        return "us" if value in {"us", "en", "en-us", "english"} else "fr"
    except (OSError, ValueError, TypeError):
        return "fr"


LANGUAGE = configured_language()


def tr(fr: str, us: str) -> str:
    return us if LANGUAGE == "us" else fr


def configured_game_dir() -> Path:
    """Resolve the selected WoW folder from config, with a portable fallback."""
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        configured = str(cfg.get("game_dir", "")).strip()
        if configured:
            return Path(configured).expanduser().resolve()
    except (OSError, ValueError, TypeError):
        pass

    # Portable installs commonly keep companion/ directly under the game root.
    adjacent_game = ROOT.parent
    if (adjacent_game / VANILLAFIXES_NAME).is_file():
        return adjacent_game.resolve()
    return DEFAULT_GAME_DIR


GAME_DIR = configured_game_dir()


def message_box(message: str, title: str = APP_NAME, flags: int = MB_OK | MB_ICONERROR) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    except Exception:
        pass


def acquire_single_instance_mutex():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        return None, False
    already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    return handle, not already_running


def validate_installation() -> tuple[Path, Path]:
    if not GAME_DIR.is_dir():
        raise RuntimeError(f"{tr('Le dossier du jeu indiqué dans config.json est introuvable :', 'The game folder configured in config.json was not found:')}\n{GAME_DIR}\n\n{tr('Relance l’installateur SpotiWoW-Raven pour choisir le dossier du client.', 'Run the SpotiWoW-Raven setup again to select your client folder.')}")
    vanilla_fixes = GAME_DIR / VANILLAFIXES_NAME
    if not vanilla_fixes.is_file():
        raise RuntimeError(f"{tr('VanillaFixes.exe est introuvable :', 'VanillaFixes.exe was not found:')}\n{vanilla_fixes}")
    if not BRIDGE_SCRIPT.is_file():
        raise RuntimeError(f"{BRIDGE_NAME} {tr('est introuvable :', 'was not found:')}\n{BRIDGE_SCRIPT}\n\n{tr('Place le lanceur dans le dossier companion, à côté du bridge.', 'Keep the launcher in the companion folder, next to the bridge.')}")
    if not CONFIG_FILE.is_file():
        example = ROOT / "config.example.json"
        hint = f"\n{tr(f'Copie {example.name} en {CONFIG_NAME}, puis renseigne ton Client ID Spotify.', f'Copy {example.name} to {CONFIG_NAME}, then enter your Spotify Client ID.')}"
        raise RuntimeError(f"{CONFIG_NAME} {tr('est introuvable :', 'was not found:')}\n{CONFIG_FILE}{hint}")
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{tr(f'Impossible de lire {CONFIG_NAME} :', f'Could not read {CONFIG_NAME}:')} {exc}") from exc
    client_id = str(cfg.get("client_id", "")).strip()
    if not client_id or client_id.upper().startswith(("COLLE_ICI", "YOUR_", "REPLACE_")):
        raise RuntimeError(f"{tr('Renseigne ton Client ID Spotify dans :', 'Enter your Spotify Client ID in:')}\n{CONFIG_FILE}")
    configured_dir = str(cfg.get("game_dir", str(GAME_DIR))).replace("/", "\\").rstrip("\\")
    expected_dir = str(GAME_DIR).replace("/", "\\").rstrip("\\")
    if os.path.normcase(configured_dir) != os.path.normcase(expected_dir):
        # The bridge config is authoritative; stop if it points at another client,
        # because otherwise WoW and the file bridge could silently use different folders.
        raise RuntimeError(
            f"{tr(f'Le game_dir de {CONFIG_NAME} ne correspond pas au dossier du lanceur.', f'The game_dir in {CONFIG_NAME} does not match the launcher folder.')}\n\n"
            f"config.json: {configured_dir}\nLauncher: {expected_dir}\n\n"
            f"{tr('Aligne ces deux chemins avant de démarrer.', 'Make these paths match before starting.')}"
        )
    return vanilla_fixes, GAME_DIR


def process_is_inside_game(exe: str | None) -> bool:
    """Return True only for the actual WoW client process.

    VanillaFixes.exe is a bootstrapper/injector, while helper executables in the
    same folder may stay alive after the game closes. Monitoring just WoW.exe
    makes Alt+F4 and normal exit reliably end the session watcher.
    """
    if not exe:
        return False
    try:
        # The launcher invokes VanillaFixes.exe without custom-executable arguments,
        # so VanillaFixes starts the standard WoW.exe in GAME_DIR.
        if Path(exe).name.casefold() not in GAME_CLIENT_EXE_NAMES:
            return False
        root = os.path.normcase(os.path.abspath(str(GAME_DIR))).rstrip("\\/")
        path = os.path.normcase(os.path.abspath(exe))
        return path.startswith(root + os.sep)
    except (OSError, ValueError):
        return False


def game_process_snapshot():
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
        try:
            info = proc.info
            if process_is_inside_game(info.get("exe")):
                found.append({
                    "pid": int(info["pid"]),
                    "name": str(info.get("name") or Path(info["exe"]).name),
                    "exe": str(info["exe"]),
                    "create_time": info.get("create_time") or 0,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            continue
    return sorted(found, key=lambda row: row["create_time"])


class SpotiWoWController:
    def __init__(self):
        self.icon = None
        self.bridge_process: subprocess.Popen | None = None
        self.stop_flag: Path | None = None
        self.bridge_log_handle = None
        self._bridge_lock = threading.RLock()
        self._quitting = threading.Event()
        self._session_thread = None
        self._log_dir = ROOT / LOG_DIR_NAME

        try:
            with Image.open(ICON_FILE) as source:
                source.seek(0)
                self._tray_image = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        except Exception as exc:
            raise RuntimeError(f"{tr('Impossible de charger l’icône :', 'Could not load the icon:')}\n{ICON_FILE}\n\n{exc}") from exc

        # Use plain closure callbacks for pystray menu actions. This avoids passing
        # bound-method objects directly to the native tray backend, which some
        # frozen Windows builds have mishandled during menu initialization.
        self.icon = pystray.Icon(
            APP_NAME,
            self._tray_image,
            title=f"{APP_NAME} — {tr('démarrage…', 'starting…')}",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda item: self._status_label(),
                    lambda icon, item: None,
                    enabled=False,
                ),
                pystray.MenuItem(
                    tr("Démarrer le bridge", "Start bridge"),
                    self._make_menu_callback(tr("Démarrer le bridge", "Start bridge"), lambda: self.start_bridge()),
                    visible=lambda item: not self.bridge_is_running(),
                ),
                pystray.MenuItem(
                    tr("Arrêter le bridge", "Stop bridge"),
                    self._make_menu_callback(tr("Arrêter le bridge", "Stop bridge"), lambda: self.stop_bridge(show_notification=True)),
                    enabled=lambda item: self.bridge_is_running(),
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    tr("Quitter", "Quit"),
                    self._make_menu_callback(tr("Quitter", "Quit"), lambda: self.quit()),
                ),
            ),
        )

    def _write_session_log(self, message: str) -> None:
        """Write session-monitor events to the launcher log for troubleshooting."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            with (self._log_dir / "launcher.log").open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except OSError:
            pass

    def _write_error_log(self, label: str, exc: BaseException) -> Path | None:
        """Write detailed errors to disk because the frozen app has no console."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self._log_dir / "launcher.log"
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {label}\n")
                stream.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                stream.write("\n")
            return log_path
        except Exception:
            return None

    def _make_menu_callback(self, label: str, callback):
        """Adapt an operation to pystray's (icon, item) callback signature."""
        def on_click(icon, item):
            try:
                callback()
            except Exception as exc:
                log_path = self._write_error_log(f"Menu action failed: {label}", exc)
                suffix = f" {tr('Consulte', 'See')} {log_path}." if log_path else f" {tr('Consulte le journal du lanceur.', 'See the launcher log.')}"
                self.notify(f"{tr(f'L’action « {label} » a échoué.', f'{label} failed.')}{suffix}")
                self._refresh_tray()
        return on_click

    def _status_label(self) -> str:
        if self.bridge_is_running():
            return f"{APP_NAME} — {tr('Bridge actif', 'Bridge running')}"
        return f"{APP_NAME} — {tr('Bridge arrêté', 'Bridge stopped')}"

    def bridge_is_running(self) -> bool:
        with self._bridge_lock:
            return self.bridge_process is not None and self.bridge_process.poll() is None

    def _refresh_tray(self):
        if self.icon is None:
            return
        try:
            self.icon.title = self._status_label()
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, message: str, title: str = APP_NAME):
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
                return
            except Exception:
                pass
        # Notifications can be unavailable until the icon has been initialized.
        if self._quitting.is_set():
            return

    def start_bridge(self, icon=None, item=None):
        with self._bridge_lock:
            if self.bridge_process is not None and self.bridge_process.poll() is None:
                self.notify(tr("Le bridge est déjà actif.", "The bridge is already running."))
                return
            if not BRIDGE_SCRIPT.is_file() or not CONFIG_FILE.is_file():
                self.notify(tr("Impossible de démarrer le bridge : vérifie spotify_bridge.py et config.json.", "Could not start the bridge: check spotify_bridge.py and config.json."))
                return

            self._log_dir.mkdir(parents=True, exist_ok=True)
            stop_flag = self._log_dir / f"stop_{os.getpid()}_{uuid.uuid4().hex}.flag"
            try:
                stop_flag.unlink()
            except FileNotFoundError:
                pass

            env = os.environ.copy()
            env["SPOTIWOW_STOP_FLAG"] = str(stop_flag)
            env["PYTHONUNBUFFERED"] = "1"
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--bridge-child"]
            else:
                command = [sys.executable, str(Path(__file__).resolve()), "--bridge-child"]

            log_path = self._log_dir / "bridge.log"
            log_handle = None
            try:
                log_handle = open(log_path, "ab", buffering=0)
                self.bridge_process = subprocess.Popen(
                    command,
                    cwd=str(ROOT),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=CREATE_NO_WINDOW,
                    close_fds=True,
                )
                # The child owns a duplicate handle to the log; close the parent copy.
                log_handle.close()
                self.bridge_log_handle = None
                self.stop_flag = stop_flag
            except Exception as exc:
                try:
                    if log_handle is not None:
                        log_handle.close()
                except Exception:
                    pass
                self.bridge_process = None
                self.stop_flag = None
                self.notify(f"{tr('Échec du démarrage du bridge :', 'Bridge startup failed:')} {exc}")
                self._refresh_tray()
                return

        self._refresh_tray()
        threading.Thread(target=self._check_bridge_startup, daemon=True).start()

    def _check_bridge_startup(self):
        time.sleep(2.0)
        with self._bridge_lock:
            proc = self.bridge_process
            active = proc is not None and proc.poll() is None
            code = proc.poll() if proc is not None else None
        if active:
            self.notify(tr("Bridge Spotify démarré. Si c’est la première connexion, le navigateur peut s’ouvrir pour Spotify.", "Spotify bridge started. On first run, your browser may open for Spotify authorization."))
        else:
            log_path = self._log_dir / "bridge.log"
            self.notify(f"{tr('Le bridge s’est arrêté au démarrage', 'The bridge exited during startup')} (code {code}). {tr('Consulte', 'See')} logs\\bridge.log.")
        self._refresh_tray()

    def stop_bridge(self, icon=None, item=None, show_notification=True):
        with self._bridge_lock:
            proc = self.bridge_process
            flag = self.stop_flag
            if proc is None or proc.poll() is not None:
                if flag is not None:
                    try:
                        flag.unlink()
                    except FileNotFoundError:
                        pass
                self.bridge_process = None
                self.stop_flag = None
                self._refresh_tray()
                return
            try:
                if flag is not None:
                    flag.parent.mkdir(parents=True, exist_ok=True)
                    flag.write_text("stop", encoding="ascii")
            except OSError:
                pass
            try:
                proc.wait(timeout=8.0)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                        proc.wait(timeout=2.0)
                    except Exception:
                        pass
            except Exception:
                pass
            self.bridge_process = None
            self.stop_flag = None
            if flag is not None:
                try:
                    flag.unlink()
                except FileNotFoundError:
                    pass
        self._refresh_tray()
        if show_notification:
            self.notify(tr("Bridge arrêté. Le jeu reste ouvert.", "Bridge stopped. The game is still running."))

    def quit(self, icon=None, item=None):
        if self._quitting.is_set():
            return
        self._quitting.set()
        self.stop_bridge(show_notification=False)
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass

    def _launch_session(self):
        self._log_dir.mkdir(parents=True, exist_ok=True)
        original = game_process_snapshot()
        initial_pids = {row["pid"] for row in original}
        self._write_session_log(
            "Initial WoW client snapshot: " + (", ".join(f"pid={row['pid']} exe={row['exe']}" for row in original) if original else "no WoW.exe process found")
        )
        self.start_bridge()

        tracked_pids = set(initial_pids)
        if original:
            self.notify(tr("Client WoW déjà ouvert : cette session sera surveillée sans lancer une deuxième instance.", "WoW client is already open. Monitoring the current session without launching another instance."))
            candidates = original
        else:
            vf = GAME_DIR / VANILLAFIXES_NAME
            try:
                # VanillaFixes.exe is a Windows GUI-subsystem executable. We start
                # it with the game directory as cwd so DLL loading/config remains normal.
                subprocess.Popen([str(vf)], cwd=str(GAME_DIR), close_fds=True)
                self.notify(tr("VanillaFixes lancé. Détection du client WoW en cours…", "VanillaFixes launched. Detecting the WoW client…"))
            except Exception as exc:
                self.notify(f"{tr('Impossible de lancer VanillaFixes :', 'Could not launch VanillaFixes:')} {exc}")
                return
            candidates = []
            deadline = time.monotonic() + 180.0
            while time.monotonic() < deadline and not self._quitting.is_set():
                candidates = [row for row in game_process_snapshot() if row["pid"] not in initial_pids]
                if candidates:
                    break
                time.sleep(0.75)
            if not candidates:
                if not self._quitting.is_set():
                    self.notify(tr("Aucun client détecté après 3 minutes. Le bridge reste contrôlable depuis le menu de notification.", "No game client detected after 3 minutes. The bridge can still be controlled from the notification-area menu."))
                return

        tracked_pids.update(row["pid"] for row in candidates)
        first = candidates[0]
        self.notify(tr(f"Client détecté : {first['name']}. Ferme le jeu ou utilise Alt+F4 pour arrêter automatiquement le bridge.", f"Game client detected: {first['name']}. Close the game or press Alt+F4 to stop the bridge automatically."))

        while not self._quitting.is_set():
            current = {row["pid"] for row in game_process_snapshot()}
            if not (tracked_pids & current):
                # The user asked for the tray app itself to exit after WoW closes,
                # not merely for the bridge child process to stop.
                self._write_session_log("Tracked WoW client closed; stopping bridge and quitting tray app.")
                self.stop_bridge(show_notification=False)
                self.notify(tr(
                    "Client fermé : bridge arrêté. Fermeture de SpotiWoW-Raven.",
                    "Game client closed: bridge stopped. Quitting SpotiWoW-Raven.",
                ))
                # Give Windows a moment to display the notification before removing
                # the tray icon and exiting the launcher.
                time.sleep(1.25)
                self.quit()
                return
            time.sleep(1.0)

    def run(self):
        def setup(icon):
            icon.visible = True
            self._session_thread = threading.Thread(target=self._launch_session, name="SpotiWoW-Session", daemon=True)
            self._session_thread.start()
        self.icon.run(setup=setup)


def run_bridge_child():
    """Re-enter this one-file EXE as a hidden bridge worker using bundled Python."""
    try:
        if not BRIDGE_SCRIPT.is_file():
            raise FileNotFoundError(f"{BRIDGE_NAME} {tr('introuvable :', 'was not found:')} {BRIDGE_SCRIPT}")
        spec = importlib.util.spec_from_file_location("spotiwow_external_bridge", BRIDGE_SCRIPT)
        if spec is None or spec.loader is None:
            raise RuntimeError(tr("Impossible de charger le bridge Python.", "Could not load the Python bridge."))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.main()
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        if code != 0 and exc.code:
            print(str(exc.code), file=sys.stderr)
        return code
    except BaseException:
        traceback.print_exc()
        return 1


def main() -> int:
    if "--bridge-child" in sys.argv[1:]:
        return run_bridge_child()

    mutex, first_instance = acquire_single_instance_mutex()
    if not first_instance:
        message_box(f"{APP_NAME} {tr('est déjà en cours d’exécution. Cherche son icône dans la zone de notification.', 'is already running. Look for its icon in the notification area.')}", flags=MB_OK | MB_ICONINFORMATION)
        return 0

    try:
        validate_installation()
        app = SpotiWoWController()
        app.run()
        return 0
    except Exception as exc:
        # The launcher is built without a console; retain the full traceback so
        # startup failures can be diagnosed instead of showing only a short popup.
        log_path = ROOT / LOG_DIR_NAME / "launcher.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Startup failure\n")
                stream.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                stream.write("\n")
        except Exception:
            log_path = None
        detail = str(exc)
        if log_path:
            detail += f"\n\n{tr('Détails techniques :', 'Technical details:')} {log_path}"
        message_box(detail)
        return 1
    finally:
        if mutex:
            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL
                kernel32.CloseHandle(mutex)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
