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

import os, sys, json, re, time, hashlib, base64, secrets, webbrowser, threading, random
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from pathlib import Path
from datetime import datetime
import tkinter as tk

import customtkinter as ctk
import requests
from curl_cffi import requests as cf_requests
import websocket

BUILD_VERSION = "0.1.0"
DEBUG = False

KICK_AUTH_URL  = "https://id.kick.com/oauth/authorize"
KICK_TOKEN_URL = "https://id.kick.com/oauth/token"
KICK_API_URL   = "https://api.kick.com/public/v1"
KICK_SCOPES    = "user:read chat:write"
PUSHER_WS      = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
                  "?protocol=7&client=js&version=8.4.0-rc2&flash=false")
REDIRECT_URI   = "http://localhost:7878/callback"
TOKEN_FILE     = Path("kick_tokens.json")
CONFIG_FILE    = Path("kick_lode_config.json")

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
#  Bot engine
# ════════════════════════════════════════════════════════════════════════════
class LodeEngine:
    CMD_START = "!start"
    CMD_STOP  = "!stop"
    CMD_MAPA  = "!mapa"
    CMD_SKORE = "!skore"

    def __init__(self, log_cb, status_cb, board_cb, scores_cb):
        self.log_cb    = log_cb
        self.status_cb = status_cb
        self.board_cb  = board_cb
        self.scores_cb = scores_cb

        self.game           = LodeGame()
        self.broadcaster_id = 0
        self.chatroom_id    = 0
        self.ws             = None
        self.ws_thread      = None
        self.running        = False

        self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._load_tokens()

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

        if self.is_moderator(sender):
            if lower == self.CMD_START:
                if self.game.active:
                    self.send_chat("⚠️ Hra už probíhá! Zastav ji příkazem !stop.", client_id, client_secret)
                else:
                    self._start_game(client_id, client_secret)
                return
            if lower == self.CMD_STOP:
                if not self.game.active:
                    self.send_chat("⚠️ Žádná hra neprobíhá.", client_id, client_secret)
                else:
                    self._stop_game(client_id, client_secret)
                return

        if lower == self.CMD_MAPA:
            if self.game.active or self.game.finished:
                self.send_chat(self.game.render_board_chat(), client_id, client_secret)
            else:
                self.send_chat("⚠️ Žádná hra neprobíhá. Moderátor zadá !start.", client_id, client_secret)
            return

        if lower == self.CMD_SKORE:
            self._send_scores(client_id, client_secret)
            return

        if self.game.active:
            coord = self.game.parse_coord(text)
            if coord is not None:
                result = self.game.shoot(username, *coord)
                self._handle_result(result, username, client_id, client_secret)

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
        ships_str = " | ".join(
            f"{s['name']} ({s['size']}p +{s['bonus']}b)" for s in self.game.ships
        )
        self.send_chat(
            f"⚓ LODĚ ZAHÁJENA! Mřížka A–J × 1–10. "
            f"Střílej souřadnicí do chatu, např. A5 nebo J10. "
            f"Zásah=+1 bod, potopení=bonus. "
            f"Příkazy: !mapa !skore | "
            f"Lodě: {ships_str}",
            client_id, client_secret
        )

    def _stop_game(self, client_id, client_secret):
        self.game.active = False
        st = self.game.stats()
        self.log(f"⏹ Hra zastavena. Výstřelů: {st['total']}, zásahů: {st['hits']}", "warn")
        self.status_cb("idle")
        self.send_chat(
            f"🛑 Hra zastavena moderátorem. "
            f"Výstřelů: {st['total']}, zásahů: {st['hits']}, "
            f"potopeno: {st['sunk']}/{st['ships']} lodí.",
            client_id, client_secret
        )
        self._send_scores(client_id, client_secret)

    def _handle_result(self, result, username, client_id, client_secret):
        t = result["type"]
        coord = result["coord"]

        if t == "already_shot":
            self.send_chat(
                f"⚠️ @{username} pole {coord} už střílel/a @{result['shot_by']}",
                client_id, client_secret
            )
            return

        self.board_cb(self.game)
        self.scores_cb(self.game.top_scores(20))

        if t == "miss":
            self.log(f"  {username} → {coord} — minul/a", "dim")
            # Miss se v chatu neoznamuje — chat by byl přeplněný při 40 hráčích

        elif t == "hit":
            pts = self.game.scores.get(username, 0)
            self.log(f"  {username} → {coord} — ZÁSAH! ({pts} b)", "info")
            self.send_chat(
                f"💥 @{username} zasáhl/a {coord}! +1 bod ({pts} celkem)",
                client_id, client_secret
            )

        elif t == "sunk":
            ship = result["ship"]
            pts  = self.game.scores.get(username, 0)
            rem  = len(self.game.remaining_ships())
            suffix = "loď" if rem == 1 else ("lodě" if 2 <= rem <= 4 else "lodí")
            self.log(f"  {username} → POTOPIL/A {ship['name']}! ({pts} b)", "success")
            self.send_chat(
                f"🔥 @{username} POTOPIL/A {ship['name'].upper()}! "
                f"+{ship['bonus']} bonusových bodů! ({pts} celkem) "
                f"Zbývá {rem} {suffix}.",
                client_id, client_secret
            )

        elif t == "game_over":
            ship = result["ship"]
            pts  = self.game.scores.get(username, 0)
            st   = self.game.stats()
            self.log(f"  {username} → POTOPIL/A poslední loď! KONEC HRY!", "success")
            self.status_cb("done")
            self.send_chat(
                f"🏆 @{username} POTOPIL/A {ship['name'].upper()} a vyhrál/a hru! "
                f"Všechny lodě jsou na dně! Celkem výstřelů: {st['total']}.",
                client_id, client_secret
            )
            self._send_scores(client_id, client_secret)

    def _send_scores(self, client_id, client_secret):
        top = self.game.top_scores(10)
        if not top:
            self.send_chat("📊 Zatím nikdo nic nezasáhl.", client_id, client_secret)
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
            self.send_chat(
                "⚓ Lodě bot je online! Moderátor zadá !start pro zahájení hry. "
                "Příkazy: !mapa !skore",
                client_id, client_secret
            )
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
            log_cb    = self._append_log,
            status_cb = self._set_status,
            board_cb  = self._update_board,
            scores_cb = self._update_scores,
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

        ctk.CTkLabel(sb, text="⚓ Lodě Bot", font=ctk.CTkFont("", 22, "bold"),
                     text_color=KICK_GREEN).grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        ctk.CTkLabel(sb, text="Multiplayer pro 40 hráčů", font=ctk.CTkFont("", 11),
                     text_color=TEXT_DIM).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 20))

        self._section(sb, "NASTAVENÍ", 3)
        self._label(sb, "Client ID", 4)
        self.entry_cid = self._entry(sb, 5, self._cfg["client_id"])
        self._label(sb, "Client Secret", 6)
        self.entry_csecret = self._entry(sb, 7, self._cfg["client_secret"], show="•")
        self._label(sb, "Název kanálu (slug)", 8)
        self.entry_channel = self._entry(sb, 9, self._cfg["channel"])

        self.lbl_token = ctk.CTkLabel(sb, text="", font=ctk.CTkFont("", 11),
                                      wraplength=210, justify="left")
        self.lbl_token.grid(row=10, column=0, padx=16, pady=(8, 4), sticky="w")

        auth_row = ctk.CTkFrame(sb, fg_color="transparent")
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

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 20))

        self._section(sb, "PŘIPOJENÍ", 13)
        self.btn_connect = ctk.CTkButton(sb, text="▶  Spustit bota",
            fg_color=KICK_GREEN, hover_color="#45d614", text_color="#000",
            font=ctk.CTkFont("", 13, "bold"), height=44, corner_radius=8,
            command=self._do_connect)
        self.btn_connect.grid(row=14, column=0, padx=16, pady=(8, 6), sticky="ew")

        self.btn_disconnect = ctk.CTkButton(sb, text="⏹  Odpojit",
            fg_color="#2a1a1a", hover_color="#3a2020", text_color="#ff6666",
            border_color="#ff4444", border_width=1,
            font=ctk.CTkFont("", 12), height=36, corner_radius=8,
            state="disabled", command=self._do_disconnect)
        self.btn_disconnect.grid(row=15, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.lbl_status = ctk.CTkLabel(sb, text="⚪ Odpojeno",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_status.grid(row=16, column=0, padx=16, pady=(0, 8), sticky="w")

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).grid(row=17, column=0, sticky="ew", padx=16, pady=(4, 16))

        # Pravidla — rychlý přehled
        self._section(sb, "PŘÍKAZY V CHATU", 18)
        rules = [
            ("!start",  "mod — zahájit hru"),
            ("!stop",   "mod — zastavit hru"),
            ("!mapa",   "zobrazit mapu"),
            ("!skore",  "žebříček"),
            ("A5, J10", "hráč — střelba"),
        ]
        for i, (cmd, desc) in enumerate(rules):
            rf = ctk.CTkFrame(sb, fg_color="transparent")
            rf.grid(row=19 + i, column=0, padx=16, pady=1, sticky="ew")
            rf.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(rf, text=cmd, font=ctk.CTkFont("Courier New", 11, "bold"),
                         text_color=KICK_GREEN, width=60, anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(rf, text=desc, font=ctk.CTkFont("", 10),
                         text_color=TEXT_DIM, anchor="w"
                         ).grid(row=0, column=1, padx=(6, 0), sticky="w")

        sb.grid_rowconfigure(25, weight=1)

        ctk.CTkButton(sb, text="❓ Kick Developer Settings",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), height=28, anchor="w",
            command=lambda: webbrowser.open("https://kick.com/settings/developer")
        ).grid(row=26, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)
        main.grid_rowconfigure(3, weight=1)

        # Banner
        self.banner = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12, height=64)
        self.banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 12))
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

        # Herní mřížka
        bf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        bf.grid(row=1, column=0, sticky="nsew", padx=(20, 6), pady=(0, 12))
        bf.grid_columnconfigure(0, weight=1)
        bf.grid_rowconfigure(1, weight=1)
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
        board_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

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

        # Panel lodí + žebříček
        rf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        rf.grid(row=1, column=1, sticky="nsew", padx=(6, 20), pady=(0, 12))
        rf.grid_columnconfigure(0, weight=1)
        rf.grid_rowconfigure(1, weight=1)
        rf.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(rf, text="Lodě", font=ctk.CTkFont("", 13, "bold"),
                     text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, padx=14, pady=(14, 4), sticky="w")
        self.ships_scroll = ctk.CTkScrollableFrame(rf, fg_color="transparent",
                                                    scrollbar_button_color=BORDER, height=120)
        self.ships_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.ships_scroll.grid_columnconfigure(0, weight=1)
        self._ship_rows = []

        ctk.CTkFrame(rf, height=1, fg_color=BORDER).grid(row=2, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(rf, text="Žebříček", font=ctk.CTkFont("", 13, "bold"),
                     text_color=TEXT_BRIGHT
                     ).grid(row=2, column=0, padx=14, pady=(10, 4), sticky="w")
        self.scores_scroll = ctk.CTkScrollableFrame(rf, fg_color="transparent",
                                                     scrollbar_button_color=BORDER)
        self.scores_scroll.grid(row=3, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self.scores_scroll.grid_columnconfigure(0, weight=1)
        self._score_rows = []

        # Log
        lf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        lf.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 20))
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
            "idle":         ("⚓", "Bot je online",       "Čeká na !start od moderátora",    KICK_GREEN),
            "playing":      ("🎯", "Hra probíhá!",        "Hráči střílí souřadnice do chatu", "#ff4444"),
            "done":         ("🏆", "Hra skončila!",       "Moderátor zadá !start pro novou",  KICK_GREEN),
            "disconnected": ("⚪", "Odpojeno",            "Klikni na Spustit bota",           TEXT_DIM),
        }
        icon, title, sub, color = configs.get(status, ("⚪", status, "", TEXT_DIM))
        dot = {"idle": "🟢 Online", "playing": "🔴 Hraje se", "done": "🏆 Hotovo",
               "disconnected": "⚪ Odpojeno"}.get(status, status)
        def _update():
            self.banner_icon.configure(text=icon)
            self.banner_text.configure(text=title, text_color=color)
            self.banner_sub.configure(text=sub)
            self.lbl_status.configure(text=dot)
        self.after(0, _update)

    def _update_board(self, game: LodeGame):
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

        self._draw_ships(game)

    def _draw_ships(self, game: LodeGame):
        for w in self._ship_rows:
            w.destroy()
        self._ship_rows.clear()

        for i, ship in enumerate(game.ships):
            bg = CARD_BG if i % 2 == 0 else PANEL_BG
            rf = ctk.CTkFrame(self.ships_scroll, fg_color=bg, corner_radius=4, height=24)
            rf.grid(row=i, column=0, sticky="ew", padx=4, pady=1)
            rf.grid_columnconfigure(1, weight=1)
            rf.grid_propagate(False)

            color = "#ff8800" if ship["sunk"] else (KICK_GREEN if ship["hits"] else TEXT_MID)
            cells_str = "█" * len(ship["hits"]) + "·" * (ship["size"] - len(ship["hits"]))
            status = f"[POTOPENA — {ship['sunk_by']}]" if ship["sunk"] else f"{len(ship['hits'])}/{ship['size']}"

            ctk.CTkLabel(rf, text=f"{ship['name']} ({ship['size']}p)",
                         font=ctk.CTkFont("", 10), text_color=color, anchor="w"
                         ).grid(row=0, column=0, padx=8, pady=2, sticky="w")
            ctk.CTkLabel(rf, text=f"{cells_str}  {status}",
                         font=ctk.CTkFont("Courier New", 10), text_color=color, anchor="e"
                         ).grid(row=0, column=1, padx=8, pady=2, sticky="e")
            self._ship_rows.append(rf)

    def _update_scores(self, rows):
        def _redraw():
            for w in self._score_rows:
                w.destroy()
            self._score_rows.clear()
            medals = ["🥇", "🥈", "🥉"] + ["  "] * 100
            for i, (user, pts) in enumerate(rows):
                bg = CARD_BG if i % 2 == 0 else PANEL_BG
                rf = ctk.CTkFrame(self.scores_scroll, fg_color=bg, corner_radius=4, height=24)
                rf.grid(row=i, column=0, sticky="ew", padx=4, pady=1)
                rf.grid_columnconfigure(0, weight=1)
                rf.grid_propagate(False)
                ctk.CTkLabel(rf,
                             text=f"{medals[i]} {user}",
                             font=ctk.CTkFont("", 11), text_color=TEXT_BRIGHT, anchor="w"
                             ).grid(row=0, column=0, padx=8, pady=2, sticky="w")
                ctk.CTkLabel(rf,
                             text=f"{pts} b",
                             font=ctk.CTkFont("", 11, "bold"), text_color=KICK_GREEN, anchor="e"
                             ).grid(row=0, column=1, padx=8, pady=2, sticky="e")
                self._score_rows.append(rf)
        self.after(0, _redraw)

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
