"""
SpotifyNow companion for Turtle WoW / WoW 1.12.1 (Windows, Python 3.15).

Communication with the addon uses SuperWoW ImportFile/ExportFile and text files
in <game_dir>\\imports. No slash-command injection, pixel strip, or screen capture
is used. Lyrics are sent to the addon as events; the addon posts them to the
configured in-game channel only while Lyrics mode is enabled.

Global hotkeys: Ctrl+Alt+L toggles Lyrics; Ctrl+Alt+S refreshes addon state.
"""
import base64
import bisect
import ctypes
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

try:
    import syncedlyrics  # Optional dependency, installed through requirements.txt.
except ImportError:
    syncedlyrics = None

HERE = Path(__file__).resolve().parent
CFG_PATH = HERE / "config.json"
if not CFG_PATH.exists():
    raise SystemExit(
        "Configuration manquante : copiez config.example.json vers config.json, "
        "puis renseignez votre client_id Spotify."
    )
CFG = json.loads(CFG_PATH.read_text(encoding="utf-8"))
CLIENT_ID = CFG["client_id"]
LYRICS_OFFSET_MS = int(CFG.get("lyrics_offset_ms", 0))
LYRICS_CACHE_FILE = HERE / "lyrics_cache.json"
LYRICS_CACHE_DAYS = max(1, int(CFG.get("lyrics_cache_days", 90)))
LYRICS_NEGATIVE_CACHE_HOURS = max(1, int(CFG.get("lyrics_negative_cache_hours", 6)))
LYRICS_SEARCH_TIMEOUT = max(5, min(30, int(CFG.get("lyrics_search_timeout_seconds", 18))))
_ALLOWED_LYRICS_PROVIDERS = {"Musixmatch", "Lrclib", "NetEase", "Megalobiz"}
_configured_providers = CFG.get("lyrics_providers", ["Musixmatch", "Lrclib", "NetEase", "Megalobiz"])
LYRICS_PROVIDERS = [p for p in _configured_providers if p in _ALLOWED_LYRICS_PROVIDERS] if isinstance(_configured_providers, list) else ["Musixmatch", "Lrclib", "NetEase", "Megalobiz"]
if not LYRICS_PROVIDERS:
    LYRICS_PROVIDERS = ["Musixmatch", "Lrclib", "NetEase", "Megalobiz"]
GAME_DIR = Path(CFG.get("game_dir", r"C:\Jeux\World of Warcraft"))
IMPORT_DIR = GAME_DIR / "imports"
STATE_FILE = IMPORT_DIR / "SpotifyNowState.txt"
COMMAND_FILE = IMPORT_DIR / "SpotifyNowCommand.txt"
# The tray launcher sets a unique stop-flag path in the child environment.
# A file-based signal allows Stop/Quit to shut down cleanly without a console.
_PARENT_STOP_FLAG = os.environ.get("SPOTIWOW_STOP_FLAG")
STOP_FLAG = Path(_PARENT_STOP_FLAG) if _PARENT_STOP_FLAG else HERE / ".spotiwow_bridge_stop.flag"

def stop_requested() -> bool:
    try:
        return STOP_FLAG.exists()
    except OSError:
        return False
REDIRECT = "http://127.0.0.1:8888/callback"
SCOPE = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
TOKEN_FILE = HERE / "tokens.json"
TOKEN_URL = "https://accounts.spotify.com/api/token"

# ---------------------------------------------------------------- Spotify auth


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, body, {"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def save_tokens(tok, old_refresh=None):
    tok["expires_at"] = time.time() + tok.get("expires_in", 3600)
    tok.setdefault("refresh_token", old_refresh)
    tok.setdefault("scope", SCOPE)
    TOKEN_FILE.write_text(json.dumps(tok), encoding="utf-8")
    return tok


def login():
    verifier = b64url(secrets.token_bytes(64))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(8)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [None])[0] == state and "code" in q:
                result["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Connecte. Tu peux fermer cet onglet.".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8888), Handler)
    server.timeout = 1.0
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": REDIRECT,
        "scope": SCOPE, "state": state,
        "code_challenge_method": "S256", "code_challenge": challenge,
    })
    webbrowser.open("https://accounts.spotify.com/authorize?" + params)
    while "code" not in result and not stop_requested():
        server.handle_request()
    server.server_close()
    if stop_requested():
        raise SystemExit("Bridge stoppato dal menu di SpotiWoW-Raven.")
    tok = post_form(TOKEN_URL, {
        "grant_type": "authorization_code", "code": result["code"],
        "redirect_uri": REDIRECT, "client_id": CLIENT_ID, "code_verifier": verifier,
    })
    return save_tokens(tok)


_tokens = None


def get_token():
    global _tokens
    if _tokens is None:
        if TOKEN_FILE.exists():
            _tokens = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            if "user-modify-playback-state" not in _tokens.get("scope", ""):
                _tokens = login()  # nouveau scope necessaire pour les controles
        else:
            _tokens = login()
    if time.time() > _tokens["expires_at"] - 30:
        _tokens = save_tokens(
            post_form(TOKEN_URL, {
                "grant_type": "refresh_token",
                "refresh_token": _tokens["refresh_token"],
                "client_id": CLIENT_ID,
            }),
            _tokens["refresh_token"],
        )
    return _tokens["access_token"]


def player_state():
    req = urllib.request.Request(
        "https://api.spotify.com/v1/me/player",
        headers={"Authorization": "Bearer " + get_token()},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return None
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(int(e.headers.get("Retry-After", "5")))
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------- Lyrics

# LRC supports multiple timestamps on one line and arbitrary fractional precision.
_LRC_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{1,2}(?:[.,]\d+)?)\]")
_INLINE_TIMESTAMP = re.compile(r"<\d{1,3}:\d{1,2}(?:[.,]\d+)?>")
_CACHE_LOCK = threading.RLock()
_LYRICS_CACHE = {}
_LYRICS_CACHE_LOADED = False
_WARNED_MISSING_SYNCEDLYRICS = False


def parse_lrc_text(lrc_text, duration_s=None):
    """Convert provider LRC into sorted (milliseconds, text) rows and validate it."""
    if not isinstance(lrc_text, str) or not lrc_text.strip():
        return []

    result = []
    max_allowed_ms = (int(duration_s) * 1000 + 15000) if duration_s else None
    for raw in lrc_text.replace("\ufeff", "").splitlines():
        stamps = _LRC_TIMESTAMP.findall(raw)
        if not stamps:
            continue
        # Remove line and inline-word timestamps, then any metadata tags such as [ar:].
        text = _LRC_TIMESTAMP.sub("", raw)
        text = _INLINE_TIMESTAMP.sub("", text)
        text = re.sub(r"\[[A-Za-z]{1,8}:[^\]]*\]", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        for minutes, seconds in stamps:
            try:
                ms = int(round(int(minutes) * 60000 + float(seconds.replace(",", ".")) * 1000))
            except (TypeError, ValueError):
                continue
            # A result with timestamps far beyond the Spotify duration is likely a wrong match.
            if ms < 0 or (max_allowed_ms is not None and ms > max_allowed_ms):
                return []
            result.append((ms, text))

    # Sort and remove duplicates without changing timestamp ordering.
    result.sort(key=lambda item: (item[0], item[1]))
    unique = []
    seen = set()
    for item in result:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _normalise_cache_part(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _lyrics_cache_key(artist, title, album, duration_s):
    payload = "\0".join((
        _normalise_cache_part(artist),
        _normalise_cache_part(title),
        _normalise_cache_part(album),
        str(int(duration_s or 0)),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_lyrics_cache_locked():
    global _LYRICS_CACHE_LOADED, _LYRICS_CACHE
    if _LYRICS_CACHE_LOADED:
        return
    _LYRICS_CACHE_LOADED = True
    try:
        data = json.loads(LYRICS_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _LYRICS_CACHE = data
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        _LYRICS_CACHE = {}


def _persist_lyrics_cache_locked():
    try:
        LYRICS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = LYRICS_CACHE_FILE.with_name(LYRICS_CACHE_FILE.name + ".tmp")
        temporary.write_text(json.dumps(_LYRICS_CACHE, ensure_ascii=False), encoding="utf-8")
        os.replace(str(temporary), str(LYRICS_CACHE_FILE))
    except OSError as exc:
        print(f"[Lyrics] Impossible d'ecrire le cache local: {exc}")


def _get_cached_lyrics(cache_key):
    now = time.time()
    with _CACHE_LOCK:
        _load_lyrics_cache_locked()
        entry = _LYRICS_CACHE.get(cache_key)
        if not isinstance(entry, dict):
            return None
        lines = entry.get("lines")
        fetched_at = entry.get("fetched_at")
        if not isinstance(lines, list) or not isinstance(fetched_at, (int, float)):
            _LYRICS_CACHE.pop(cache_key, None)
            return None
        ttl = (LYRICS_CACHE_DAYS * 86400) if lines else (LYRICS_NEGATIVE_CACHE_HOURS * 3600)
        if now - fetched_at > ttl:
            _LYRICS_CACHE.pop(cache_key, None)
            return None
        try:
            parsed_lines = [(int(row[0]), str(row[1])) for row in lines if len(row) >= 2]
        except (TypeError, ValueError, IndexError):
            _LYRICS_CACHE.pop(cache_key, None)
            return None
        return parsed_lines, str(entry.get("source") or "cache")


def _store_cached_lyrics(cache_key, lines, source):
    with _CACHE_LOCK:
        _load_lyrics_cache_locked()
        _LYRICS_CACHE[cache_key] = {
            "fetched_at": time.time(),
            "source": source,
            "lines": [[int(ms), text] for ms, text in lines],
        }
        _persist_lyrics_cache_locked()


def _fetch_lrclib_exact(artist, title, album, duration_s):
    """First try LRCLIB's metadata-and-duration aware exact endpoint."""
    qs = urllib.parse.urlencode({
        "artist_name": artist, "track_name": title,
        "album_name": album, "duration": duration_s,
    })
    req = urllib.request.Request(
        "https://lrclib.net/api/get?" + qs,
        headers={"User-Agent": "SpotifyNow/1.3 (Turtle WoW lyrics bridge)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=7) as response:
            data = json.load(response)
        return parse_lrc_text(data.get("syncedLyrics") or "", duration_s)
    except Exception:
        return []


def _candidate_score(lines, duration_s):
    """Heuristic ranking for alternate-source results when providers return LRC only."""
    if not lines:
        return -1
    score = min(len(lines), 100) * 1.0
    if duration_s and duration_s > 0:
        ratio = lines[-1][0] / float(duration_s * 1000)
        if 0.40 <= ratio <= 1.08:
            score += 12
        elif 0.25 <= ratio < 0.40:
            score += 5
        elif ratio < 0.12 and duration_s > 90:
            score -= 8
    return score


def _clean_search_title(title):
    """Remove common upload-label suffixes without stripping meaningful song versions."""
    cleaned = re.sub(
        r"\s*[\[(](?:official\s+)?(?:audio|video|lyrics?|lyric video|visualizer)[^\])]*[\])]\s*$",
        "", title or "", flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*[-|–]\s*(?:official\s+)?(?:audio|video|lyrics?)\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or (title or "").strip()


def _search_one_provider(provider, query, duration_s):
    if syncedlyrics is None:
        return None
    try:
        lrc_text = syncedlyrics.search(query, synced_only=True, providers=[provider])
        lines = parse_lrc_text(lrc_text, duration_s)
        if not lines:
            return None
        return {
            "provider": provider,
            "lines": lines,
            "score": _candidate_score(lines, duration_s),
        }
    except Exception as exc:
        # Provider failures are expected occasionally (rate limits, upstream changes).
        print(f"[Lyrics] {provider} indisponible: {type(exc).__name__}")
        return None


def _cleanup_syncedlyrics_log_handlers():
    """Avoid accumulating duplicate handlers; syncedlyrics currently adds one per provider instance."""
    for name in ("Musixmatch", "Lrclib", "NetEase", "Megalobiz", "Genius"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers[1:]):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def _search_multi_source(artist, title, duration_s):
    """Search synchronized providers concurrently; no plain-text lyrics are accepted."""
    global _WARNED_MISSING_SYNCEDLYRICS
    if syncedlyrics is None:
        if not _WARNED_MISSING_SYNCEDLYRICS:
            print("[Lyrics] Multi-sources indisponibles: installez companion/requirements.txt")
            _WARNED_MISSING_SYNCEDLYRICS = True
        return [], ""

    clean_title = _clean_search_title(title)
    queries = []
    for query in (f"{artist} - {title}", f"{artist} - {clean_title}", f"{title} {artist}"):
        query = re.sub(r"\s+", " ", query).strip(" -")
        if query and query.casefold() not in {q.casefold() for q in queries}:
            queries.append(query)

    deadline = time.monotonic() + LYRICS_SEARCH_TIMEOUT
    for query in queries:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        pool = ThreadPoolExecutor(max_workers=min(4, len(LYRICS_PROVIDERS)))
        futures = {
            pool.submit(_search_one_provider, provider, query, duration_s): provider
            for provider in LYRICS_PROVIDERS
        }
        candidates = []
        try:
            for future in as_completed(futures, timeout=remaining):
                try:
                    candidate = future.result()
                except Exception:
                    candidate = None
                if candidate:
                    candidates.append(candidate)
        except FuturesTimeoutError:
            pass
        finally:
            for future in futures:
                if not future.done():
                    future.cancel()
            # Providers have their own request timeouts; don't block lyrics state updates here.
            pool.shutdown(wait=False, cancel_futures=True)

        _cleanup_syncedlyrics_log_handlers()
        if candidates:
            best = max(candidates, key=lambda item: item["score"])
            return best["lines"], best["provider"]
    return [], ""


def fetch_lyrics(artist, title, album, duration_s):
    """Find synced lyrics: exact LRCLIB first, then parallel multi-source fallbacks."""
    cache_key = _lyrics_cache_key(artist, title, album, duration_s)
    cached = _get_cached_lyrics(cache_key)
    if cached is not None:
        lines, source = cached
        print(f"[Lyrics] Cache: {len(lines)} lignes ({source})")
        return lines, source

    lines = _fetch_lrclib_exact(artist, title, album, duration_s)
    if lines:
        source = "LRCLIB exact"
        _store_cached_lyrics(cache_key, lines, source)
        return lines, source

    lines, source = _search_multi_source(artist, title, duration_s)
    if lines:
        _store_cached_lyrics(cache_key, lines, source)
        return lines, source

    # If the optional multi-source package is missing, don't persist a negative
    # result: installing it should take effect on the very next track replay.
    if syncedlyrics is not None:
        _store_cached_lyrics(cache_key, [], "not found")
    return [], "aucune source synchronisée trouvée"


# ------------------------------------------------------------- Fichiers de bridge
# SuperWoW exposes ImportFile/ExportFile for files under <game_dir>\imports.
# File names are deliberately fixed (no path components) to respect that API.

user32 = ctypes.windll.user32
state_write_lock = threading.Lock()


def encode_field(value) -> str:
    """Percent-encode a field so the protocol delimiter (|) is never ambiguous."""
    return urllib.parse.quote(str(value or ""), safe="")


def atomic_write(path: Path, content: str) -> None:
    """Avoid Lua reading a partially written state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="")
    os.replace(str(temp), str(path))


def publish_state() -> None:
    """Publish one compact, Lua-5.0-friendly state record to the game imports dir."""
    with state_write_lock:
        S["state_seq"] += 1
        volume = S["volume"] if S["volume"] is not None else -1
        fields = [
            "SPN1", str(S["state_seq"]), encode_field(S["track_id"] or ""),
            encode_field(S["artist"]), encode_field(S["title"]),
            str(int(S["progress_ms"] or 0)), str(int(S["duration_ms"] or 0)),
            "1" if S["playing"] else "0", str(int(volume)),
            "1" if S["lyrics_on"] else "0", str(int(S["line_seq"])),
            encode_field(S["current_lyric"]),
        ]
        payload = "|".join(fields) + "\n"
        try:
            atomic_write(STATE_FILE, payload)
        except Exception as exc:
            print(f"[Bridge] Impossible d'ecrire {STATE_FILE}: {exc}")


def read_command_payload() -> str:
    try:
        return COMMAND_FILE.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError, UnicodeError):
        return ""


def parse_command_payload(payload):
    """Return (session, sequence, command, argument), or None for invalid data."""
    fields = payload.split("|", 4)
    if len(fields) != 5 or fields[0] != "SPNC1":
        return None
    if not fields[1].isdigit() or not fields[2].isdigit():
        return None
    return fields[1], fields[2], fields[3].strip().lower(), fields[4].strip()


# ------------------------------------------------------------------ Etat / threads

S = {
    "lyrics_on": False, "track_id": None, "artist": "", "title": "",
    "lines": [], "times": [], "progress_ms": 0, "stamp": 0.0, "duration_ms": 0,
    "playing": False, "volume": None, "sent_idx": -1,
    "state_seq": 0, "line_seq": 0, "current_lyric": "",
}
wake = threading.Event()


def load_track_lyrics(track_id, artist, title, album, duration_s):
    """Fetch lyrics away from the Spotify polling loop and discard stale results."""
    lines, source = fetch_lyrics(artist, title, album, duration_s)
    if track_id != S["track_id"]:
        return
    S["lines"], S["times"] = lines, [t for t, _ in lines]
    if lines:
        print(f"[Lyrics] {len(lines)} lignes synchronisees via {source}")
    else:
        print(f"[Lyrics] Aucun resultat synchronise pour {artist} - {title}")


def poll_loop():
    while not stop_requested():
        data = player_state()
        item = (data or {}).get("item")
        if item and data.get("currently_playing_type") == "track":
            S["progress_ms"] = data.get("progress_ms") or 0
            S["stamp"] = time.time()
            S["duration_ms"] = item.get("duration_ms") or 0
            S["playing"] = bool(data.get("is_playing"))
            S["volume"] = (data.get("device") or {}).get("volume_percent")
            if item["id"] != S["track_id"]:
                S["track_id"] = item["id"]
                S["artist"] = ", ".join(a["name"] for a in item.get("artists", []))
                S["title"] = item.get("name") or ""
                S["sent_idx"] = -1
                S["lines"], S["times"] = [], []
                S["current_lyric"] = ""
                print(f"[Spotify] {S['artist']} - {S['title']}")
                publish_state()
                first_artist = (item.get("artists") or [{}])[0].get("name", "")
                album = (item.get("album") or {}).get("name", "")
                duration_s = round((item.get("duration_ms") or 0) / 1000)
                threading.Thread(
                    target=load_track_lyrics,
                    args=(item["id"], first_artist, S["title"], album, duration_s),
                    daemon=True,
                ).start()
            publish_state()
        else:
            if S["playing"]:
                S["playing"] = False
                S["stamp"] = time.time()
                publish_state()
        # Refresh Spotify's current-track metadata every 10 seconds. Addon file
        # synchronization remains independent and can still react to commands.
        wake.wait(10)
        wake.clear()


def lyrics_loop():
    while not stop_requested():
        time.sleep(0.1)
        if not (S["lyrics_on"] and S["playing"] and S["lines"]):
            continue
        pos = S["progress_ms"] + (time.time() - S["stamp"]) * 1000 + LYRICS_OFFSET_MS
        idx = bisect.bisect_right(S["times"], pos) - 1
        if idx < 0 or idx == S["sent_idx"]:
            continue
        moved_backwards = idx < S["sent_idx"]
        late = pos - S["times"][idx]
        S["sent_idx"] = idx
        # Seeking backwards should immediately restore the corresponding line.
        if late < 1500 or moved_backwards:
            S["current_lyric"] = S["lines"][idx][1]
            S["line_seq"] += 1
            publish_state()


def set_lyrics(on):
    on = bool(on)
    changed = on != S["lyrics_on"]
    S["lyrics_on"] = on
    if on and changed:
        # Allow the current line to be emitted after re-enabling Lyrics mode.
        S["sent_idx"] = -1
    print(f"[Lyrics] mode {'on' if on else 'off'}")
    publish_state()


def toggle_lyrics():
    set_lyrics(not S["lyrics_on"])


# ------------------------------------------------------- Controles du mini-lecteur


def api_send(method, path, params=None):
    url = "https://api.spotify.com/v1/me/player/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, data=b"", method=method,
        headers={"Authorization": "Bearer " + get_token()},
    )
    try:
        urllib.request.urlopen(req, timeout=10).close()
        return True
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("[Controle] refuse (Spotify Premium requis, ou action non supportee)")
        else:
            print(f"[Controle] erreur HTTP {e.code}")
    except Exception as e:
        print("[Controle] erreur :", e)
    return False


def current_pos():
    if not S["playing"]:
        return S["progress_ms"]
    return S["progress_ms"] + (time.time() - S["stamp"]) * 1000


def handle_command(cmd):
    """Execute a command sent by the addon through SpotifyNowCommand.txt."""
    if cmd == "prev":
        api_send("POST", "previous")
    elif cmd == "pause":
        ok = api_send("PUT", "pause" if S["playing"] else "play")
        if ok:
            S["progress_ms"] = current_pos()
            S["stamp"] = time.time()
            S["playing"] = not S["playing"]
    elif cmd == "next":
        api_send("POST", "next")
    elif cmd in ("back", "fwd"):
        pos = current_pos() + (-10000 if cmd == "back" else 10000)
        pos = int(min(max(pos, 0), max(S["duration_ms"] - 1000, 0)))
        if api_send("PUT", "seek", {"position_ms": pos}):
            S["progress_ms"], S["stamp"] = pos, time.time()
    elif cmd in ("voldown", "volup"):
        vol = S["volume"] if S["volume"] is not None else 50
        vol = min(max(vol + (-10 if cmd == "voldown" else 10), 0), 100)
        if api_send("PUT", "volume", {"volume_percent": vol}):
            S["volume"] = vol
    publish_state()
    time.sleep(0.3)
    wake.set()


def handle_bridge_command(cmd, argument):
    if cmd == "lyrics":
        set_lyrics(argument == "1")
    elif cmd in {"prev", "pause", "next", "back", "fwd", "voldown", "volup"}:
        threading.Thread(target=handle_command, args=(cmd,), daemon=True).start()
    else:
        print(f"[Bridge] Commande ignoree: {cmd!r}")


def command_loop(initial_payload=""):
    """Poll the addon's ExportFile output; no chat injection or pixel capture."""
    initial = parse_command_payload(initial_payload)
    last_id = (initial[0], initial[1]) if initial else None
    while not stop_requested():
        payload = read_command_payload()
        parsed = parse_command_payload(payload) if payload else None
        if parsed:
            session, sequence, cmd, argument = parsed
            command_id = (session, sequence)
            if command_id != last_id:
                last_id = command_id
                handle_bridge_command(cmd, argument)
        time.sleep(0.1)


def command_id_from_payload(payload):
    parsed = parse_command_payload(payload) if payload else None
    return (parsed[0], parsed[1]) if parsed else None


def main():
    # Clear only the standalone mode's stale flag. The tray launcher supplies a
    # unique environment path which must never be deleted at child startup.
    if not _PARENT_STOP_FLAG:
        try:
            STOP_FLAG.unlink()
        except FileNotFoundError:
            pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    if not GAME_DIR.is_dir():
        raise SystemExit(
            f"Dossier du jeu introuvable: {GAME_DIR}. "
            "Verifiez game_dir dans companion/config.json."
        )
    try:
        IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise SystemExit(f"Impossible de creer le dossier Imports {IMPORT_DIR}: {exc}")

    # Capture the current command before OAuth; commands made during login aren't lost.
    initial_command = read_command_payload()
    publish_state()
    get_token()  # opens the browser on first run
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=lyrics_loop, daemon=True).start()
    threading.Thread(target=command_loop, args=(initial_command,), daemon=True).start()

    MOD_ALT, MOD_CONTROL, WM_HOTKEY = 0x1, 0x2, 0x0312
    user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT, ord("L"))
    user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_ALT, ord("S"))
    print(f"Pret. Dossier de bridge: {IMPORT_DIR}")
    print("Ctrl+Alt+L = mode Lyrics, Ctrl+Alt+S = actualiser l'etat. Ctrl+C pour quitter.")
    msg = wintypes.MSG()
    PM_REMOVE = 0x0001
    WM_QUIT = 0x0012
    try:
        # Poll the Windows message queue instead of blocking forever in GetMessageW;
        # this makes the bridge responsive to the tray Stop/Quit flag.
        while not stop_requested():
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    return
                if msg.message == WM_HOTKEY:
                    if msg.wParam == 1:
                        toggle_lyrics()
                    elif msg.wParam == 2:
                        publish_state()
            time.sleep(0.05)
    finally:
        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)
        # Only the standalone bridge removes its shared default flag. The tray
        # launcher owns its own unique per-session path and cleans it itself.
        if not _PARENT_STOP_FLAG:
            try:
                STOP_FLAG.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    main()
