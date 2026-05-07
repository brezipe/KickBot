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

BUILD_VERSION = "260507.0814"

DEBUG = False
pass

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

# ── GitHub auto-update ────────────────────────────────────────────────────────
GITHUB_REPO    = "brezipe/KickBot"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

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
        "cislo_obsazeno":  "⛔ @{username} Číslo {cislo} už zadal/a {jiny_hrac} — vyber si jiné!",
    },
    "debug": {
        "enabled":          False,
        "test_server_port": 7879,
    },
    "gui": {
        "log_collapsed": True,
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
        "cislo_obsazeno":  "⛔ @{username} Číslo {cislo} už zadal/a {jiny_hrac} — vyber si jiné!",
    },
    "_napoveda_promennych": {
        "popis": "Tyto proměnné musí zůstat v příslušných zprávách:",
        "bot_online":    "{cmd_start} = text příkazu start",
        "sber_ukoncen":  "{pocet} = počet hráčů,  {cmd_cislo} = text příkazu cislo",
        "spatny_prikaz": "{cmd_cislo} = text příkazu cislo",
        "vitez_presny":  "{vitezove} = vítězové s číslem,  {cislo} = správné číslo",
        "vitez_nejbliz": "{vitezove} = vítězové s číslem,  {cislo} = správné číslo,  {rozdil} = rozdíl",
        "cislo_obsazeno": "{username} = hráč co psal,  {cislo} = obsazené číslo,  {jiny_hrac} = kdo ho zadal dříve",
    },
    "debug": {
        "_vysvetleni":      "Testovací mód — spustí lokální HTTP server pro kick_bot_test.py.",
        "enabled":          False,
        "test_server_port": 7879,
    },
    "gui": {
        "_vysvetleni":  "Nastavení vzhledu a chování rozhraní.",
        "log_collapsed": True,
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
        # Debug a gui sekce — přijímají bool a int
        for section in ("debug", "gui"):
            if section in user and isinstance(user[section], dict):
                for k, v in user[section].items():
                    if not k.startswith("_") and k in cfg[section]:
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
    def __init__(self, log_cb, status_cb, guess_cb, result_cb=None):
        self.log_cb    = log_cb
        self.status_cb = status_cb
        self.guess_cb  = guess_cb
        self.result_cb = result_cb or (lambda c, r: None)

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

    def _parse_pure_int(self, text: str):
        """Vrátí int pouze pokud je zpráva čistě celé číslo (max. okolní mezery). Věty s číslem odmítne."""
        if re.fullmatch(r"\s*-?\d+\s*", text):
            return int(text.strip())
        return None

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
            guess = self._parse_pure_int(text)
            if guess is not None:
                taken_by = next(
                    (u for u, g in self.guesses.items() if g == guess and u != username),
                    None
                )
                if taken_by is not None:
                    self.send_chat(
                        self._msg("cislo_obsazeno", username=username, cislo=guess, jiny_hrac=taken_by),
                        client_id, client_secret)
                    self.log(f"  {username} zkusil {guess} — obsazeno ({taken_by})", "warn")
                    return
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
            self.result_cb(correct, [])
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

        sorted_results = sorted(
            [(u, g, abs(g - correct)) for u, g in self.guesses.items()],
            key=lambda x: x[2]
        )
        self.result_cb(correct, sorted_results)

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
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.configure(fg_color=DARK_BG)

        self._load_config()
        self.engine = BotEngine(
            log_cb    = self._append_log,
            status_cb = self._set_status,
            guess_cb  = self._update_guesses,
            result_cb = self._update_results,
        )
        if self.engine._token_valid():
            self._token_status = "valid"
        elif self.engine.tokens.get("refresh_token"):
            self._token_status = "refresh"
        else:
            self._token_status = "none"

        self._build_ui()
        self._refresh_token_label()
        # Spusť test server pokud je debug zapnutý v bot_config.json
        debug_cfg = self.engine.bcfg.get("debug", {})
        if debug_cfg.get("enabled", False):
            global DEBUG
            DEBUG = True
            self._start_test_server(int(debug_cfg.get("test_server_port", 7879)))
        # Aplikuj výchozí stav protokolu z bot_config.json
        if self.engine.bcfg.get("gui", {}).get("log_collapsed", True):
            self.after(100, self._toggle_log)
        # Ukliď pozůstatek po aktualizaci; do té doby zablokuj zavření okna
        if getattr(sys, "frozen", False) and (
                Path(sys.executable).parent.parent / "_KickBot_old").exists():
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.after(3000, self._cleanup_old_exe)
        # První spuštění — nabídni nastavení (výjimka AV, zástupce na ploše)
        self.after(50, self._check_first_run)
        # Zkontroluj kompatibilitu bot_config.json
        self.after(200, self._check_config_compat)
        # Zkontroluj dostupnost aktualizace na GitHubu
        self.after(400, self._check_for_update)

    # ── Test server (DEBUG) ───────────────────────────────────────────────────
    def _start_test_server(self, port: int):
        engine  = self.engine
        cfg_ref = self._cfg

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/simulate":
                    self.send_response(404); self.end_headers(); return
                try:
                    length  = int(self.headers.get("Content-Length", 0))
                    body    = self.rfile.read(length)
                    data    = json.loads(body)
                    sender  = data.get("sender", {})
                    content = data.get("content", "")
                    cid     = cfg_ref.get("client_id", "")
                    cs      = cfg_ref.get("client_secret", "")
                    engine.handle_message(sender, content, cid, cs)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            def log_message(self, *a): pass

        try:
            srv = HTTPServer(("localhost", port), _Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self._append_log(
                f"🧪 [DEBUG] Test server spuštěn — localhost:{port}/simulate", "warn")
        except Exception as e:
            self._append_log(f"❌ Nelze spustit test server na portu {port}: {e}", "error")

    # ── Config kompatibilita ──────────────────────────────────────────────────
    def _check_config_compat(self):
        if not BOT_CONFIG_FILE.exists():
            return
        try:
            raw = json.loads(BOT_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        missing = []
        for section, defaults in DEFAULT_BOT_CONFIG.items():
            if not isinstance(defaults, dict):
                continue
            if section not in raw:
                missing.append(f"cela sekce [{section}]")
            else:
                for key in defaults:
                    if not key.startswith("_") and key not in raw[section]:
                        missing.append(f"{section} → {key}")
        if missing:
            self._show_config_compat_dialog(missing)

    def _show_config_compat_dialog(self, missing: list):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Nekompatibilní konfigurace")
        dlg.configure(fg_color=DARK_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dlg, text="⚠️  Nekompatibilní konfigurace",
                     font=ctk.CTkFont("", 16, "bold"), text_color=YELLOW_WARN
                     ).grid(row=0, column=0, padx=28, pady=(28, 6))
        ctk.CTkLabel(dlg,
                     text="bot_config.json není kompatibilní s touto verzí bota.\nChybí následující položky:",
                     font=ctk.CTkFont("", 12), text_color=TEXT_MID, justify="center"
                     ).grid(row=1, column=0, padx=28, pady=(0, 10))

        items_frame = ctk.CTkFrame(dlg, fg_color=CARD_BG, corner_radius=8)
        items_frame.grid(row=2, column=0, padx=28, pady=(0, 20), sticky="ew")
        for i, item in enumerate(missing):
            ctk.CTkLabel(items_frame, text=f"• {item}",
                         font=ctk.CTkFont("Courier New", 11), text_color=TEXT_DIM,
                         anchor="w").grid(row=i, column=0, padx=16, pady=(6 if i == 0 else 2, 6 if i == len(missing)-1 else 2), sticky="w")

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=28, pady=(0, 28), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        def do_fix():
            self._fix_config()
            dlg.destroy()

        ctk.CTkButton(btn_row, text="✅  Opravit",
                      fg_color="#1e3a1e", hover_color="#2a4f2a",
                      text_color=KICK_GREEN, border_color=KICK_GREEN, border_width=1,
                      font=ctk.CTkFont("", 13, "bold"), height=42, corner_radius=8,
                      command=do_fix
                      ).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(btn_row, text="Ignorovat",
                      fg_color="transparent", hover_color=CARD_BG,
                      text_color=TEXT_DIM, border_color=BORDER, border_width=1,
                      font=ctk.CTkFont("", 12), height=42, corner_radius=8,
                      command=dlg.destroy
                      ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _fix_config(self):
        try:
            raw = json.loads(BOT_CONFIG_FILE.read_text(encoding="utf-8"))
            for section, defaults in DEFAULT_BOT_CONFIG.items():
                if not isinstance(defaults, dict):
                    continue
                if section not in raw:
                    raw[section] = {k: v for k, v in defaults.items()
                                    if not k.startswith("_")}
                else:
                    for key, val in defaults.items():
                        if not key.startswith("_") and key not in raw[section]:
                            raw[section][key] = val
            BOT_CONFIG_FILE.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            self.engine.reload_bot_config()
        except Exception as e:
            self._append_log(f"❌ Chyba při opravě configu: {e}", "error")

    def _cleanup_old_exe(self, attempt: int = 0):
        if not getattr(sys, "frozen", False):
            return
        import shutil
        old = Path(sys.executable).parent.parent / "_KickBot_old"
        if old.exists():
            try:
                shutil.rmtree(old)
            except Exception:
                if attempt < 5:
                    self.after(2000, lambda: self._cleanup_old_exe(attempt + 1))
                    return
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ── První spuštění ────────────────────────────────────────────────────────
    def _check_first_run(self):
        if not getattr(sys, "frozen", False):
            return
        flag = Path(sys.executable).parent / ".configured"
        if not flag.exists():
            self._show_first_run_dialog(flag)

    def _show_first_run_dialog(self, flag: Path):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Nastavení KickBotu")
        dlg.configure(fg_color=DARK_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dlg, text="Vítej v KickBotu!",
                     font=ctk.CTkFont("", 16, "bold"), text_color=KICK_GREEN
                     ).grid(row=0, column=0, padx=32, pady=(28, 6))
        ctk.CTkLabel(dlg,
                     text="Pro správnou funkci doporučuji provést\njednorázové nastavení:",
                     font=ctk.CTkFont("", 12), text_color=TEXT_MID, justify="center"
                     ).grid(row=1, column=0, padx=32, pady=(0, 20))

        var_defender = ctk.BooleanVar(value=True)
        var_shortcut = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(dlg,
                        text="Přidat výjimku v antivirovém programu\n(nutné pro aktualizace)",
                        variable=var_defender, font=ctk.CTkFont("", 12),
                        text_color=TEXT_BRIGHT, fg_color=KICK_GREEN, hover_color="#45d614",
                        ).grid(row=2, column=0, padx=32, pady=(0, 12), sticky="w")
        ctk.CTkCheckBox(dlg, text="Vytvořit zástupce na ploše",
                        variable=var_shortcut, font=ctk.CTkFont("", 12),
                        text_color=TEXT_BRIGHT, fg_color=KICK_GREEN, hover_color="#45d614",
                        ).grid(row=3, column=0, padx=32, pady=(0, 20), sticky="w")

        lbl_status = ctk.CTkLabel(dlg, text="", font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        lbl_status.grid(row=4, column=0, padx=32, pady=(0, 8))

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.grid(row=5, column=0, padx=32, pady=(0, 28), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        def _finish():
            flag.touch()
            if var_defender.get():
                lbl_status.configure(text="Čeká na potvrzení UAC…")
                dlg.update()
                self._add_defender_exclusion()
            if var_shortcut.get():
                self._create_shortcut()
            lbl_status.configure(text="Hotovo!")
            dlg.after(1200, dlg.destroy)

        def _skip():
            flag.touch()
            dlg.destroy()

        ctk.CTkButton(btn_row, text="Nastavit",
                      fg_color="#1e3a1e", hover_color="#2a4f2a",
                      text_color=KICK_GREEN, border_color=KICK_GREEN, border_width=1,
                      font=ctk.CTkFont("", 13, "bold"), height=42, corner_radius=8,
                      command=_finish
                      ).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(btn_row, text="Přeskočit",
                      fg_color="transparent", hover_color=CARD_BG,
                      text_color=TEXT_DIM, border_color=BORDER, border_width=1,
                      font=ctk.CTkFont("", 12), height=42, corner_radius=8,
                      command=_skip
                      ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _add_defender_exclusion(self):
        import ctypes
        exe_dir = str(Path(sys.executable).parent)
        ps_cmd  = f"Add-MpPreference -ExclusionPath '{exe_dir}'"
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f"-ExecutionPolicy Bypass -WindowStyle Hidden -Command \"{ps_cmd}\"",
            None, 1,
        )

    def _create_shortcut(self):
        try:
            exe_path = str(Path(sys.executable))
            work_dir = str(Path(sys.executable).parent)
            shortcut = str(Path.home() / "Desktop" / "KickBot.lnk")
            ps_cmd   = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{shortcut}'); "
                f"$s.TargetPath = '{exe_path}'; "
                f"$s.WorkingDirectory = '{work_dir}'; "
                f"$s.Save()"
            )
            import subprocess as _sp
            _sp.run(["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True, timeout=10)
            self._append_log("Zástupce na ploše vytvořen.", "success")
        except Exception as exc:
            self._append_log(f"Nelze vytvořit zástupce: {exc}", "warn")

    # ── Auto-update ───────────────────────────────────────────────────────────
    def _check_for_update(self):
        if getattr(sys, "frozen", False) and not (Path(sys.executable).parent / ".configured").exists():
            return
        def _worker():
            try:
                r = requests.get(GITHUB_API_URL, timeout=8,
                                 headers={"User-Agent": f"KickBot/{BUILD_VERSION}"})
                if r.status_code != 200:
                    return
                data    = r.json()
                tag     = data.get("tag_name", "").lstrip("v")
                if not tag or tag <= BUILD_VERSION:
                    return
                assets  = data.get("assets", [])
                zip_url = next(
                    (a["browser_download_url"] for a in assets
                     if a["name"].lower().endswith(".zip")),
                    None,
                )
                self.after(0, lambda: self._show_update_dialog(tag, zip_url))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _show_update_dialog(self, new_version: str, zip_url):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Dostupná aktualizace")
        dlg.configure(fg_color=DARK_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        dlg.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dlg, text="Dostupná aktualizace",
                     font=ctk.CTkFont("", 16, "bold"), text_color=KICK_GREEN
                     ).grid(row=0, column=0, padx=32, pady=(28, 6))
        ctk.CTkLabel(dlg,
                     text=f"Verze  {new_version}  je k dispozici.\nAktualni verze: {BUILD_VERSION}",
                     font=ctk.CTkFont("", 12), text_color=TEXT_MID, justify="center"
                     ).grid(row=1, column=0, padx=32, pady=(0, 16))

        lbl_progress = ctk.CTkLabel(dlg, text="", font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        lbl_progress.grid(row=2, column=0, padx=32, pady=(0, 4))

        progress_bar = ctk.CTkProgressBar(dlg, width=300, height=8,
                                           fg_color=CARD_BG, progress_color=KICK_GREEN)
        progress_bar.set(0)
        progress_bar.grid(row=3, column=0, padx=32, pady=(0, 20))
        progress_bar.grid_remove()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.grid(row=4, column=0, padx=32, pady=(0, 28), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        if zip_url:
            btn_update = ctk.CTkButton(btn_row, text="Stáhnout a aktualizovat",
                          fg_color="#1e3a1e", hover_color="#2a4f2a",
                          text_color=KICK_GREEN, border_color=KICK_GREEN, border_width=1,
                          font=ctk.CTkFont("", 13, "bold"), height=42, corner_radius=8)
            btn_update.configure(command=lambda: self._do_update(
                zip_url, dlg, btn_update, lbl_progress, progress_bar))
            btn_update.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        else:
            ctk.CTkButton(btn_row, text="Otevřít GitHub",
                          fg_color="#1e3a1e", hover_color="#2a4f2a",
                          text_color=KICK_GREEN, border_color=KICK_GREEN, border_width=1,
                          font=ctk.CTkFont("", 13, "bold"), height=42, corner_radius=8,
                          command=lambda: webbrowser.open(
                              f"https://github.com/{GITHUB_REPO}/releases/latest")
                          ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(btn_row, text="Přeskočit",
                      fg_color="transparent", hover_color=CARD_BG,
                      text_color=TEXT_DIM, border_color=BORDER, border_width=1,
                      font=ctk.CTkFont("", 12), height=42, corner_radius=8,
                      command=dlg.destroy
                      ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _do_update(self, zip_url: str, dlg, btn_update, lbl_progress, progress_bar):
        if not getattr(sys, "frozen", False):
            self._append_log(
                "Automatická aktualizace funguje pouze v .exe verzi.", "warn")
            dlg.destroy()
            return

        import zipfile, shutil as _shutil
        app_dir    = Path(sys.executable).parent
        parent_dir = app_dir.parent
        zip_path   = parent_dir / "_kickbot_update.zip"
        extract_to = parent_dir / "_kickbot_update"
        new_dir    = extract_to / app_dir.name
        old_dir    = parent_dir / "_KickBot_old"
        new_exe    = app_dir / Path(sys.executable).name
        log_path   = parent_dir / "kickbot_install_log.txt"

        def log(msg):
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                with open(log_path, "a", encoding="utf-8") as _f:
                    _f.write(f"[{ts}][PY] {msg}\n")
            except Exception:
                pass

        def _worker():
            try:
                log(f"=== Update start: {BUILD_VERSION}")
                log(f"app_dir   = {app_dir}")
                log(f"parent_dir= {parent_dir}")
                log(f"new_dir   = {new_dir}")
                log(f"old_dir   = {old_dir}")
                log(f"new_exe   = {new_exe}")

                self.after(0, lambda: btn_update.configure(state="disabled", text="Stahuji..."))
                self.after(0, progress_bar.grid)

                log(f"Downloading: {zip_url}")
                r = requests.get(zip_url, stream=True, timeout=180,
                                 headers={"User-Agent": f"KickBot/{BUILD_VERSION}"})
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                done  = 0
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done / total
                            self.after(0, lambda p=pct: progress_bar.set(p))
                            self.after(0, lambda p=pct: lbl_progress.configure(
                                text=f"Stahování…  {p*100:.0f} %"))
                log(f"Download OK: {done} bytes")

                self.after(0, lambda: lbl_progress.configure(text="Rozbaluji…"))
                log("Extracting zip...")
                if extract_to.exists():
                    _shutil.rmtree(extract_to)
                new_dir.mkdir(parents=True)
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(new_dir)
                zip_path.unlink()
                log(f"Extracted OK to {new_dir}")

                self.after(0, lambda: lbl_progress.configure(text="Instaluji…"))
                if old_dir.exists():
                    _shutil.rmtree(old_dir)

                import subprocess as _sp
                pid = os.getpid()
                ps1_path = parent_dir / "_kickbot_update.ps1"
                ps1_content = (
                    f"$log = '{log_path}'\n"
                    f"function Log($m) {{ Add-Content $log ('[PS] ' + $m) }}\n"
                    f"Log 'Script started, waiting for PID {pid}'\n"
                    f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue\n"
                    f"Log 'Process exited, sleeping 2s'\n"
                    f"Start-Sleep 2\n"
                    f"Log 'Move1 start'\n"
                    f"try {{ Move-Item '{app_dir}' '{old_dir}' -ErrorAction Stop; Log 'Move1 OK' }}\n"
                    f"catch {{ Log ('Move1 FAILED: ' + $_.Exception.Message); exit 1 }}\n"
                    f"if ((Test-Path '{old_dir}') -and (-not (Test-Path '{app_dir}'))) {{\n"
                    f"  Log 'Move2 start'\n"
                    f"  try {{ Move-Item '{new_dir}' '{app_dir}' -ErrorAction Stop; Log 'Move2 OK' }}\n"
                    f"  catch {{ Log ('Move2 FAILED: ' + $_.Exception.Message); exit 1 }}\n"
                    f"  Remove-Item '{extract_to}' -Recurse -Force -ErrorAction SilentlyContinue\n"
                    f"  Log 'Starting new exe'\n"
                    f"  Start-Process '{new_exe}'\n"
                    f"  Start-Sleep 20\n"
                    f"  Remove-Item '{old_dir}' -Recurse -Force -ErrorAction SilentlyContinue\n"
                    f"  Log 'Done'\n"
                    f"}} else {{\n"
                    f"  Log ('Condition FAILED: old=' + (Test-Path '{old_dir}') + ' app=' + (Test-Path '{app_dir}'))\n"
                    f"}}\n"
                    f"Remove-Item '{ps1_path}' -Force -ErrorAction SilentlyContinue\n"
                )
                ps1_path.write_text(ps1_content, encoding="utf-8-sig")
                log(f"Launching PowerShell -File (PID={pid})")
                _sp.Popen(
                    ["powershell", "-ExecutionPolicy", "Bypass",
                     "-WindowStyle", "Hidden", "-NonInteractive",
                     "-File", str(ps1_path)],
                    creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP
                )

                self.after(0, lambda: lbl_progress.configure(text="Hotovo! Spouštím novou verzi…"))
                self.after(800, self.destroy)

            except Exception as exc:
                log(f"EXCEPTION: {exc}")
                self.after(0, lambda: self._append_log(
                    f"Chyba při aktualizaci: {exc}", "error"))
                self.after(0, lambda: lbl_progress.configure(
                    text=f"Chyba: {exc}", text_color=RED_ERR))
                self.after(0, lambda: btn_update.configure(
                    state="normal", text="Zkusit znovu"))
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                    if extract_to.exists():
                        _shutil.rmtree(extract_to)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

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
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_right_panel()

    def _build_sidebar(self):
        outer = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, width=280)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_propagate(False)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        sb = ctk.CTkScrollableFrame(outer, fg_color=PANEL_BG, corner_radius=0,
                                     scrollbar_button_color=BORDER,
                                     scrollbar_fg_color=PANEL_BG)
        sb.grid(row=0, column=0, sticky="nsew")
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
            text=self._disconnected_sub(),
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
        self._log_main      = main
        self._log_collapsed = False
        lf = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        lf.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        lf.grid_columnconfigure(0, weight=1)
        lf.grid_rowconfigure(1, weight=1)
        self._log_frame = lf
        lhdr = ctk.CTkFrame(lf, fg_color="transparent")
        lhdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        lhdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(lhdr, text="Protokol",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        self.btn_clear_log = ctk.CTkButton(lhdr, text="Vymazat", width=70, height=24,
            fg_color="transparent", hover_color=BORDER, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), command=self._clear_log)
        self.btn_clear_log.grid(row=0, column=1, sticky="e")
        self.btn_log_toggle = ctk.CTkButton(lhdr, text="▼", width=28, height=24,
            fg_color="transparent", hover_color=BORDER, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 13), command=self._toggle_log)
        self.btn_log_toggle.grid(row=0, column=2, sticky="e", padx=(4, 0))
        self.log_box = ctk.CTkTextbox(lf, fg_color="transparent",
            font=ctk.CTkFont("Courier New", 11), text_color=TEXT_MID,
            wrap="word", scrollbar_button_color=BORDER)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    def _build_right_panel(self):
        rp = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, width=240)
        rp.grid(row=0, column=2, sticky="nsew", padx=(1, 0))
        rp.grid_propagate(False)
        rp.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rp, text="🎮 Ovládání", font=ctk.CTkFont("", 18, "bold"),
                     text_color=TEXT_BRIGHT).grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")
        ctk.CTkFrame(rp, height=1, fg_color=BORDER).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

        self._section(rp, "SOUTĚŽ", 2)

        self.btn_panel_start = ctk.CTkButton(rp, text="▶  Start soutěže",
            fg_color=KICK_GREEN, hover_color="#45d614", text_color="#000",
            font=ctk.CTkFont("", 13, "bold"), height=44, corner_radius=8,
            command=self._panel_start)
        self.btn_panel_start.grid(row=3, column=0, padx=16, pady=(4, 6), sticky="ew")

        self.btn_panel_stop = ctk.CTkButton(rp, text="⏹  Stop soutěže",
            fg_color="#2a1a1a", hover_color="#3a2020", text_color="#ff6666",
            border_color="#ff4444", border_width=1,
            font=ctk.CTkFont("", 12), height=36, corner_radius=8,
            command=self._panel_stop)
        self.btn_panel_stop.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")

        ctk.CTkFrame(rp, height=1, fg_color=BORDER).grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))

        self._section(rp, "VYHODNOCENÍ", 6)
        ctk.CTkLabel(rp, text="Výherní číslo", font=ctk.CTkFont("", 12),
                     text_color=TEXT_MID).grid(row=7, column=0, padx=16, pady=(4, 2), sticky="w")
        self.entry_winner_num = ctk.CTkEntry(rp, fg_color=CARD_BG, border_color=BORDER,
            text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 15, "bold"),
            height=40, corner_radius=6, placeholder_text="např. 254")
        self.entry_winner_num.grid(row=8, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.btn_evaluate = ctk.CTkButton(rp, text="🏆  Zobraz výsledek",
            fg_color="#1e2a3a", hover_color="#2a3a4f", text_color="#4da6ff",
            border_color="#2a4a6a", border_width=1,
            font=ctk.CTkFont("", 13, "bold"), height=44, corner_radius=8,
            command=self._panel_evaluate)
        self.btn_evaluate.grid(row=9, column=0, padx=16, pady=(0, 16), sticky="ew")

        ctk.CTkFrame(rp, height=1, fg_color=BORDER).grid(row=10, column=0, sticky="ew", padx=16, pady=(0, 12))

        self._section(rp, "VÝSLEDKY — TOP 3", 11)

        self.results_frame = ctk.CTkFrame(rp, fg_color="transparent")
        self.results_frame.grid(row=12, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.lbl_results_placeholder = ctk.CTkLabel(self.results_frame,
            text="Zadej výherní číslo\na klikni na\n'Zobraz výsledek'.",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM, justify="center")
        self.lbl_results_placeholder.grid(row=0, column=0, pady=16)

        self._result_rows = []
        rp.grid_rowconfigure(12, weight=1)

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

    def _disconnected_sub(self) -> str:
        if self._token_status in ("valid", "refresh"):
            return "Klikni na Spustit bota"
        return "Klikni na Přihlásit bota"

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
                self.after(0, lambda: self.banner_sub.configure(text=self._disconnected_sub()))
        self.engine.do_oauth(cid, cs, done)

    def _do_login_reset(self):
        """Smaže uložený token a vynutí nové přihlášení."""
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self.engine.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._token_status = "none"
        self._refresh_token_label()
        self.banner_sub.configure(text=self._disconnected_sub())
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

    def _panel_start(self):
        if not self.engine.running:
            self._append_log("Bot není připojen.", "error"); return
        if self.engine.collecting:
            self._append_log("Soutěž už probíhá.", "warn"); return
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine.collecting = True
        self.engine.guesses = {}
        self.engine.guess_cb([])
        self.engine.log("▶ Soutěž zahájena", "success")
        self.engine.status_cb("collecting")
        self.engine.send_chat(self.engine._msg("soutez_zahajena"), cid, cs)

    def _panel_stop(self):
        if not self.engine.running:
            self._append_log("Bot není připojen.", "error"); return
        if not self.engine.collecting:
            self._append_log("Žádná soutěž momentálně neprobíhá.", "warn"); return
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine.collecting = False
        self.engine.log(f"⏹ Sběr ukončen. Odhadů: {len(self.engine.guesses)}", "warn")
        self.engine.status_cb("stopped")
        self.engine.send_chat(
            self.engine._msg("sber_ukoncen", pocet=len(self.engine.guesses)), cid, cs)

    def _panel_evaluate(self):
        text = self.entry_winner_num.get().strip()
        if not text:
            self._append_log("Zadej výherní číslo.", "error"); return
        try:
            n = int(text)
        except ValueError:
            self._append_log("Neplatné číslo — zadej celé číslo.", "error"); return
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        self.engine._evaluate(n, cid, cs)

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
            "disconnected": ("⚪", "Odpojeno",            self._disconnected_sub(),          TEXT_DIM),
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

    def _update_results(self, correct, sorted_results):
        def _redraw():
            for w in self._result_rows:
                w.destroy()
            self._result_rows.clear()
            if not sorted_results:
                self.lbl_results_placeholder.configure(
                    text="Nikdo nic nehádal.")
                self.lbl_results_placeholder.grid(row=0, column=0, pady=16)
                return
            self.lbl_results_placeholder.grid_remove()
            medals = ["🥇", "🥈", "🥉"]
            top3 = sorted_results[:3]
            for i, (user, guess, dist) in enumerate(top3):
                medal = medals[i] if i < len(medals) else "  "
                row_f = ctk.CTkFrame(self.results_frame, fg_color=CARD_BG, corner_radius=6)
                row_f.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
                row_f.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(row_f, text=medal,
                             font=ctk.CTkFont("", 16)).grid(row=0, column=0, padx=(8, 4), pady=8)
                ctk.CTkLabel(row_f, text=user, font=ctk.CTkFont("", 11, "bold"),
                             text_color=TEXT_BRIGHT, anchor="w"
                             ).grid(row=0, column=1, sticky="w", padx=4, pady=8)
                color = KICK_GREEN if dist == 0 else (YELLOW_WARN if i == 0 else TEXT_MID)
                label = str(guess) if dist == 0 else f"{guess}\n±{dist}"
                ctk.CTkLabel(row_f, text=label, font=ctk.CTkFont("", 11),
                             text_color=color, anchor="e", justify="right"
                             ).grid(row=0, column=2, padx=8, pady=8, sticky="e")
                self._result_rows.append(row_f)
        self.after(0, _redraw)

    def _toggle_log(self):
        if self._log_collapsed:
            self._log_frame.grid_rowconfigure(1, weight=1)
            self.log_box.grid()
            self._log_frame.grid_propagate(True)
            self._log_main.grid_rowconfigure(3, weight=1)
            self.btn_clear_log.grid()
            self.btn_log_toggle.configure(text="▼")
            self._log_collapsed = False
        else:
            self.btn_clear_log.grid_remove()
            self.log_box.grid_remove()
            self._log_frame.grid_rowconfigure(1, weight=0)
            self._log_frame.configure(height=46)
            self._log_frame.grid_propagate(False)
            self._log_main.grid_rowconfigure(3, weight=0)
            self.btn_log_toggle.configure(text="▲")
            self._log_collapsed = True
        self._save_log_collapsed_state(self._log_collapsed)

    def _save_log_collapsed_state(self, collapsed: bool):
        try:
            raw = json.loads(BOT_CONFIG_FILE.read_text(encoding="utf-8"))
            raw.setdefault("gui", {})["log_collapsed"] = collapsed
            BOT_CONFIG_FILE.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            self.engine.bcfg.setdefault("gui", {})["log_collapsed"] = collapsed
        except Exception:
            pass

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
