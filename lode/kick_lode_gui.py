"""
Kick.com Lodě Bot — GUI verze
Hra Lodě pro až 40 hráčů najednou v chatu.

PRAVIDLA:
  Moderátor spustí hru příkazem !start. Bot rozmístí lodě na skryté mřížce
  10×10 (řádky A–J, sloupce 1–10). Hráči střílí zadáním souřadnice do chatu
  (např. A5, B10, j1 — case-insensitive). Každou souřadnici bere první kdo
  ji napíše. Zásah = +1 bod, potopení lodě = bonus body dle velikosti.
  Hra končí potopením všech lodí nebo příkazem !stop moderátora.

LODĚ:
  1× Letadlová loď  5 polí  bonus 10 bodů
  1× Křižník        4 pole  bonus  7 bodů
  2× Torpédoborec   3 pole  bonus  5 bodů
  2× Ponorka        2 pole  bonus  3 body
  3× Hlídkový člun  1 pole  bonus  1 bod

PŘÍKAZY V CHATU:
  !start   (moderátor) — zahájit novou hru
  !stop    (moderátor) — ukončit hru předčasně
  !mapa    (kdokoliv)  — zobrazit aktuální mapu
  !skore   (kdokoliv)  — zobrazit žebříček

Instalace: pip install customtkinter websocket-client curl_cffi requests
Spuštění:  python kick_lode_gui.py
"""

import os, sys, json, re, time, hashlib, base64, secrets, webbrowser, threading, random, math
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from pathlib import Path
from datetime import datetime
import tkinter as tk

import customtkinter as ctk
import requests
from curl_cffi import requests as cf_requests
import websocket

BUILD_VERSION = "260502.0502"
DEBUG = False

KICK_AUTH_URL  = "https://id.kick.com/oauth/authorize"
KICK_TOKEN_URL = "https://id.kick.com/oauth/token"
KICK_API_URL   = "https://api.kick.com/public/v1"
KICK_SCOPES    = "user:read chat:write"
PUSHER_WS      = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
                  "?protocol=7&client=js&version=8.4.0-rc2&flash=false")
REDIRECT_URI   = "http://localhost:7878/callback"
TOKEN_FILE          = Path("kick_tokens.json")
CONFIG_FILE         = Path("kick_lode_config.json")
LODE_BOT_CONFIG_FILE = Path("lode_bot_config.json")

KICK_GREEN  = "#53FC18"
DARK_BG     = "#0d0d0d"
PANEL_BG    = "#141414"
CARD_BG     = "#1a1a1a"
BORDER      = "#2a2a2a"
TEXT_DIM    = "#666666"
TEXT_MID    = "#aaaaaa"
TEXT_BRIGHT = "#f0f0f0"
RED_ERR     = "#ff4444"
YELLOW_WARN = "#ffcc00"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

ROWS = "ABCDEFGHIJ"

SHIPS_DEF = [
    # (název, velikost, bonus_za_potopení)
    ("Letadlová loď", 5, 10),
    ("Křižník",       4,  7),
    ("Torpédoborec",  3,  5),
    ("Torpédoborec",  3,  5),
    ("Ponorka",       2,  3),
    ("Ponorka",       2,  3),
    ("Hlídkový člun", 1,  1),
    ("Hlídkový člun", 1,  1),
    ("Hlídkový člun", 1,  1),
]


# ════════════════════════════════════════════════════════════════════════════
#  Textová konfigurace bota (lode_bot_config.json)
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_LODE_CONFIG = {
    "prikazy": {
        "start": "!start",
        "close": "!close",
        "stop":  "!stop",
        "mapa":  "!mapa",
    },
    "zpravy": {
        # Standardní hra
        "bot_online":         "⚓ Lodě bot je online! Moderátor zadá {prikaz_start} pro zahájení registrace. Příkazy: {prikaz_mapa}",
        "std_zahajena":       "⚓ LODĚ ZAHÁJENA! Mřížka A–J × 1–10. Střílej souřadnicí do chatu, např. A5 nebo J10. Zásah=+1 bod, potopení=bonus. Příkazy: !mapa !skore | Lodě: {lode}",
        "std_zastavena":      "🛑 Hra zastavena. Výstřelů: {vystrely}, zásahů: {zasahy}, potopeno: {potopeno}/{lodi} lodí.",
        "std_probiha":        "⚠️ Hra už probíhá! Zastav ji příkazem {prikaz_stop}.",
        "std_zadna":          "⚠️ Žádná hra neprobíhá.",
        "std_zasah":          "💥 @{username} zasáhl/a {coord}! +1 bod ({body} celkem)",
        "std_potopeni":       "🔥 @{username} POTOPIL/A {lod}! +{bonus} bodů bonus! ({body} celkem) Zbývá {zbyva} {lodi_text}.",
        "std_konec":          "🏆 @{username} POTOPIL/A {lod} a vyhrál/a hru! Všechny lodě jsou na dně! Výstřelů: {vystrely}.",
        "std_jiz_strileno":   "⚠️ @{username} pole {coord} už střílel/a @{kdo}",
        "std_zadne_zasahy":   "📊 Zatím nikdo nic nezasáhl.",
        # Vlastní hra s registrací
        "vlast_reg_start":    "🎮 Zahajujeme vlastní hru Lodě! Kdo chce hrát, napiš 1 do chatu! Počet hráčů určí velikost herního pole.",
        "vlast_prihlasen":    "✅ @{username} přihlášen/a! Celkem hráčů: {n}",
        "vlast_zadni_hraci":  "⚠️ Nikdo se nepřihlásil!",
        "vlast_reg_uzavrena": "🛑 Registrace uzavřena! Hráčů: {n}. Herní pole: {radky} ({celkem} polí). Moderátor nyní umísťuje loď...",
        "vlast_hra_start":    "⚓ HRA ZAČÍNÁ! Pořadí: {hraci}. Loď má {pocet_poli} polí. Pole: {radky}. Příkaz {prikaz_mapa} zobrazí mapu.",
        "vlast_na_rade":      "🎯 @{username} — kde střílíš? (souřadnice, např. A5) [zbývá {zbyva} {zbyvajici_text} lodě]",
        "vlast_miss":         "💧 @{username} minul/a {coord}.",
        "vlast_zasah":        "💥 @{username} ZASÁHL/A {coord}! Zbývá {zbyva} {zbyvajici_text} lodě!",
        "vlast_jiz_strileno": "⚠️ @{username} pole {coord} už bylo stříleno — zkus jiné!",
        "vlast_konec":        "🏆 @{username} POTOPIL/A loď na {coord} a VYHRÁL/A! Výstřelů: {vystrely}.",
        "vlast_zastavena":    "🛑 Vlastní hra zastavena moderátorem.",
    },
}

LODE_CONFIG_TEMPLATE = {
    "_komentare": {
        "popis":    "Konfigurační soubor Kick Lodě Bota",
        "poznamka": "Proměnné v {složených závorkách} se automaticky dosadí — nemazat je!",
    },
    "prikazy": {
        "_vysvetleni": "Příkazy bota v chatu — změň na cokoliv (musí začínat !). Po změně klikni Načíst změny konfigurace.",
        **DEFAULT_LODE_CONFIG["prikazy"],
    },
    "zpravy": {
        "_vysvetleni": "Texty které bot píše do chatu. Proměnné v {závorkách} jsou povinné. V textech lze použít {prikaz_start} {prikaz_close} {prikaz_stop} {prikaz_mapa}.",
        **DEFAULT_LODE_CONFIG["zpravy"],
    },
    "_napoveda_promennych": {
        "std_zahajena":       "{lode} = seznam lodí",
        "std_zastavena":      "{vystrely} {zasahy} {potopeno} {lodi}",
        "std_zasah":          "{username} {coord} {body}",
        "std_potopeni":       "{username} {lod} {bonus} {body} {zbyva} {lodi_text}",
        "std_konec":          "{username} {lod} {vystrely}",
        "std_jiz_strileno":   "{username} {coord} {kdo}",
        "vlast_prihlasen":    "{username} {n}",
        "vlast_reg_uzavrena": "{n} {radky} {celkem}",
        "vlast_hra_start":    "{hraci} {pocet_poli} {radky}",
        "vlast_na_rade":      "{username} {zbyva} {zbyvajici_text}",
        "vlast_miss":         "{username} {coord}",
        "vlast_zasah":        "{username} {coord} {zbyva} {zbyvajici_text}",
        "vlast_jiz_strileno": "{username} {coord}",
        "vlast_konec":        "{username} {coord} {vystrely}",
    },
}


def load_lode_config() -> dict:
    import copy
    cfg = copy.deepcopy(DEFAULT_LODE_CONFIG)
    if not LODE_BOT_CONFIG_FILE.exists():
        try:
            LODE_BOT_CONFIG_FILE.write_text(
                json.dumps(LODE_CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[WARN] Nelze vytvořit lode_bot_config.json: {e}")
        return cfg
    try:
        user = json.loads(LODE_BOT_CONFIG_FILE.read_text(encoding="utf-8"))
        if "zpravy" in user and isinstance(user["zpravy"], dict):
            for k, v in user["zpravy"].items():
                if not k.startswith("_") and isinstance(v, str):
                    cfg["zpravy"][k] = v
        if "prikazy" in user and isinstance(user["prikazy"], dict):
            for k, v in user["prikazy"].items():
                if not k.startswith("_") and isinstance(v, str):
                    cfg["prikazy"][k] = v
    except json.JSONDecodeError as e:
        print(f"[ERROR] lode_bot_config.json má chybu: {e} — používám výchozí hodnoty")
    except Exception as e:
        print(f"[WARN] Nelze načíst lode_bot_config.json: {e} — používám výchozí hodnoty")
    return cfg


# ════════════════════════════════════════════════════════════════════════════
#  Herní logika
# ════════════════════════════════════════════════════════════════════════════
class LodeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        self._grid  = [[None] * 10 for _ in range(10)]  # None nebo index lodi
        self.ships  = []
        self.shots  = {}   # (r, c) -> {"hit": bool, "username": str}
        self.scores = {}   # username -> body
        self.active   = False
        self.finished = False

    def new_game(self):
        self.reset()
        self._place_ships()
        self.active = True

    # ── Rozmístění lodí ──────────────────────────────────────────────────────
    def _place_ships(self):
        for attempt in range(10):
            self._grid = [[None] * 10 for _ in range(10)]
            self.ships = []
            ok = True
            for idx, (name, size, bonus) in enumerate(SHIPS_DEF):
                placed = False
                for _ in range(500):
                    horiz = random.choice([True, False])
                    if horiz:
                        r = random.randint(0, 9)
                        c = random.randint(0, 10 - size)
                        cells = [(r, c + i) for i in range(size)]
                    else:
                        r = random.randint(0, 10 - size)
                        c = random.randint(0, 9)
                        cells = [(r + i, c) for i in range(size)]
                    if all(self._cell_free(r2, c2) for r2, c2 in cells):
                        for r2, c2 in cells:
                            self._grid[r2][c2] = idx
                        self.ships.append({
                            "name": name, "size": size, "bonus": bonus,
                            "cells": set(cells), "hits": set(),
                            "sunk": False, "sunk_by": None,
                        })
                        placed = True
                        break
                if not placed:
                    ok = False
                    break
            if ok:
                return
        raise RuntimeError("Nepodařilo se rozmístit lodě — zkus znovu.")

    def _cell_free(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < 10 and 0 <= nc < 10 and self._grid[nr][nc] is not None:
                    return False
        return True

    # ── Parsování souřadnice ─────────────────────────────────────────────────
    def parse_coord(self, text: str):
        """Vrátí (row_idx, col_idx) nebo None. Přijme jen čistou souřadnici."""
        m = re.fullmatch(r"\s*([A-Ja-j])\s*(10|[1-9])\s*", text)
        if not m:
            return None
        return ROWS.index(m.group(1).upper()), int(m.group(2)) - 1

    @staticmethod
    def coord_str(r: int, c: int) -> str:
        return f"{ROWS[r]}{c + 1}"

    # ── Střelba ──────────────────────────────────────────────────────────────
    def shoot(self, username: str, r: int, c: int) -> dict:
        coord = (r, c)
        label = self.coord_str(r, c)

        if coord in self.shots:
            return {"type": "already_shot", "coord": label,
                    "shot_by": self.shots[coord]["username"]}

        hit = self._grid[r][c] is not None
        self.shots[coord] = {"hit": hit, "username": username}
        self.scores.setdefault(username, 0)

        if not hit:
            return {"type": "miss", "coord": label}

        self.scores[username] += 1
        ship = self.ships[self._grid[r][c]]
        ship["hits"].add(coord)

        if ship["hits"] == ship["cells"]:
            ship["sunk"] = True
            ship["sunk_by"] = username
            self.scores[username] += ship["bonus"]
            if all(s["sunk"] for s in self.ships):
                self.active = False
                self.finished = True
                return {"type": "game_over", "coord": label, "ship": ship}
            return {"type": "sunk", "coord": label, "ship": ship}

        return {"type": "hit", "coord": label}

    # ── Zobrazení ────────────────────────────────────────────────────────────
    def render_board_chat(self) -> str:
        lines = ["   1234567890"]
        for ri, row in enumerate(ROWS):
            line = f"{row}: "
            for ci in range(10):
                s = self.shots.get((ri, ci))
                line += ("X" if s["hit"] else "O") if s else "·"
            lines.append(line)
        return "\n".join(lines)

    def top_scores(self, n: int = 15) -> list:
        return sorted(self.scores.items(), key=lambda x: -x[1])[:n]

    def remaining_ships(self) -> list:
        return [s for s in self.ships if not s["sunk"]]

    def stats(self) -> dict:
        total = len(self.shots)
        hits  = sum(1 for v in self.shots.values() if v["hit"])
        return {"total": total, "hits": hits, "misses": total - hits,
                "sunk": sum(1 for s in self.ships if s["sunk"]),
                "ships": len(self.ships)}


# ════════════════════════════════════════════════════════════════════════════
#  Vlastní hra — registrace + ručně umístěná loď + střídání hráčů
# ════════════════════════════════════════════════════════════════════════════
class CustomGame:
    ALL_ROWS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    IDLE         = "idle"
    REGISTRATION = "registration"
    PLACEMENT    = "placement"
    PLAYING      = "playing"
    DONE         = "done"

    def __init__(self):
        self.phase      = self.IDLE
        self.players    = []       # pořadí registrace
        self.ship_cells = set()    # (r, c) buňky lodě
        self.shots      = {}       # (r, c) -> {"hit": bool, "username": str}
        self.grid_rows  = 10
        self.grid_cols  = 10
        self.turn_idx   = 0
        self.winner     = None

    @property
    def rows_labels(self) -> str:
        return self.ALL_ROWS[:self.grid_rows]

    @property
    def current_player(self):
        if self.phase != self.PLAYING or not self.players:
            return None
        return self.players[self.turn_idx % len(self.players)]

    def start_registration(self):
        self.phase      = self.REGISTRATION
        self.players    = []
        self.ship_cells = set()
        self.shots      = {}
        self.turn_idx   = 0
        self.winner     = None

    def register(self, username: str) -> bool:
        if username not in self.players:
            self.players.append(username)
            return True
        return False

    def close_registration(self) -> bool:
        if not self.players:
            return False
        total = len(self.players) * 4
        self.grid_cols = 10
        self.grid_rows = min(26, max(4, math.ceil(total / 10)))
        self.phase = self.PLACEMENT
        return True

    def set_ship_and_start(self, cells: set) -> bool:
        if not cells:
            return False
        self.ship_cells = set(cells)
        self.phase      = self.PLAYING
        self.turn_idx   = 0
        return True

    def parse_coord(self, text: str):
        rl = self.rows_labels
        safe = re.escape(rl + rl.lower())
        m = re.fullmatch(rf"\s*([{safe}])\s*(10|[1-9])\s*", text)
        if not m:
            return None
        r = rl.index(m.group(1).upper())
        c = int(m.group(2)) - 1
        return r, c

    def coord_label(self, r: int, c: int) -> str:
        return f"{self.rows_labels[r]}{c + 1}"

    def shoot(self, username: str, r: int, c: int) -> dict:
        label = self.coord_label(r, c)
        if username != self.current_player:
            return {"type": "not_your_turn", "current": self.current_player}
        coord = (r, c)
        if coord in self.shots:
            return {"type": "already_shot", "coord": label,
                    "shot_by": self.shots[coord]["username"]}
        hit = coord in self.ship_cells
        self.shots[coord] = {"hit": hit, "username": username}
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        if not hit:
            return {"type": "miss", "coord": label}
        if all(c2 in self.shots and self.shots[c2]["hit"] for c2 in self.ship_cells):
            self.winner = username
            self.phase  = self.DONE
            return {"type": "game_over", "coord": label}
        return {"type": "hit", "coord": label}

    def hits_left(self) -> int:
        return sum(1 for c in self.ship_cells
                   if not (self.shots.get(c, {}).get("hit")))

    def render_board_chat(self) -> str:
        rl   = self.rows_labels
        cols = self.grid_cols
        lines = ["   " + "".join(str(c % 10) for c in range(1, cols + 1))]
        for ri in range(self.grid_rows):
            line = f"{rl[ri]}: "
            for ci in range(cols):
                s = self.shots.get((ri, ci))
                line += ("X" if s["hit"] else "O") if s else "·"
            lines.append(line)
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
#  Bot engine
# ════════════════════════════════════════════════════════════════════════════
class LodeEngine:

    def __init__(self, log_cb, status_cb, board_cb, scores_cb,
                 reg_update_cb=None, turn_cb=None, placement_cb=None):
        self.log_cb        = log_cb
        self.status_cb     = status_cb
        self.board_cb      = board_cb
        self.scores_cb     = scores_cb
        self.reg_update_cb = reg_update_cb  # (players: list) -> None
        self.turn_cb       = turn_cb        # (current_player: str) -> None
        self.placement_cb  = placement_cb   # () -> None  — GUI otevře dialog

        self.game           = LodeGame()
        self.cgame          = CustomGame()
        self.broadcaster_id = 0
        self.chatroom_id    = 0
        self.ws             = None
        self.ws_thread      = None
        self.running        = False

        self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._load_tokens()
        self.bcfg = load_lode_config()
        self._load_commands()

    def _load_commands(self):
        p = self.bcfg.get("prikazy", {})
        self.CMD_START = p.get("start", "!start").strip().lower()
        self.CMD_CLOSE = p.get("close", "!close").strip().lower()
        self.CMD_STOP  = p.get("stop",  "!stop").strip().lower()
        self.CMD_MAPA  = p.get("mapa",  "!mapa").strip().lower()

    def reload_config(self):
        self.bcfg = load_lode_config()
        self._load_commands()
        self.log("✅ lode_bot_config.json znovu načten.", "success")

    def _msg(self, key: str, **kwargs) -> str:
        template = self.bcfg["zpravy"].get(key, f"[{key}]")
        p = self.bcfg.get("prikazy", {})
        try:
            return template.format(
                prikaz_start=p.get("start", "!start"),
                prikaz_close=p.get("close", "!close"),
                prikaz_stop=p.get("stop",  "!stop"),
                prikaz_mapa=p.get("mapa",  "!mapa"),
                **kwargs,
            )
        except (KeyError, ValueError):
            return template

    @staticmethod
    def _pole_text(n: int) -> str:
        return "pole" if n == 1 else "polí"

    @staticmethod
    def _lodi_text(n: int) -> str:
        if n == 1:   return "loď"
        if n <= 4:   return "lodě"
        return "lodí"

    # ── Tokeny ───────────────────────────────────────────────────────────────
    def _load_tokens(self):
        if TOKEN_FILE.exists():
            try:
                self.tokens.update(json.loads(TOKEN_FILE.read_text()))
            except Exception:
                pass

    def _save_tokens(self):
        TOKEN_FILE.write_text(json.dumps(self.tokens, indent=2))

    def _token_valid(self):
        return bool(self.tokens["access_token"]) and time.time() < self.tokens["expires_at"] - 60

    def _pkce_pair(self):
        v = secrets.token_urlsafe(64)
        d = hashlib.sha256(v.encode()).digest()
        c = base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        return v, c

    # ── OAuth ─────────────────────────────────────────────────────────────────
    def do_oauth(self, client_id, client_secret, on_done):
        def run():
            self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
            verifier, challenge = self._pkce_pair()
            params = {
                "response_type": "code", "client_id": client_id,
                "redirect_uri": REDIRECT_URI, "scope": KICK_SCOPES,
                "code_challenge": challenge, "code_challenge_method": "S256",
                "state": secrets.token_urlsafe(16),
            }
            webbrowser.open(f"{KICK_AUTH_URL}?{urlencode(params)}")
            result = {}

            class H(BaseHTTPRequestHandler):
                def do_GET(s):
                    parsed = urlparse(s.path)
                    qs = parse_qs(parsed.query)
                    result["code"]  = qs.get("code",  [""])[0]
                    result["error"] = qs.get("error", [""])[0]
                    s.send_response(200)
                    s.send_header("Content-Type", "text/html; charset=utf-8")
                    s.end_headers()
                    body = (b"<html><body style='font-family:sans-serif;text-align:center;"
                            b"padding:60px;background:#0d0d0d;color:#53FC18'>"
                            b"<h2>Bot autorizovan!</h2><p style='color:#aaa'>"
                            b"Toto okno muzete zavrit.</p></body></html>")
                    if not result["code"]:
                        body = body.replace(b"#53FC18", b"#ff4444").replace(
                            b"Bot autorizovan!", b"Autorizace selhala")
                    s.wfile.write(body)
                def log_message(s, *a): pass

            try:
                port = int(REDIRECT_URI.split(":")[-1].split("/")[0])
                srv = HTTPServer(("localhost", port), H)
                srv.timeout = 120
                self.log("Čekám na potvrzení v prohlížeči (max 2 min) ...", "info")
                srv.handle_request()
            except Exception as e:
                self.log(f"Chyba callback serveru: {e}", "error")
                on_done(False); return

            code = result.get("code", "")
            if not code:
                self.log("Kick neposlal autorizační kód!", "error")
                on_done(False); return

            try:
                resp = requests.post(KICK_TOKEN_URL, data={
                    "grant_type": "authorization_code", "client_id": client_id,
                    "client_secret": client_secret, "redirect_uri": REDIRECT_URI,
                    "code": code, "code_verifier": verifier,
                }, timeout=15)
                resp.raise_for_status()
                d = resp.json()
                self.tokens["access_token"]  = d["access_token"]
                self.tokens["refresh_token"] = d.get("refresh_token", "")
                self.tokens["expires_at"]    = time.time() + d.get("expires_in", 3600)
                self._save_tokens()
                self.log("✅ Přihlášení úspěšné! Token uložen.", "success")
                on_done(True)
            except Exception as e:
                self.log(f"Chyba výměny tokenu: {e}", "error")
                on_done(False)

        threading.Thread(target=run, daemon=True).start()

    def refresh_token(self, client_id, client_secret):
        if not self.tokens["refresh_token"]:
            return False
        try:
            resp = requests.post(KICK_TOKEN_URL, data={
                "grant_type": "refresh_token", "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": self.tokens["refresh_token"],
            }, timeout=15)
            if not resp.ok:
                return False
            d = resp.json()
            self.tokens["access_token"]  = d["access_token"]
            self.tokens["refresh_token"] = d.get("refresh_token", self.tokens["refresh_token"])
            self.tokens["expires_at"]    = time.time() + d.get("expires_in", 3600)
            self._save_tokens()
            self.log("Token automaticky obnoven.", "info")
            return True
        except Exception:
            return False

    def ensure_token(self, client_id, client_secret):
        if self._token_valid():
            return True
        return self.refresh_token(client_id, client_secret)

    # ── Kick REST ─────────────────────────────────────────────────────────────
    def get_channel_info(self, slug):
        try:
            r = cf_requests.get(f"https://kick.com/api/v2/channels/{slug}",
                                impersonate="chrome124", timeout=15)
            r.raise_for_status()
            d = r.json()
            return d["id"], d["chatroom"]["id"]
        except Exception as e:
            self.log(f"Kanál nenalezen: {e}", "error")
            return None, None

    def send_chat(self, message, client_id, client_secret):
        if not self.broadcaster_id:
            return
        if not self.ensure_token(client_id, client_secret):
            self.log("Nelze poslat zprávu — chybí token.", "error")
            return
        try:
            resp = requests.post(f"{KICK_API_URL}/chat",
                headers={"Authorization": f"Bearer {self.tokens['access_token']}",
                         "Content-Type": "application/json"},
                json={"broadcaster_user_id": self.broadcaster_id,
                      "content": message, "type": "bot"},
                timeout=10)
            if resp.ok:
                self.log(f"[Chat ✓] {message[:100]}", "success")
            else:
                self.log(f"Chat API chyba: {resp.status_code} | {resp.text[:100]}", "error")
        except Exception as e:
            self.log(f"Chyba odesílání: {e}", "error")

    # ── Moderátor ─────────────────────────────────────────────────────────────
    def is_moderator(self, sender):
        badges = sender.get("identity", {}).get("badges", [])
        return any(b.get("type", "").lower() in
                   {"moderator", "broadcaster", "editor", "og"} for b in badges)

    # ── Zpracování zpráv ──────────────────────────────────────────────────────
    def handle_message(self, sender, content, client_id, client_secret):
        text     = content.strip()
        lower    = text.lower()
        username = sender.get("username", "???")

        # ── Příkazy moderátora (fungují z jakékoliv fáze) ────────────────────
        if self.is_moderator(sender):
            if lower == self.CMD_START:
                if self.cgame.phase not in (CustomGame.IDLE, CustomGame.DONE):
                    self.send_chat(self._msg("std_probiha"), client_id, client_secret)
                else:
                    self.custom_start_registration(client_id, client_secret)
                return
            if lower == self.CMD_CLOSE:
                if self.cgame.phase == CustomGame.REGISTRATION:
                    self.custom_close_registration(client_id, client_secret)
                return
            if lower == self.CMD_STOP:
                if self.cgame.phase == CustomGame.IDLE:
                    self.send_chat(self._msg("std_zadna"), client_id, client_secret)
                else:
                    self.custom_stop_game(client_id, client_secret)
                return

        # ── Vlastní hra: registrace ──────────────────────────────────────────
        if self.cgame.phase == CustomGame.REGISTRATION:
            if text == "1":
                if self.cgame.register(username):
                    n = len(self.cgame.players)
                    self.log(f"  {username} se přihlásil/a ({n}. hráč)", "info")
                    self.send_chat(self._msg("vlast_prihlasen", username=username, n=n),
                                   client_id, client_secret)
                    if self.reg_update_cb:
                        self.reg_update_cb(list(self.cgame.players))
            return

        # ── Vlastní hra: střelba na střídačku ───────────────────────────────
        if self.cgame.phase == CustomGame.PLAYING:
            if lower == self.CMD_MAPA:
                self.send_chat(self.cgame.render_board_chat(), client_id, client_secret)
                return
            coord = self.cgame.parse_coord(text)
            if coord is not None:
                result = self.cgame.shoot(username, *coord)
                self._handle_custom_result(result, username, client_id, client_secret)
            return

        # ── Po skončení hry — !mapa ukáže výslednou mapu ────────────────────
        if lower == self.CMD_MAPA and self.cgame.phase == CustomGame.DONE:
            self.send_chat(self.cgame.render_board_chat(), client_id, client_secret)

    # ── Vlastní hra — engine metody ───────────────────────────────────────────
    def custom_start_registration(self, client_id, client_secret):
        self.cgame.start_registration()
        self.log("📋 Registrace zahájena", "info")
        self.status_cb("registration")
        if self.reg_update_cb:
            self.reg_update_cb([])
        self.send_chat(self._msg("vlast_reg_start"), client_id, client_secret)

    def custom_close_registration(self, client_id, client_secret) -> bool:
        if not self.cgame.close_registration():
            self.send_chat(self._msg("vlast_zadni_hraci"), client_id, client_secret)
            return False
        n    = len(self.cgame.players)
        rows = self.cgame.grid_rows
        cols = self.cgame.grid_cols
        rl   = self.cgame.rows_labels
        self.log(f"📋 Registrace uzavřena. {n} hráčů, pole {rows}×{cols}", "success")
        self.status_cb("placement")
        self.send_chat(
            self._msg("vlast_reg_uzavrena", n=n,
                      radky=f"{rl[0]}–{rl[-1]} × 1–{cols}",
                      celkem=rows * cols),
            client_id, client_secret
        )
        return True

    def custom_start_game(self, cells: set, client_id, client_secret) -> bool:
        if not self.cgame.set_ship_and_start(cells):
            return False
        first = self.cgame.current_player
        rl    = self.cgame.rows_labels
        self.log(f"▶ Vlastní hra zahájena. Loď má {len(cells)} polí.", "success")
        self.status_cb("custom_playing")
        self.board_cb(self.cgame)
        self.send_chat(
            self._msg("vlast_hra_start",
                      hraci=" → ".join(self.cgame.players),
                      pocet_poli=len(cells),
                      radky=f"{rl[0]}–{rl[-1]} × 1–{self.cgame.grid_cols}"),
            client_id, client_secret
        )
        self._ask_next(first, client_id, client_secret)
        return True

    def custom_stop_game(self, client_id, client_secret):
        self.cgame.phase = CustomGame.IDLE
        self.log("⏹ Vlastní hra zastavena", "warn")
        self.status_cb("idle")
        self.send_chat(self._msg("vlast_zastavena"), client_id, client_secret)
        if self.reg_update_cb:
            self.reg_update_cb([])

    def _ask_next(self, player, client_id, client_secret):
        left = self.cgame.hits_left()
        self.send_chat(
            self._msg("vlast_na_rade", username=player, zbyva=left,
                      zbyvajici_text=self._pole_text(left)),
            client_id, client_secret
        )
        if self.turn_cb:
            self.turn_cb(player)

    def _handle_custom_result(self, result, username, client_id, client_secret):
        t = result["type"]

        if t == "not_your_turn":
            return

        if t == "already_shot":
            self.send_chat(
                self._msg("vlast_jiz_strileno", username=username, coord=result["coord"]),
                client_id, client_secret
            )
            self._ask_next(self.cgame.current_player, client_id, client_secret)
            return

        coord = result["coord"]

        if t == "miss":
            self.log(f"  {username} → {coord} — minul/a", "dim")
            self.send_chat(self._msg("vlast_miss", username=username, coord=coord),
                           client_id, client_secret)

        elif t == "hit":
            left = self.cgame.hits_left()
            self.log(f"  {username} → {coord} — ZÁSAH! (zbývá {left})", "info")
            self.send_chat(
                self._msg("vlast_zasah", username=username, coord=coord,
                          zbyva=left, zbyvajici_text=self._pole_text(left)),
                client_id, client_secret
            )

        elif t == "game_over":
            self.log(f"  {username} → {coord} — POTOPIL/A! KONEC HRY!", "success")
            self.cgame.phase = CustomGame.DONE
            self.status_cb("done")
            self.board_cb(self.cgame)
            self.send_chat(
                self._msg("vlast_konec", username=username, coord=coord,
                          vystrely=len(self.cgame.shots)),
                client_id, client_secret
            )
            if self.reg_update_cb:
                self.reg_update_cb(list(self.cgame.players))
            return

        self.board_cb(self.cgame)
        next_p = self.cgame.current_player
        if next_p:
            self._ask_next(next_p, client_id, client_secret)
        if self.turn_cb:
            self.turn_cb(next_p or "")

    def _start_game(self, client_id, client_secret):
        try:
            self.game.new_game()
        except RuntimeError as e:
            self.send_chat(f"❌ Chyba při rozmísťování lodí: {e}", client_id, client_secret)
            return
        self.log("▶ Nová hra Lodě zahájena", "success")
        self.status_cb("playing")
        self.board_cb(self.game)
        self.scores_cb([])
        lode_str = " | ".join(f"{s['name']} ({s['size']}p +{s['bonus']}b)"
                              for s in self.game.ships)
        self.send_chat(self._msg("std_zahajena", lode=lode_str), client_id, client_secret)

    def _stop_game(self, client_id, client_secret):
        self.game.active = False
        st = self.game.stats()
        self.log(f"⏹ Hra zastavena. Výstřelů: {st['total']}, zásahů: {st['hits']}", "warn")
        self.status_cb("idle")
        self.send_chat(
            self._msg("std_zastavena", vystrely=st["total"], zasahy=st["hits"],
                      potopeno=st["sunk"], lodi=st["ships"]),
            client_id, client_secret
        )
        self._send_scores(client_id, client_secret)

    def _handle_result(self, result, username, client_id, client_secret):
        t = result["type"]
        coord = result["coord"]

        if t == "already_shot":
            self.send_chat(
                self._msg("std_jiz_strileno", username=username, coord=coord,
                          kdo=result["shot_by"]),
                client_id, client_secret
            )
            return

        self.board_cb(self.game)
        self.scores_cb(self.game.top_scores(20))

        if t == "miss":
            self.log(f"  {username} → {coord} — minul/a", "dim")

        elif t == "hit":
            pts = self.game.scores.get(username, 0)
            self.log(f"  {username} → {coord} — ZÁSAH! ({pts} b)", "info")
            self.send_chat(self._msg("std_zasah", username=username, coord=coord, body=pts),
                           client_id, client_secret)

        elif t == "sunk":
            ship = result["ship"]
            pts  = self.game.scores.get(username, 0)
            rem  = len(self.game.remaining_ships())
            self.log(f"  {username} → POTOPIL/A {ship['name']}! ({pts} b)", "success")
            self.send_chat(
                self._msg("std_potopeni", username=username, lod=ship["name"].upper(),
                          bonus=ship["bonus"], body=pts, zbyva=rem,
                          lodi_text=self._lodi_text(rem)),
                client_id, client_secret
            )

        elif t == "game_over":
            ship = result["ship"]
            st   = self.game.stats()
            self.log(f"  {username} → POTOPIL/A poslední loď! KONEC HRY!", "success")
            self.status_cb("done")
            self.send_chat(
                self._msg("std_konec", username=username, lod=ship["name"].upper(),
                          vystrely=st["total"]),
                client_id, client_secret
            )
            self._send_scores(client_id, client_secret)

    def _send_scores(self, client_id, client_secret):
        top = self.game.top_scores(10)
        if not top:
            self.send_chat(self._msg("std_zadne_zasahy"), client_id, client_secret)
            return
        medals = ["🥇", "🥈", "🥉"] + ["  "] * 10
        parts  = [f"{medals[i]} {u}: {p}b" for i, (u, p) in enumerate(top)]
        self.send_chat("🏆 SKÓRE: " + " | ".join(parts), client_id, client_secret)

    # ── WebSocket ─────────────────────────────────────────────────────────────
    def connect(self, slug, client_id, client_secret, on_connected):
        bid, cid = self.get_channel_info(slug)
        if not bid:
            on_connected(False); return
        self.broadcaster_id = bid
        self.chatroom_id    = cid
        if DEBUG:
            self.log(f"[DEBUG] broadcaster_id={bid}  chatroom_id={cid}", "info")

        def on_open(ws):
            ws.send(json.dumps({"event": "pusher:subscribe",
                                "data": {"auth": "", "channel": f"chatrooms.{cid}.v2"}}))
            self.log("✅ Připojeno k chatu!", "success")
            self.running = True
            self.status_cb("idle")
            self.send_chat(self._msg("bot_online"), client_id, client_secret)
            on_connected(True)

        def on_msg(ws, raw):
            try:
                outer = json.loads(raw)
            except Exception:
                return
            if outer.get("event") == "pusher:ping":
                ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                return
            if outer.get("event") != "App\\Events\\ChatMessageEvent":
                return
            rd = outer.get("data", "{}")
            d  = json.loads(rd) if isinstance(rd, str) else rd
            s, c = d.get("sender", {}), d.get("content", "")
            if s and c:
                self.handle_message(s, c, client_id, client_secret)

        def on_err(ws, err):
            self.log(f"WS chyba: {err}", "error")

        def on_close(ws, code, msg):
            self.running = False
            self.log("Odpojeno od chatu.", "warn")
            self.status_cb("disconnected")

        self.ws = websocket.WebSocketApp(PUSHER_WS,
            on_open=on_open, on_message=on_msg,
            on_error=on_err, on_close=on_close)
        self.ws_thread = threading.Thread(
            target=lambda: self.ws.run_forever(ping_interval=30, ping_timeout=10),
            daemon=True)
        self.ws_thread.start()

    def disconnect(self):
        if self.ws:
            self.ws.close()
        self.running = False

    def log(self, msg, level="info"):
        self.log_cb(msg, level)


# ════════════════════════════════════════════════════════════════════════════
#  Dialog pro umístění lodě moderátorem
# ════════════════════════════════════════════════════════════════════════════
class ShipPlacementDialog(ctk.CTkToplevel):
    CELL_SIZE = 28

    # (label, offsets from anchor = leftmost cell of the horizontal bar)
    # Shape: XXX + one cell up/down at left or right end
    SHAPES = [
        ("↑ vlevo",  [( 0,0),(0,1),(0,2),(-1,0)]),  # X·· / XXX
        ("↓ vlevo",  [( 0,0),(0,1),(0,2),( 1,0)]),  # XXX / X··
        ("↑ vpravo", [( 0,0),(0,1),(0,2),(-1,2)]),  # ··X / XXX
        ("↓ vpravo", [( 0,0),(0,1),(0,2),( 1,2)]),  # XXX / ··X
    ]

    def __init__(self, parent, cgame: CustomGame, on_confirm):
        super().__init__(parent)
        self.cgame      = cgame
        self.on_confirm = on_confirm
        self.anchor     = None   # (r, c) – leftmost cell of horizontal bar
        self.shape_idx  = 0

        rows = cgame.grid_rows
        cols = cgame.grid_cols
        rl   = cgame.rows_labels

        w = max(cols * self.CELL_SIZE + 80, 400)
        h = rows * self.CELL_SIZE + 220
        self.title("Umístění L-lodě")
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.configure(fg_color=DARK_BG)
        self.grab_set()

        ctk.CTkLabel(self,
            text="1. Vyber orientaci  2. Klikni na mřížce (levý kraj XXX)",
            font=ctk.CTkFont("", 12, "bold"), text_color=TEXT_BRIGHT
        ).pack(pady=(16, 8))

        # Shape selector
        shape_row = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=6)
        shape_row.pack(pady=(0, 6), padx=16, fill="x")
        self._shape_btns = []
        for i, (name, _) in enumerate(self.SHAPES):
            btn = ctk.CTkButton(
                shape_row, text=f"L {name}",
                fg_color=KICK_GREEN if i == 0 else "transparent",
                text_color="#000" if i == 0 else TEXT_MID,
                hover_color="#45d614",
                border_color=BORDER, border_width=1,
                font=ctk.CTkFont("", 11, "bold"), height=30, corner_radius=4,
                command=lambda idx=i: self._select_shape(idx)
            )
            btn.pack(side="left", padx=4, pady=6, expand=True, fill="x")
            self._shape_btns.append(btn)

        self.lbl_status = ctk.CTkLabel(self,
            text="Klikni na mřížce na levý kraj horizontální části lodě",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_status.pack(pady=(0, 6))

        # Grid
        grid_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=8)
        grid_frame.pack(padx=16, fill="both", expand=True)

        ctk.CTkLabel(grid_frame, text="  ", width=28, fg_color="transparent"
                     ).grid(row=0, column=0)
        for ci in range(cols):
            ctk.CTkLabel(grid_frame,
                text=str(ci + 1) if ci < 9 else "10",
                width=self.CELL_SIZE, font=ctk.CTkFont("Courier New", 10),
                text_color=TEXT_DIM, fg_color="transparent"
            ).grid(row=0, column=ci + 1, padx=1)

        self._btns = {}
        for ri in range(rows):
            ctk.CTkLabel(grid_frame, text=rl[ri], width=28,
                font=ctk.CTkFont("Courier New", 10, "bold"),
                text_color=TEXT_DIM, fg_color="transparent"
            ).grid(row=ri + 1, column=0)
            for ci in range(cols):
                btn = tk.Button(
                    grid_frame,
                    text="", width=2, height=1,
                    bg=PANEL_BG, activebackground=KICK_GREEN,
                    relief="flat", bd=1, highlightbackground=BORDER,
                    cursor="hand2",
                    command=lambda r=ri, c=ci: self._set_anchor(r, c)
                )
                btn.grid(row=ri + 1, column=ci + 1, padx=1, pady=1, ipadx=2, ipady=2)
                self._btns[(ri, ci)] = btn

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10, fill="x", padx=16)
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(btn_row, text="Zrušit",
            fg_color="transparent", border_color=BORDER, border_width=1,
            text_color=TEXT_MID, hover_color=CARD_BG,
            command=self.destroy
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_confirm = ctk.CTkButton(btn_row, text="✅  Spustit hru",
            fg_color=KICK_GREEN, text_color="#000", hover_color="#45d614",
            font=ctk.CTkFont("", 12, "bold"), state="disabled",
            command=self._confirm)
        self.btn_confirm.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _select_shape(self, idx):
        self.shape_idx = idx
        for i, btn in enumerate(self._shape_btns):
            sel = (i == idx)
            btn.configure(
                fg_color=KICK_GREEN if sel else "transparent",
                text_color="#000" if sel else TEXT_MID,
            )
        if self.anchor is not None:
            self._set_anchor(*self.anchor)

    def _get_cells(self, anchor_r, anchor_c):
        return [(anchor_r + dr, anchor_c + dc)
                for dr, dc in self.SHAPES[self.shape_idx][1]]

    def _cells_valid(self, cells):
        return all(0 <= r < self.cgame.grid_rows and 0 <= c < self.cgame.grid_cols
                   for r, c in cells)

    def _set_anchor(self, r, c):
        for btn in self._btns.values():
            btn.config(bg=PANEL_BG)
        self.anchor = (r, c)
        cells = self._get_cells(r, c)
        valid = self._cells_valid(cells)
        for cr, cc in cells:
            if 0 <= cr < self.cgame.grid_rows and 0 <= cc < self.cgame.grid_cols:
                self._btns[(cr, cc)].config(bg=KICK_GREEN if valid else "#663300")
        if valid:
            rl = self.cgame.rows_labels
            coords = ", ".join(f"{rl[cr]}{cc + 1}" for cr, cc in cells)
            self.lbl_status.configure(text=f"Loď: {coords}", text_color=KICK_GREEN)
            self.btn_confirm.configure(state="normal")
        else:
            self.lbl_status.configure(
                text="⚠️ Loď přesahuje mřížku — zvol jiné místo",
                text_color=RED_ERR)
            self.btn_confirm.configure(state="disabled")

    def _confirm(self):
        if self.anchor is not None and self.btn_confirm.cget("state") == "normal":
            cells = self._get_cells(*self.anchor)
            if self._cells_valid(cells):
                self.on_confirm(set(cells))
                self.destroy()


# ════════════════════════════════════════════════════════════════════════════
#  GUI
# ════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Kick Lodě Bot v{BUILD_VERSION}")
        self.geometry("1100x760")
        self.minsize(960, 700)
        self.configure(fg_color=DARK_BG)

        self._load_config()
        self.engine = LodeEngine(
            log_cb        = self._append_log,
            status_cb     = self._set_status,
            board_cb      = self._update_board,
            scores_cb     = self._update_scores,
            reg_update_cb = self._update_reg_list,
            turn_cb       = self._update_turn,
        )
        self._token_status = (
            "valid"   if self.engine._token_valid() else
            "refresh" if self.engine.tokens.get("refresh_token") else
            "none"
        )
        self._build_ui()
        self._refresh_token_label()
        self._draw_board(LodeGame())  # prázdná mřížka

    # ── Config ────────────────────────────────────────────────────────────────
    def _load_config(self):
        self._cfg = {"client_id": "", "client_secret": "", "channel": ""}
        if CONFIG_FILE.exists():
            try:
                self._cfg.update(json.loads(CONFIG_FILE.read_text()))
            except Exception:
                pass

    def _save_config(self):
        self._cfg["client_id"]     = self.entry_cid.get().strip()
        self._cfg["client_secret"] = self.entry_csecret.get().strip()
        self._cfg["channel"]       = self.entry_channel.get().strip()
        CONFIG_FILE.write_text(json.dumps(self._cfg, indent=2))

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, width=260)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(0, weight=1)

        # Scrollovatelný vnitřní panel — obsah se vejde i na malém okně
        inner = ctk.CTkScrollableFrame(sb, fg_color="transparent",
                                       scrollbar_button_color=BORDER,
                                       scrollbar_button_hover_color=TEXT_DIM)
        inner.grid(row=0, column=0, sticky="nsew")
        inner.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(inner, text="⚓ Lodě Bot", font=ctk.CTkFont("", 22, "bold"),
                     text_color=KICK_GREEN).grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        ctk.CTkLabel(inner, text="Multiplayer pro 40 hráčů", font=ctk.CTkFont("", 11),
                     text_color=TEXT_DIM).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")
        ctk.CTkFrame(inner, height=1, fg_color=BORDER).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 20))

        self._section(inner, "NASTAVENÍ", 3)
        self._label(inner, "Client ID", 4)
        self.entry_cid = self._entry(inner, 5, self._cfg["client_id"])
        self._label(inner, "Client Secret", 6)
        self.entry_csecret = self._entry(inner, 7, self._cfg["client_secret"], show="•")
        self._label(inner, "Název kanálu (slug)", 8)
        self.entry_channel = self._entry(inner, 9, self._cfg["channel"])

        self.lbl_token = ctk.CTkLabel(inner, text="", font=ctk.CTkFont("", 11),
                                      wraplength=210, justify="left")
        self.lbl_token.grid(row=10, column=0, padx=16, pady=(8, 4), sticky="w")

        auth_row = ctk.CTkFrame(inner, fg_color="transparent")
        auth_row.grid(row=11, column=0, padx=16, pady=(4, 16), sticky="ew")
        auth_row.grid_columnconfigure(0, weight=1)
        auth_row.grid_columnconfigure(1, weight=0)

        self.btn_auth = ctk.CTkButton(auth_row, text="🔑  Přihlásit bota",
            fg_color="#1e3a1e", hover_color="#2a4f2a", text_color=KICK_GREEN,
            border_color=KICK_GREEN, border_width=1,
            font=ctk.CTkFont("", 12, "bold"), height=38, corner_radius=8,
            command=self._do_auth)
        self.btn_auth.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_reset_login = ctk.CTkButton(auth_row, text="🗑",
            fg_color="#2a1a1a", hover_color="#3a2020", text_color="#ff6666",
            border_color="#ff4444", border_width=1,
            font=ctk.CTkFont("", 14), width=38, height=38, corner_radius=8,
            command=self._do_login_reset)
        self.btn_reset_login.grid(row=0, column=1, sticky="e")

        ctk.CTkFrame(inner, height=1, fg_color=BORDER).grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 20))

        self._section(inner, "PŘIPOJENÍ", 13)
        self.btn_connect = ctk.CTkButton(inner, text="▶  Spustit bota",
            fg_color=KICK_GREEN, hover_color="#45d614", text_color="#000",
            font=ctk.CTkFont("", 13, "bold"), height=44, corner_radius=8,
            command=self._do_connect)
        self.btn_connect.grid(row=14, column=0, padx=16, pady=(8, 6), sticky="ew")

        self.btn_disconnect = ctk.CTkButton(inner, text="⏹  Odpojit",
            fg_color="#2a1a1a", hover_color="#3a2020", text_color="#ff6666",
            border_color="#ff4444", border_width=1,
            font=ctk.CTkFont("", 12), height=36, corner_radius=8,
            state="disabled", command=self._do_disconnect)
        self.btn_disconnect.grid(row=15, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.lbl_status = ctk.CTkLabel(inner, text="⚪ Odpojeno",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_status.grid(row=16, column=0, padx=16, pady=(0, 8), sticky="w")

        ctk.CTkFrame(inner, height=1, fg_color=BORDER).grid(row=17, column=0, sticky="ew", padx=16, pady=(4, 16))

        # Pravidla — rychlý přehled
        self._section(inner, "PŘÍKAZY V CHATU", 18)
        rules = [
            ("!start",  "mod — zahájit registraci"),
            ("!close",  "mod — uzavřít registraci"),
            ("!stop",   "mod — zastavit hru"),
            ("!mapa",   "zobrazit mapu"),
            ("1",       "hráč — přihlásit se do hry"),
            ("A5, B3",  "hráč — střelba (na tahu)"),
        ]
        for i, (cmd, desc) in enumerate(rules):
            rf = ctk.CTkFrame(inner, fg_color="transparent")
            rf.grid(row=19 + i, column=0, padx=16, pady=1, sticky="ew")
            rf.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(rf, text=cmd, font=ctk.CTkFont("Courier New", 11, "bold"),
                         text_color=KICK_GREEN, width=60, anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(rf, text=desc, font=ctk.CTkFont("", 10),
                         text_color=TEXT_DIM, anchor="w"
                         ).grid(row=0, column=1, padx=(6, 0), sticky="w")

        ctk.CTkFrame(inner, height=1, fg_color=BORDER).grid(row=24, column=0, sticky="ew", padx=16, pady=(12, 8))

        self._section(inner, "TEXTY BOTA", 25)
        ctk.CTkButton(inner, text="✏️  Upravit texty",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_MID,
            border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 11), height=32, corner_radius=6,
            command=self._open_bot_config
        ).grid(row=26, column=0, padx=16, pady=(4, 4), sticky="ew")

        ctk.CTkButton(inner, text="🔄  Načíst změny konfigurace",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_MID,
            border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 11), height=32, corner_radius=6,
            command=self._reload_bot_config
        ).grid(row=27, column=0, padx=16, pady=(0, 8), sticky="ew")

        ctk.CTkFrame(inner, height=1, fg_color=BORDER).grid(row=28, column=0, sticky="ew", padx=16, pady=(4, 8))

        ctk.CTkButton(inner, text="❓ Kick Developer Settings",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), height=28, anchor="w",
            command=lambda: webbrowser.open("https://kick.com/settings/developer")
        ).grid(row=29, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=2)
        main.grid_rowconfigure(2, weight=1)

        # Banner
        self.banner = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12, height=64)
        self.banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 8))
        self.banner.grid_propagate(False)
        self.banner.grid_columnconfigure(1, weight=1)
        self.banner_icon = ctk.CTkLabel(self.banner, text="⚓", font=ctk.CTkFont("", 28))
        self.banner_icon.grid(row=0, column=0, padx=(20, 12), pady=12)
        self.banner_text = ctk.CTkLabel(self.banner, text="Bot je odpojený",
            font=ctk.CTkFont("", 16, "bold"), text_color=TEXT_MID, anchor="w")
        self.banner_text.grid(row=0, column=1, sticky="w")
        self.banner_sub = ctk.CTkLabel(self.banner,
            text="Vyplň nastavení a klikni Spustit bota",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM, anchor="e")
        self.banner_sub.grid(row=0, column=2, padx=20, sticky="e")

        # Herní mřížka (levý panel)
        bf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        bf.grid(row=1, column=0, sticky="nsew", padx=(20, 6), pady=(0, 8))
        bf.grid_columnconfigure(0, weight=1)
        bf.grid_rowconfigure(1, weight=2)
        bf.grid_rowconfigure(4, weight=1)

        bh = ctk.CTkFrame(bf, fg_color="transparent")
        bh.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        bh.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bh, text="Herní mřížka",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        self.lbl_shots = ctk.CTkLabel(bh, text="",
                     font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_shots.grid(row=0, column=1, sticky="e")

        board_container = ctk.CTkFrame(bf, fg_color="transparent")
        board_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        self.board_text = tk.Text(
            board_container,
            bg=CARD_BG, fg=TEXT_MID,
            font=("Courier New", 14, "bold"),
            state="disabled", relief="flat", bd=0,
            highlightthickness=0, selectbackground=CARD_BG,
            width=24, height=12,
        )
        self.board_text.pack(fill="both", expand=True)
        self.board_text.tag_configure("header",  foreground=TEXT_DIM)
        self.board_text.tag_configure("empty",   foreground="#333333")
        self.board_text.tag_configure("hit",     foreground="#ff4444")
        self.board_text.tag_configure("miss",    foreground="#334466")
        self.board_text.tag_configure("rowlbl",  foreground=TEXT_DIM)
        self.board_text.tag_configure("sunk",    foreground="#ff8800")

        ctk.CTkFrame(bf, height=1, fg_color=BORDER).grid(
            row=2, column=0, sticky="ew", padx=12, pady=(0, 6))

        shot_hdr = ctk.CTkFrame(bf, fg_color="transparent")
        shot_hdr.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 4))
        shot_hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(shot_hdr, text="Výstřely",
            font=ctk.CTkFont("", 12, "bold"), text_color=TEXT_BRIGHT
        ).grid(row=0, column=0, sticky="w")
        self.lbl_shot_count = ctk.CTkLabel(shot_hdr, text="",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_shot_count.grid(row=0, column=1, sticky="e")

        self.shot_scroll = ctk.CTkScrollableFrame(bf, fg_color="transparent",
            scrollbar_button_color=BORDER)
        self.shot_scroll.grid(row=4, column=0, sticky="nsew", padx=6, pady=(0, 10))
        self.shot_scroll.grid_columnconfigure(0, weight=1)
        self._shot_rows = []

        # Pravý panel — ovládání hry + hráči
        rf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        rf.grid(row=1, column=1, sticky="nsew", padx=(6, 20), pady=(0, 8))
        rf.grid_columnconfigure(0, weight=1)
        rf.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(rf, text="OVLÁDÁNÍ HRY",
            font=ctk.CTkFont("", 10, "bold"), text_color=TEXT_DIM
        ).grid(row=0, column=0, padx=14, pady=(14, 6), sticky="w")

        self.btn_reg_start = ctk.CTkButton(rf, text="🎮  Zahájit registraci",
            fg_color="#1a2a3a", hover_color="#223344", text_color="#66aaff",
            border_color="#336699", border_width=1,
            font=ctk.CTkFont("", 13, "bold"), height=40, corner_radius=8,
            command=self._do_custom_reg_start)
        self.btn_reg_start.grid(row=1, column=0, padx=12, pady=(0, 5), sticky="ew")

        self.btn_reg_close = ctk.CTkButton(rf, text="🔒  Uzavřít registraci (0 hráčů)",
            fg_color="transparent", hover_color=CARD_BG,
            text_color=TEXT_DIM, border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 12), height=40, corner_radius=8,
            state="disabled", command=self._do_custom_reg_close)
        self.btn_reg_close.grid(row=2, column=0, padx=12, pady=(0, 5), sticky="ew")

        self.btn_place_ship = ctk.CTkButton(rf, text="🗺  Umístit loď",
            fg_color="transparent", hover_color=CARD_BG,
            text_color=TEXT_DIM, border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 12), height=40, corner_radius=8,
            state="disabled", command=self._do_custom_place_ship)
        self.btn_place_ship.grid(row=3, column=0, padx=12, pady=(0, 5), sticky="ew")

        self.btn_custom_stop = ctk.CTkButton(rf, text="⏹  Zastavit hru",
            fg_color="#2a1a1a", hover_color="#3a2020",
            text_color="#ff6666", border_color="#ff4444", border_width=1,
            font=ctk.CTkFont("", 12), height=40, corner_radius=8,
            state="disabled", command=self._do_custom_stop)
        self.btn_custom_stop.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkFrame(rf, height=1, fg_color=BORDER).grid(
            row=5, column=0, sticky="ew", padx=12, pady=(0, 8))

        self.lbl_turn = ctk.CTkLabel(rf, text="",
            font=ctk.CTkFont("", 13, "bold"), text_color=KICK_GREEN)
        self.lbl_turn.grid(row=6, column=0, padx=14, pady=(0, 8), sticky="w")

        ctk.CTkFrame(rf, height=1, fg_color=BORDER).grid(
            row=7, column=0, sticky="ew", padx=12, pady=(0, 6))

        reg_hdr = ctk.CTkFrame(rf, fg_color="transparent")
        reg_hdr.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 4))
        reg_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(reg_hdr, text="PŘIHLÁŠENÍ HRÁČI",
            font=ctk.CTkFont("", 10, "bold"), text_color=TEXT_DIM
        ).grid(row=0, column=0, sticky="w")
        self.lbl_player_count = ctk.CTkLabel(reg_hdr, text="0 hráčů",
            font=ctk.CTkFont("", 10), text_color=TEXT_DIM)
        self.lbl_player_count.grid(row=0, column=1, sticky="e")

        self.players_scroll = ctk.CTkScrollableFrame(rf, fg_color="transparent",
            scrollbar_button_color=BORDER)
        self.players_scroll.grid(row=9, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self.players_scroll.grid_columnconfigure(0, weight=1)
        self._player_rows = []

        # Log
        lf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 20))
        lf.grid_columnconfigure(0, weight=1)
        lf.grid_rowconfigure(1, weight=1)
        lhdr = ctk.CTkFrame(lf, fg_color="transparent")
        lhdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        lhdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(lhdr, text="Protokol",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(lhdr, text="Vymazat", width=70, height=24,
            fg_color="transparent", hover_color=BORDER, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), command=self._clear_log
            ).grid(row=0, column=1, sticky="e")
        self.log_box = ctk.CTkTextbox(lf, fg_color="transparent",
            font=ctk.CTkFont("Courier New", 11), text_color=TEXT_MID,
            wrap="word", scrollbar_button_color=BORDER)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("", 10, "bold"),
                     text_color=TEXT_DIM).grid(row=row, column=0, padx=16, pady=(0, 4), sticky="w")

    def _label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("", 12),
                     text_color=TEXT_MID).grid(row=row, column=0, padx=16, pady=(8, 2), sticky="w")

    def _entry(self, parent, row, default="", show=""):
        e = ctk.CTkEntry(parent, fg_color=CARD_BG, border_color=BORDER,
                         text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 12),
                         height=34, corner_radius=6, show=show)
        e.insert(0, default)
        e.grid(row=row, column=0, padx=16, pady=(0, 4), sticky="ew")
        return e

    def _refresh_token_label(self):
        if self._token_status == "valid":
            self.lbl_token.configure(text="✅ Bot je přihlášen", text_color=KICK_GREEN)
        elif self._token_status == "refresh":
            self.lbl_token.configure(text="🔄 Token bude obnoven automaticky", text_color=YELLOW_WARN)
        else:
            self.lbl_token.configure(text="⚠️ Bot není přihlášen — klikni níže", text_color=YELLOW_WARN)

    # ── Akce tlačítek ─────────────────────────────────────────────────────────
    def _do_auth(self):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        if not cid or not cs:
            self._append_log("Vyplň Client ID a Client Secret!", "error"); return
        self._save_config()
        self.btn_auth.configure(state="disabled", text="⏳ Čekám na prohlížeč ...")
        def done(ok):
            self.after(0, lambda: self.btn_auth.configure(state="normal", text="🔑  Přihlásit bota"))
            if ok:
                self._token_status = "valid"
                self.after(0, self._refresh_token_label)
        self.engine.do_oauth(cid, cs, done)

    def _do_login_reset(self):
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self.engine.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._token_status = "none"
        self._refresh_token_label()
        self._append_log("Token smazán. Klikni na Přihlásit bota.", "warn")

    def _do_connect(self):
        cid     = self.entry_cid.get().strip()
        cs      = self.entry_csecret.get().strip()
        channel = self.entry_channel.get().strip().lower()
        if not cid or not cs:
            self._append_log("Vyplň Client ID a Client Secret.", "error"); return
        if not channel:
            self._append_log("Vyplň název kanálu.", "error"); return
        if not self.engine._token_valid() and not self.engine.tokens.get("refresh_token"):
            self._append_log("Nejdřív přihlas bota tlačítkem 🔑 Přihlásit bota.", "error"); return
        self._save_config()
        self.btn_connect.configure(state="disabled", text="⏳ Připojuji ...")
        def connected(ok):
            if ok:
                self.after(0, lambda: self.btn_connect.configure(state="disabled", text="▶  Spustit bota"))
                self.after(0, lambda: self.btn_disconnect.configure(state="normal"))
            else:
                self.after(0, lambda: self.btn_connect.configure(state="normal", text="▶  Spustit bota"))
                self._append_log("Připojení selhalo.", "error")
        self.engine.connect(channel, cid, cs, connected)

    def _do_disconnect(self):
        self.engine.disconnect()
        self.btn_connect.configure(state="normal", text="▶  Spustit bota")
        self.btn_disconnect.configure(state="disabled")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _append_log(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        def _insert():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts}] {msg}\n")
            self.log_box.configure(state="disabled")
            self.log_box.see("end")
        self.after(0, _insert)

    def _set_status(self, status):
        configs = {
            "idle":           ("⚓", "Bot je online",        "Moderátor zadá !start pro registraci",        KICK_GREEN),
            "registration":   ("📋", "Registrace otevřena!", "Hráči píší 1 do chatu  •  !close uzavře",    "#66aaff"),
            "placement":      ("🗺", "Uzavřeno — umísti loď", "Klikni 🗺 Umístit loď vpravo",              YELLOW_WARN),
            "custom_playing": ("🎯", "Hra probíhá!",          "Hráči se střídají — bot se ptá",             "#ff4444"),
            "done":           ("🏆", "Hra skončila!",         "Moderátor zadá !start pro novou hru",        KICK_GREEN),
            "disconnected":   ("⚪", "Odpojeno",              "Klikni na Spustit bota",                     TEXT_DIM),
        }
        icon, title, sub, color = configs.get(status, ("⚪", status, "", TEXT_DIM))
        dot = {
            "idle":           "🟢 Online",
            "registration":   "🔵 Registrace",
            "placement":      "🟡 Umísťování",
            "custom_playing": "🔴 Hra probíhá",
            "done":           "🏆 Hotovo",
            "disconnected":   "⚪ Odpojeno",
        }.get(status, status)

        def _update():
            self.banner_icon.configure(text=icon)
            self.banner_text.configure(text=title, text_color=color)
            self.banner_sub.configure(text=sub)
            self.lbl_status.configure(text=dot)

            if status in ("idle", "done"):
                self.btn_reg_start.configure(state="normal")
                self.btn_reg_close.configure(state="disabled")
                self.btn_place_ship.configure(state="disabled")
                self.btn_custom_stop.configure(state="disabled")
            elif status == "registration":
                self.btn_reg_start.configure(state="disabled")
                self.btn_reg_close.configure(state="normal")
                self.btn_place_ship.configure(state="disabled")
                self.btn_custom_stop.configure(state="normal")
            elif status == "placement":
                self.btn_reg_start.configure(state="disabled")
                self.btn_reg_close.configure(state="disabled")
                self.btn_place_ship.configure(state="normal")
                self.btn_custom_stop.configure(state="normal")
                self.after(150, self._do_custom_place_ship)  # auto-otevřít dialog
            elif status == "custom_playing":
                self.btn_reg_start.configure(state="disabled")
                self.btn_reg_close.configure(state="disabled")
                self.btn_place_ship.configure(state="disabled")
                self.btn_custom_stop.configure(state="normal")
            elif status == "disconnected":
                self.btn_reg_start.configure(state="disabled")
                self.btn_reg_close.configure(state="disabled")
                self.btn_place_ship.configure(state="disabled")
                self.btn_custom_stop.configure(state="disabled")

        self.after(0, _update)

    # ── Vlastní hra — akce tlačítek ───────────────────────────────────────────
    def _do_custom_reg_start(self):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        if not self.engine.running:
            self._append_log("Bot není připojen.", "error"); return
        self.engine.custom_start_registration(cid, cs)

    def _do_custom_reg_close(self):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine.custom_close_registration(cid, cs)

    def _do_custom_place_ship(self):
        if not self.engine.cgame.players:
            self._append_log("Nejdřív zaregistruj hráče.", "error"); return
        ShipPlacementDialog(self, self.engine.cgame, self._on_ship_placed)

    def _on_ship_placed(self, cells: set):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine.custom_start_game(cells, cid, cs)

    def _do_custom_stop(self):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine.custom_stop_game(cid, cs)
        self.lbl_turn.configure(text="")

    def _update_reg_list(self, players: list):
        def _upd():
            n = len(players)
            self.lbl_player_count.configure(text=f"{n} hráčů")
            self.btn_reg_close.configure(text=f"🔒  Uzavřít registraci ({n} hráčů)")
            for w in self._player_rows:
                w.destroy()
            self._player_rows.clear()
            if players:
                for i, p in enumerate(players):
                    lbl = ctk.CTkLabel(self.players_scroll,
                        text=f"{i + 1}. {p}",
                        font=ctk.CTkFont("", 11), text_color=TEXT_BRIGHT, anchor="w")
                    lbl.grid(row=i, column=0, padx=8, pady=1, sticky="w")
                    self._player_rows.append(lbl)
            else:
                lbl = ctk.CTkLabel(self.players_scroll,
                    text="Čekám… hráči píší 1 do chatu",
                    font=ctk.CTkFont("", 11), text_color=TEXT_DIM, anchor="w")
                lbl.grid(row=0, column=0, padx=8, pady=4, sticky="w")
                self._player_rows.append(lbl)
        self.after(0, _upd)

    def _update_turn(self, current_player: str):
        def _upd():
            if current_player:
                self.lbl_turn.configure(text=f"Na tahu: @{current_player}")
            else:
                self.lbl_turn.configure(text="")
        self.after(0, _upd)

    def _update_board(self, game):
        if isinstance(game, CustomGame):
            self.after(0, lambda: self._draw_custom_board(game))
        else:
            self.after(0, lambda: self._draw_board(game))

    def _draw_board(self, game: LodeGame):
        # Zjistíme sunk cells pro oranžovou barvu
        sunk_cells = set()
        for ship in game.ships:
            if ship["sunk"]:
                sunk_cells |= ship["cells"]

        t = self.board_text
        t.configure(state="normal")
        t.delete("1.0", "end")

        # Záhlaví
        t.insert("end", "   ", "header")
        for c in range(1, 11):
            t.insert("end", str(c % 10), "header")
        t.insert("end", "\n")

        for ri, row in enumerate(ROWS):
            t.insert("end", f"{row}: ", "rowlbl")
            for ci in range(10):
                coord = (ri, ci)
                shot  = game.shots.get(coord)
                if shot is None:
                    t.insert("end", "·", "empty")
                elif not shot["hit"]:
                    t.insert("end", "○", "miss")
                elif coord in sunk_cells:
                    t.insert("end", "█", "sunk")
                else:
                    t.insert("end", "X", "hit")
            t.insert("end", "\n")

        t.configure(state="disabled")

        st = game.stats()
        if st["total"] > 0:
            self.lbl_shots.configure(
                text=f"výstřelů: {st['total']}  zásahů: {st['hits']}  potopeno: {st['sunk']}/{st['ships']}"
            )
        else:
            self.lbl_shots.configure(text="")

    def _draw_custom_board(self, cgame: CustomGame):
        rl   = cgame.rows_labels
        cols = cgame.grid_cols

        t = self.board_text
        t.configure(state="normal")
        t.delete("1.0", "end")

        t.insert("end", "   ", "header")
        for c in range(1, cols + 1):
            t.insert("end", str(c % 10), "header")
        t.insert("end", "\n")

        for ri in range(cgame.grid_rows):
            t.insert("end", f"{rl[ri]}: ", "rowlbl")
            for ci in range(cols):
                shot = cgame.shots.get((ri, ci))
                if shot is None:
                    t.insert("end", "·", "empty")
                elif shot["hit"]:
                    t.insert("end", "X", "hit")
                else:
                    t.insert("end", "○", "miss")
            t.insert("end", "\n")

        t.configure(state="disabled")

        total = len(cgame.shots)
        hits  = sum(1 for s in cgame.shots.values() if s["hit"])
        left  = cgame.hits_left()
        if total > 0:
            self.lbl_shots.configure(
                text=f"výstřelů: {total}  zásahů: {hits}  zbývá: {left}"
            )
        else:
            self.lbl_shots.configure(text="")

        # Shot history list
        for w in self._shot_rows:
            w.destroy()
        self._shot_rows.clear()

        shots_list = list(cgame.shots.items())
        self.lbl_shot_count.configure(
            text=f"{total} výstřelů  •  {hits} zásahů" if total else ""
        )
        for i, ((r, c), data) in enumerate(shots_list):
            coord_str = f"{rl[r]}{c + 1}"
            hit  = data["hit"]
            user = data["username"]

            bg  = CARD_BG if i % 2 == 0 else PANEL_BG
            row = ctk.CTkFrame(self.shot_scroll, fg_color=bg, corner_radius=3, height=22)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=1)
            row.grid_columnconfigure(1, weight=1)
            row.grid_propagate(False)

            ctk.CTkLabel(row, text=coord_str,
                font=ctk.CTkFont("Courier New", 11, "bold"),
                text_color="#ff4444" if hit else "#4466aa",
                width=34, anchor="w"
            ).grid(row=0, column=0, padx=(6, 2), pady=2, sticky="w")

            ctk.CTkLabel(row, text=f"@{user}",
                font=ctk.CTkFont("", 11),
                text_color=TEXT_BRIGHT if hit else TEXT_DIM,
                anchor="w"
            ).grid(row=0, column=1, padx=2, pady=2, sticky="w")

            ctk.CTkLabel(row, text="✓" if hit else "✗",
                font=ctk.CTkFont("", 11, "bold"),
                text_color="#ff4444" if hit else TEXT_DIM,
                width=20, anchor="e"
            ).grid(row=0, column=2, padx=(2, 6), pady=2, sticky="e")

            self._shot_rows.append(row)

        # Auto-scroll to latest shot
        if self._shot_rows:
            self.shot_scroll._parent_canvas.yview_moveto(1.0)

    def _update_scores(self, rows):
        pass  # custom game has no score system

    def _open_bot_config(self):
        cfg_path = LODE_BOT_CONFIG_FILE.resolve()
        if not cfg_path.exists():
            self.engine.reload_config()  # ensures file is created
        try:
            os.startfile(str(cfg_path))
        except Exception as e:
            self._append_log(f"Nelze otevřít soubor: {e}", "error")

    def _reload_bot_config(self):
        self.engine.reload_config()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def on_closing(self):
        self.engine.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
