"""
Kick.com Soutěžní Bot — GUI verze
Instalace: pip install customtkinter websocket-client curl_cffi requests
Spuštění:  python kick_bot_gui.py
"""

import os, sys, json, re, time, hashlib, base64, secrets, webbrowser, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
import requests
from curl_cffi import requests as cf_requests
import websocket

BUILD_VERSION = "0.0.3"

DEBUG = False

# ── Kick API konstanty ───────────────────────────────────────────────────────
KICK_AUTH_URL   = "https://id.kick.com/oauth/authorize"
KICK_TOKEN_URL  = "https://id.kick.com/oauth/token"
KICK_API_URL    = "https://api.kick.com/public/v1"
KICK_SCOPES     = "user:read chat:write"
PUSHER_WS       = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
                   "?protocol=7&client=js&version=8.4.0-rc2&flash=false")
REDIRECT_URI    = "http://localhost:7878/callback"
TOKEN_FILE      = Path("kick_tokens.json")
CONFIG_FILE     = Path("kick_config.json")
BOT_CONFIG_FILE = Path("bot_config.json")

# ── Barvy ────────────────────────────────────────────────────────────────────
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


# ════════════════════════════════════════════════════════════════════════════
#  Načítání bot_config.json
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_BOT_CONFIG = {
    "prikazy": {
        "start":    "!start",
        "stop":     "!stop",
        "cislo":    "!cislo",
        # "vysledky": "!vysledky",
    },
    "zpravy": {
        "bot_online":      "🤖 Bot je online! Moderátor může zadat {cmd_start} pro zahájení soutěže.",
        "soutez_zahajena": "🎯 Soutěž zahájena! Napište číslo do chatu — počítá se váš POSLEDNÍ odhad.",
        "soutez_probiha":  "⚠️ Soutěž už probíhá!",
        "sber_ukoncen":    "🛑 Sběr ukončen. Celkem: {pocet} odhadů. Moderátor zadá {cmd_cislo} <číslo>",
        "zadna_soutez":    "⚠️ Žádná soutěž momentálně neprobíhá.",
        "spatny_prikaz":   "⚠️ Použití: {cmd_cislo} <číslo>  (např. {cmd_cislo} 254)",
        "zadne_odhady":    "❌ Nikdo nic nehádal!",
        "vitez_presny":    "🎯 PŘESNÝ ZÁSAH! {vitezove} | Správné číslo bylo: {cislo}",
        "vitez_nejbliz":   "🏆 Nejblíže (rozdíl: {rozdil}): {vitezove} | Správné číslo bylo: {cislo}",
    },
}

# Šablona která se zapíše jako bot_config.json pokud soubor neexistuje
BOT_CONFIG_TEMPLATE = {
    "_komentare": {
        "popis": "Konfigurační soubor Kick Soutěžního Bota",
        "poznamka_prikazy": "Příkazy jsou case-insensitive: START = start = Start",
        "poznamka_zpravy": "Proměnné v {složených závorkách} se automaticky dosadí — nemazat je!",
    },
    "prikazy": {
        "_vysvetleni": "Změň hodnoty na cokoliv chceš. Příklad: místo !start napiš START nebo /start",
        "start":    "!start",
        "stop":     "!stop",
        "cislo":    "!cislo",
        # "vysledky": "!vysledky",
    },
    "zpravy": {
        "_vysvetleni": "Texty které bot píše do chatu. Proměnné v {závorkách} jsou povinné.",
        "bot_online":      "🤖 Bot je online! Moderátor může zadat {cmd_start} pro zahájení soutěže.",
        "soutez_zahajena": "🎯 Soutěž zahájena! Napište číslo do chatu — počítá se váš POSLEDNÍ odhad.",
        "soutez_probiha":  "⚠️ Soutěž už probíhá!",
        "sber_ukoncen":    "🛑 Sběr ukončen. Celkem: {pocet} odhadů. Moderátor zadá {cmd_cislo} <číslo>",
        "zadna_soutez":    "⚠️ Žádná soutěž momentálně neprobíhá.",
        "spatny_prikaz":   "⚠️ Použití: {cmd_cislo} <číslo>  (např. {cmd_cislo} 254)",
        "zadne_odhady":    "❌ Nikdo nic nehádal!",
        "vitez_presny":    "🎯 PŘESNÝ ZÁSAH! {vitezove} | Správné číslo bylo: {cislo}",
        "vitez_nejbliz":   "🏆 Nejblíže (rozdíl: {rozdil}): {vitezove} | Správné číslo bylo: {cislo}",
    },
    "_napoveda_promennych": {
        "popis": "Tyto proměnné musí zůstat v příslušných zprávách:",
        "bot_online":    "{cmd_start} = text příkazu start",
        "sber_ukoncen":  "{pocet} = počet hráčů,  {cmd_cislo} = text příkazu cislo",
        "spatny_prikaz": "{cmd_cislo} = text příkazu cislo",
        "vitez_presny":  "{vitezove} = vítězové s číslem,  {cislo} = správné číslo",
        "vitez_nejbliz": "{vitezove} = vítězové s číslem,  {cislo} = správné číslo,  {rozdil} = rozdíl",
    },
}


def load_bot_config() -> dict:
    """Načte bot_config.json. Při prvním spuštění vytvoří soubor s výchozími hodnotami."""
    import copy
    cfg = copy.deepcopy(DEFAULT_BOT_CONFIG)

    if not BOT_CONFIG_FILE.exists():
        # Vytvoř výchozí soubor
        try:
            BOT_CONFIG_FILE.write_text(
                json.dumps(BOT_CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[WARN] Nelze vytvořit bot_config.json: {e}")
        return cfg

    try:
        user = json.loads(BOT_CONFIG_FILE.read_text(encoding="utf-8"))
        # Přepíše jen klíče které uživatel definoval, ignoruje "_komentare" a "_vysvetleni"
        for section in ("prikazy", "zpravy"):
            if section in user and isinstance(user[section], dict):
                for k, v in user[section].items():
                    if not k.startswith("_") and isinstance(v, str):
                        cfg[section][k] = v
    except json.JSONDecodeError as e:
        print(f"[ERROR] bot_config.json má chybu: {e} — používám výchozí hodnoty")
    except Exception as e:
        print(f"[WARN] Nelze načíst bot_config.json: {e} — používám výchozí hodnoty")

    return cfg


# ════════════════════════════════════════════════════════════════════════════
#  Logika bota
# ════════════════════════════════════════════════════════════════════════════
class BotEngine:
    def __init__(self, log_cb, status_cb, guess_cb):
        self.log_cb    = log_cb
        self.status_cb = status_cb
        self.guess_cb  = guess_cb

        self.collecting     = False
        self.guesses        = {}
        self.broadcaster_id = 0
        self.chatroom_id    = 0
        self.ws             = None
        self.ws_thread      = None
        self.running        = False

        self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._load_tokens()
        self.bcfg = load_bot_config()

    def reload_bot_config(self):
        """Znovu načte bot_config.json za běhu — bez restartu bota."""
        self.bcfg = load_bot_config()
        self.log("✅ bot_config.json znovu načten.", "success")

    # ── Přístup ke konfiguraci ───────────────────────────────────────────────
    def _cmd(self, key: str) -> str:
        """Vrátí příkaz v lowercase pro porovnání (case-insensitive)."""
        return self.bcfg["prikazy"].get(key, f"!{key}").strip().lower()

    def _msg(self, key: str, **kwargs) -> str:
        """Vrátí text zprávy s dosazenými proměnnými."""
        template = self.bcfg["zpravy"].get(key, f"[{key}]")
        # Automaticky dostupné proměnné — hodnoty příkazů z konfigurace
        kwargs.setdefault("cmd_start",    self.bcfg["prikazy"].get("start",    "!start"))
        kwargs.setdefault("cmd_stop",     self.bcfg["prikazy"].get("stop",     "!stop"))
        kwargs.setdefault("cmd_cislo",    self.bcfg["prikazy"].get("cislo",    "!cislo"))
        # kwargs.setdefault("cmd_vysledky", self.bcfg["prikazy"].get("vysledky", "!vysledky"))
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template  # šablona obsahuje neznámou proměnnou — vrať tak jak je

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

    # ── PKCE ─────────────────────────────────────────────────────────────────
    def _pkce_pair(self):
        v = secrets.token_urlsafe(64)
        d = hashlib.sha256(v.encode()).digest()
        c = base64.urlsafe_b64encode(d).rstrip(b"=").decode()
        return v, c

    # ── OAuth ─────────────────────────────────────────────────────────────────
    def do_oauth(self, client_id, client_secret, on_done):
        def run():
            # Vymaž starý token aby se nepoužil pokud přihlášení selže
            self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}

            verifier, challenge = self._pkce_pair()
            params = {
                "response_type": "code", "client_id": client_id,
                "redirect_uri": REDIRECT_URI, "scope": KICK_SCOPES,
                "code_challenge": challenge, "code_challenge_method": "S256",
                "state": secrets.token_urlsafe(16),
            }
            auth_url = f"{KICK_AUTH_URL}?{urlencode(params)}"
            self.log("Otevírám prohlížeč pro přihlášení ...", "info")
            webbrowser.open(auth_url)

            result = {}
            log_ref = self.log

            class H(BaseHTTPRequestHandler):
                def do_GET(s):
                    parsed = urlparse(s.path)
                    qs = parse_qs(parsed.query)
                    result["raw"]        = parsed.query
                    result["code"]       = qs.get("code",  [""])[0]
                    result["error"]      = qs.get("error", [""])[0]
                    result["error_desc"] = qs.get("error_description", [""])[0]
                    s.send_response(200)
                    s.send_header("Content-Type", "text/html; charset=utf-8")
                    s.end_headers()
                    if result["code"]:
                        s.wfile.write(b"<html><body style='font-family:sans-serif;"
                            b"text-align:center;padding:60px;background:#0d0d0d;color:#53FC18'>"
                            b"<h2>Bot autorizovan!</h2>"
                            b"<p style='color:#aaa'>Toto okno muzete zavrit.</p>"
                            b"</body></html>")
                    else:
                        s.wfile.write(b"<html><body style='font-family:sans-serif;"
                            b"text-align:center;padding:60px;background:#0d0d0d;color:#ff4444'>"
                            b"<h2>Autorizace selhala</h2>"
                            b"<p style='color:#aaa'>Zkuste to znovu v aplikaci.</p>"
                            b"</body></html>")
                def log_message(s, *a): pass

            try:
                port = int(REDIRECT_URI.split(":")[-1].split("/")[0])
                srv = HTTPServer(("localhost", port), H)
                srv.timeout = 120
                self.log("Čekám na potvrzení v prohlížeči (max 2 min) ...", "info")
                srv.handle_request()
            except Exception as e:
                self.log(f"Chyba callback serveru: {e}", "error")
                on_done(False)
                return

            if result.get("error"):
                self.log(f"Kick vrátil chybu: {result['error']} — {result.get('error_desc','')}", "error")
                on_done(False)
                return

            code = result.get("code", "")
            if not code:
                self.log(
                    "Kick neposlal autorizační kód! "
                    "Zkontroluj Redirect URI na kick.com/settings/developer — "
                    "musí být PŘESNĚ: http://localhost:7878/callback", "error")
                on_done(False)
                return

            try:
                resp = requests.post(KICK_TOKEN_URL, data={
                    "grant_type":    "authorization_code",
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "redirect_uri":  REDIRECT_URI,
                    "code":          code,
                    "code_verifier": verifier,
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

    def get_my_user_id(self) -> int | None:
        """Zjistí user ID přihlášeného bot účtu."""
        try:
            resp = requests.get(f"{KICK_API_URL}/users/me",
                headers={"Authorization": f"Bearer {self.tokens['access_token']}"},
                timeout=10)
            if resp.ok:
                data = resp.json()
                # Kick API vrací buď {"data": {...}} nebo přímo objekt
                user = data.get("data", data)
                uid = user.get("user_id") or user.get("id")
                return uid
            else:
                return None
        except Exception as e:
            return None

    def send_chat(self, message, client_id, client_secret):
        if not self.broadcaster_id:
            return
        if not self.ensure_token(client_id, client_secret):
            self.log("Nelze poslat zprávu — chybí token.", "error")
            return
        try:
            payload = {
                "broadcaster_user_id": self.broadcaster_id,
                "content": message,
                "type": "bot",
            }
            resp = requests.post(f"{KICK_API_URL}/chat",
                headers={"Authorization": f"Bearer {self.tokens['access_token']}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=10)
            if resp.ok:
                if DEBUG:
                    self.log(f"[Chat ✓] {resp.status_code} | {resp.text[:200]}", "success")
                else:
                    self.log(f"[Chat ✓] {message}", "success")
            else:
                self.log(f"Chat API chyba: {resp.status_code} | {resp.text}", "error")
        except Exception as e:
            self.log(f"Chyba odesílání: {e}", "error")

    # ── Soutěžní logika ───────────────────────────────────────────────────────
    def is_moderator(self, sender):
        badges = sender.get("identity", {}).get("badges", [])
        return any(b.get("type", "").lower() in
                   {"moderator", "broadcaster", "editor", "og"} for b in badges)

    def extract_int(self, text):
        m = re.findall(r"-?\d+", text)
        return int(m[0]) if m else None

    def handle_message(self, sender, content, client_id, client_secret):
        text  = content.strip()
        lower = text.lower()

        if self.is_moderator(sender):
            cmd_start    = self._cmd("start")
            cmd_stop     = self._cmd("stop")
            cmd_cislo    = self._cmd("cislo")
            # cmd_vysledky = self._cmd("vysledky")

            if lower == cmd_start:
                if self.collecting:
                    self.send_chat(self._msg("soutez_probiha"), client_id, client_secret)
                else:
                    self.collecting = True
                    self.guesses = {}
                    self.guess_cb([])
                    self.log("▶ Soutěž zahájena", "success")
                    self.status_cb("collecting")
                    self.send_chat(self._msg("soutez_zahajena"), client_id, client_secret)
                return

            if lower == cmd_stop:
                if not self.collecting:
                    self.send_chat(self._msg("zadna_soutez"), client_id, client_secret)
                else:
                    self.collecting = False
                    self.log(f"⏹ Sběr ukončen. Odhadů: {len(self.guesses)}", "warn")
                    self.status_cb("stopped")
                    self.send_chat(
                        self._msg("sber_ukoncen", pocet=len(self.guesses)),
                        client_id, client_secret)
                return

            # Příkaz cislo — může být "!cislo254" nebo "!cislo 254"
            if lower == cmd_cislo or lower.startswith(cmd_cislo + " "):
                suffix = text[len(cmd_cislo):].strip()
                n = self.extract_int(suffix)
                if n is None:
                    self.send_chat(self._msg("spatny_prikaz"), client_id, client_secret)
                else:
                    self._evaluate(n, client_id, client_secret)
                return

            # if lower == cmd_vysledky:
            #     if not self.guesses:
            #         self.send_chat(self._msg("zadne_odhady"), client_id, client_secret)
            #     return

        # Hráčský odhad
        if self.collecting:
            username = sender.get("username", "???")
            guess = self.extract_int(text)
            if guess is not None:
                prev = self.guesses.get(username)
                self.guesses[username] = guess
                if prev is None:
                    self.log(f"  {username} → {guess}", "info")
                else:
                    self.log(f"  {username} → {guess}  (byl: {prev})", "dim")
                self.guess_cb(sorted(self.guesses.items()))

    def _evaluate(self, correct, client_id, client_secret):
        self.log(f"━━━ Vyhodnocení — správné číslo: {correct} ━━━", "success")
        if not self.guesses:
            self.send_chat(self._msg("zadne_odhady"), client_id, client_secret)
            return
        distances = {u: abs(g - correct) for u, g in self.guesses.items()}
        min_dist  = min(distances.values())
        winners   = [(u, self.guesses[u]) for u, d in distances.items() if d == min_dist]
        wstr      = ", ".join(f"{u} [{g}]" for u, g in winners)

        if min_dist == 0:
            msg = self._msg("vitez_presny", vitezove=wstr, cislo=correct)
        else:
            msg = self._msg("vitez_nejbliz", vitezove=wstr, cislo=correct, rozdil=min_dist)

        self.send_chat(msg, client_id, client_secret)
        for u, g in winners:
            self.log(f"  🏆 {u} → {g}", "success")
        self.status_cb("done")

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
            # Ověř token a zjisti bot user ID
            self.get_my_user_id()
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
#  GUI
# ════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Kick Soutěžní Bot v{BUILD_VERSION}")
        self.geometry("960x700")
        self.minsize(880, 850)
        self.configure(fg_color=DARK_BG)

        self._load_config()
        self.engine = BotEngine(
            log_cb    = self._append_log,
            status_cb = self._set_status,
            guess_cb  = self._update_guesses,
        )
        if self.engine._token_valid():
            self._token_status = "valid"
        elif self.engine.tokens.get("refresh_token"):
            self._token_status = "refresh"
        else:
            self._token_status = "none"

        self._build_ui()
        self._refresh_token_label()

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
        sb = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, width=280)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        # Logo
        ctk.CTkLabel(sb, text="🎯 KickBot", font=ctk.CTkFont("", 22, "bold"),
                     text_color=KICK_GREEN).grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        ctk.CTkLabel(sb, text="Soutěžní bot", font=ctk.CTkFont("", 12),
                     text_color=TEXT_DIM).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")
        ctk.CTkFrame(sb, height=1, fg_color=BORDER).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 20))

        # Nastavení
        self._section(sb, "NASTAVENÍ", 3)
        self._label(sb, "Client ID", 4)
        self.entry_cid = self._entry(sb, 5, self._cfg["client_id"])
        self._label(sb, "Client Secret", 6)
        self.entry_csecret = self._entry(sb, 7, self._cfg["client_secret"], show="•")
        self._label(sb, "Název kanálu (slug)", 8)
        self.entry_channel = self._entry(sb, 9, self._cfg["channel"])

        self.lbl_token = ctk.CTkLabel(sb, text="", font=ctk.CTkFont("", 11),
                                      wraplength=220, justify="left")
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

        # Připojení
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

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).grid(row=17, column=0, sticky="ew", padx=16, pady=(4, 12))

        # Konfigurace
        self._section(sb, "KONFIGURACE BOTA", 18)
        self.btn_edit_cfg = ctk.CTkButton(sb, text="✏️  Upravit texty a příkazy",
            fg_color="transparent", hover_color=CARD_BG,
            text_color=TEXT_MID, border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 11), height=34, corner_radius=8,
            command=self._open_bot_config)
        self.btn_edit_cfg.grid(row=19, column=0, padx=16, pady=(4, 4), sticky="ew")

        self.btn_reload_cfg = ctk.CTkButton(sb, text="🔄  Načíst změny konfigurace",
            fg_color="transparent", hover_color=CARD_BG,
            text_color=TEXT_DIM, border_color=BORDER, border_width=1,
            font=ctk.CTkFont("", 11), height=30, corner_radius=8,
            command=self._reload_bot_config)
        self.btn_reload_cfg.grid(row=20, column=0, padx=16, pady=(0, 8), sticky="ew")

        sb.grid_rowconfigure(21, weight=1)

        ctk.CTkButton(sb, text="❓ Jak získat Client ID?",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), height=28, anchor="w",
            command=lambda: webbrowser.open("https://kick.com/settings/developer")
        ).grid(row=22, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=2)
        main.grid_rowconfigure(3, weight=1)

        # Banner
        self.banner = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12, height=64)
        self.banner.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        self.banner.grid_propagate(False)
        self.banner.grid_columnconfigure(1, weight=1)
        self.banner_icon = ctk.CTkLabel(self.banner, text="⚪", font=ctk.CTkFont("", 28))
        self.banner_icon.grid(row=0, column=0, padx=(20, 12), pady=12)
        self.banner_text = ctk.CTkLabel(self.banner, text="Bot je odpojený",
            font=ctk.CTkFont("", 16, "bold"), text_color=TEXT_MID, anchor="w")
        self.banner_text.grid(row=0, column=1, sticky="w")
        self.banner_sub = ctk.CTkLabel(self.banner,
            text="Vyplň nastavení a klikni na Spustit bota",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM, anchor="e")
        self.banner_sub.grid(row=0, column=2, padx=20, sticky="e")

        # Tabulka odhadů
        gf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        gf.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        gf.grid_columnconfigure(0, weight=1)
        gf.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(gf, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Odhady hráčů",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        self.lbl_count = ctk.CTkLabel(hdr, text="0 hráčů",
                     font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_count.grid(row=0, column=1, sticky="e")
        self.guess_scroll = ctk.CTkScrollableFrame(gf, fg_color="transparent",
                                                    scrollbar_button_color=BORDER)
        self.guess_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.guess_scroll.grid_columnconfigure(0, weight=1)
        self._guess_rows = []
        self.guess_placeholder = ctk.CTkLabel(self.guess_scroll,
            text="Zatím žádné odhady.\nZahaj soutěž start příkazem v chatu.",
            font=ctk.CTkFont("", 12), text_color=TEXT_DIM, justify="center")
        self.guess_placeholder.grid(row=0, column=0, columnspan=2, pady=30)

        # Log
        lf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        lf.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
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
        """Smaže uložený token a vynutí nové přihlášení."""
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

    def _open_bot_config(self):
        """Otevře bot_config.json ve výchozím textovém editoru."""
        if not BOT_CONFIG_FILE.exists():
            load_bot_config()  # vytvoří soubor
        try:
            if sys.platform == "win32":
                os.startfile(str(BOT_CONFIG_FILE.resolve()))
            elif sys.platform == "darwin":
                os.system(f"open '{BOT_CONFIG_FILE}'")
            else:
                os.system(f"xdg-open '{BOT_CONFIG_FILE}'")
            self._append_log(
                "bot_config.json otevřen v editoru. "
                "Po uložení klikni na '🔄 Načíst změny konfigurace'.", "info")
        except Exception as e:
            self._append_log(f"Nelze otevřít editor: {e}", "error")

    def _reload_bot_config(self):
        """Znovu načte bot_config.json bez restartu bota."""
        self.engine.reload_bot_config()

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _append_log(self, msg, level="info"):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        def _insert():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line)
            self.log_box.configure(state="disabled")
            self.log_box.see("end")
        self.after(0, _insert)

    def _set_status(self, status):
        configs = {
            "idle":         ("🟢", "Bot je online",       "Čeká na příkaz od moderátora",   KICK_GREEN),
            "collecting":   ("🔴", "Sbírám odhady!",      "Moderátor zadá stop příkaz",      "#ff4444"),
            "stopped":      ("🟡", "Sběr ukončen",        "Moderátor zadá číslo příkaz",     YELLOW_WARN),
            "done":         ("🏆", "Výsledky vyhlášeny!", "Čeká na příkaz od moderátora",    KICK_GREEN),
            "disconnected": ("⚪", "Odpojeno",            "Klikni na Spustit bota",          TEXT_DIM),
        }
        icon, title, sub, color = configs.get(status, ("⚪", status, "", TEXT_DIM))
        def _update():
            self.banner_icon.configure(text=icon)
            self.banner_text.configure(text=title, text_color=color)
            self.banner_sub.configure(text=sub)
            dot = {"idle": "🟢 Online", "collecting": "🔴 Sbírám", "stopped": "🟡 Čekám",
                   "done": "🏆 Hotovo", "disconnected": "⚪ Odpojeno"}.get(status, status)
            self.lbl_status.configure(text=dot)
        self.after(0, _update)

    def _update_guesses(self, rows):
        def _redraw():
            for w in self._guess_rows:
                w.destroy()
            self._guess_rows.clear()
            if not rows:
                self.guess_placeholder.grid(row=0, column=0, columnspan=2, pady=30)
                self.lbl_count.configure(text="0 hráčů")
                return
            self.guess_placeholder.grid_remove()
            self.lbl_count.configure(text=f"{len(rows)} hráčů")
            for i, (user, guess) in enumerate(rows):
                bg = CARD_BG if i % 2 == 0 else PANEL_BG
                row_f = ctk.CTkFrame(self.guess_scroll, fg_color=bg,
                                     corner_radius=4, height=28)
                row_f.grid(row=i, column=0, columnspan=2, sticky="ew", padx=4, pady=1)
                row_f.grid_columnconfigure(0, weight=1)
                row_f.grid_propagate(False)
                ctk.CTkLabel(row_f, text=user, font=ctk.CTkFont("", 11),
                             text_color=TEXT_BRIGHT, anchor="w"
                             ).grid(row=0, column=0, padx=10, pady=2, sticky="w")
                ctk.CTkLabel(row_f, text=str(guess), font=ctk.CTkFont("", 11, "bold"),
                             text_color=KICK_GREEN, anchor="e"
                             ).grid(row=0, column=1, padx=10, pady=2, sticky="e")
                self._guess_rows.append(row_f)
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
