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

# ── Kick API konstanty ───────────────────────────────────────────────────────
KICK_AUTH_URL  = "https://id.kick.com/oauth/authorize"
KICK_TOKEN_URL = "https://id.kick.com/oauth/token"
KICK_API_URL   = "https://api.kick.com/public/v1"
KICK_SCOPES    = "user:read channel:read chat:write"
PUSHER_WS      = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
                  "?protocol=7&client=js&version=8.4.0-rc2&flash=false")
REDIRECT_URI   = "http://localhost:7878/callback"
TOKEN_FILE     = Path("kick_tokens.json")
CONFIG_FILE    = Path("kick_config.json")

# ── Barvy / témata ───────────────────────────────────────────────────────────
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
#  Logika bota (stejná jako CLI verze, bez print výstupů)
# ════════════════════════════════════════════════════════════════════════════
class BotEngine:
    def __init__(self, log_cb, status_cb, guess_cb):
        self.log_cb    = log_cb    # callback pro log zprávy
        self.status_cb = status_cb # callback pro status bar
        self.guess_cb  = guess_cb  # callback pro aktualizaci tabulky odhadů

        self.collecting      = False
        self.guesses         = {}   # {username: int}
        self.broadcaster_id  = 0
        self.chatroom_id     = 0
        self.ws              = None
        self.ws_thread       = None
        self.running         = False

        self.tokens = {"access_token": "", "refresh_token": "", "expires_at": 0}
        self._load_tokens()

    # ── Persistence ──────────────────────────────────────────────────────────
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
        """Spustí OAuth flow v samostatném vlákně, zavolá on_done(True/False)."""
        def run():
            verifier, challenge = self._pkce_pair()
            state_val = secrets.token_urlsafe(16)
            params = {
                "response_type": "code", "client_id": client_id,
                "redirect_uri": REDIRECT_URI, "scope": KICK_SCOPES,
                "code_challenge": challenge, "code_challenge_method": "S256",
                "state": state_val,
            }
            auth_url = f"{KICK_AUTH_URL}?{urlencode(params)}"
            self.log("Otevírám prohlížeč pro přihlášení ...", "info")
            webbrowser.open(auth_url)

            result = {}
            class H(BaseHTTPRequestHandler):
                def do_GET(s):
                    qs = parse_qs(urlparse(s.path).query)
                    result["code"] = qs.get("code", [""])[0]
                    s.send_response(200)
                    s.send_header("Content-Type", "text/html; charset=utf-8")
                    s.end_headers()
                    s.wfile.write("<html><body style='font-family:sans-serif;text-align:center;padding:60px;background:#0d0d0d;color:#53FC18'><h2>✅ Bot autorizován!</h2><p style='color:#aaa'>Toto okno můžeš zavřít.</p></body></html>".encode())
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
                self.log("Autorizace zrušena nebo vypršela.", "error")
                on_done(False); return

            try:
                resp = requests.post(KICK_TOKEN_URL, data={
                    "grant_type": "authorization_code", "client_id": client_id,
                    "client_secret": client_secret, "redirect_uri": REDIRECT_URI,
                    "code": code, "code_verifier": verifier,
                }, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                self.tokens["access_token"]  = data["access_token"]
                self.tokens["refresh_token"] = data.get("refresh_token", "")
                self.tokens["expires_at"]    = time.time() + data.get("expires_in", 3600)
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
            data = resp.json()
            self.tokens["access_token"]  = data["access_token"]
            self.tokens["refresh_token"] = data.get("refresh_token", self.tokens["refresh_token"])
            self.tokens["expires_at"]    = time.time() + data.get("expires_in", 3600)
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
            if not resp.ok:
                self.log(f"Chat API chyba: {resp.status_code}", "warn")
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
        username = sender.get("username", "???")
        text = content.strip()

        if self.is_moderator(sender):
            lower = text.lower()
            if lower == "!start":
                if self.collecting:
                    self.send_chat("⚠️ Soutěž už probíhá!", client_id, client_secret)
                else:
                    self.collecting = True
                    self.guesses = {}
                    self.guess_cb([])
                    self.log("▶ Soutěž zahájena", "success")
                    self.status_cb("collecting")
                    self.send_chat("🎯 Soutěž zahájena! Napište číslo do chatu — počítá se váš POSLEDNÍ odhad.", client_id, client_secret)
                return
            if lower == "!stop":
                if not self.collecting:
                    pass
                    #self.send_chat("⚠️ Žádná soutěž neprobíhá.", client_id, client_secret)
                else:
                    self.collecting = False
                    self.log(f"⏹ Sběr ukončen. Odhadů: {len(self.guesses)}", "warn")
                    self.status_cb("stopped")
                    self.send_chat(f"🛑 Sběr ukončen. Celkem: {len(self.guesses)} odhadů.", client_id, client_secret)
                return
            if lower == "!reset":
                self.collecting = False
                self.guesses = {}
                self.guess_cb([])
                self.log("🔄 Reset", "info")
                self.status_cb("idle")
                self.send_chat("🔄 Soutěž resetována.", client_id, client_secret)
                return
            if lower.startswith("!cislo"):
                n = self.extract_int(text[6:])
                if n is None:
                    self.send_chat("⚠️ Použití: !cislo <číslo>", client_id, client_secret)
                else:
                    self._evaluate(n, client_id, client_secret)
                return

        if self.collecting:
            guess = self.extract_int(text)
            if guess is not None:
                prev = self.guesses.get(username)
                self.guesses[username] = guess
                if prev is None:
                    self.log(f"  {username} → {guess}", "info")
                else:
                    self.log(f"  {username} → {guess}  (byl: {prev})", "dim")
                # Aktualizuj tabulku (seřazeno abecedně)
                rows = sorted(self.guesses.items())
                self.guess_cb(rows)

    def _evaluate(self, correct, client_id, client_secret):
        self.log(f"━━━ Vyhodnocení — správné číslo: {correct} ━━━", "success")
        if not self.guesses:
            self.send_chat("❌ Žádné odhady!", client_id, client_secret)
            self.collecting = False
            self.guesses = {}
            self.guess_cb([])
            self.log("🔄 Reset", "info")
            self.status_cb("idle")
            return
        distances = {u: abs(g - correct) for u, g in self.guesses.items()}
        min_dist  = min(distances.values())
        winners   = [(u, self.guesses[u]) for u, d in distances.items() if d == min_dist]
        prefix    = "🎯 PŘESNÝ ZÁSAH!" if min_dist == 0 else f"🏆 Nejblíže (rozdíl: {min_dist}):"
        wstr      = ", ".join(f"{u} [{g}]" for u, g in winners)
        self.send_chat(f"{prefix} {wstr} | Správné číslo: {correct}", client_id, client_secret)
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

        def on_open(ws):
            ws.send(json.dumps({"event": "pusher:subscribe",
                                "data": {"auth": "", "channel": f"chatrooms.{cid}.v2"}}))
            self.log("✅ Připojeno k chatu!", "success")
            self.running = True
            self.status_cb("idle")
            self.send_chat("🤖 Bot je online! Moderátor může zadat !start.", client_id, client_secret)
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
        self.title("Kick Soutěžní Bot")
        self.geometry("960x700")
        self.minsize(860, 720)
        self.configure(fg_color=DARK_BG)

        self._load_config()
        self.engine = BotEngine(
            log_cb    = self._append_log,
            status_cb = self._set_status,
            guess_cb  = self._update_guesses,
        )
        # Check existing token
        if self.engine._token_valid():
            self._token_status = "valid"
        elif self.engine.tokens.get("refresh_token"):
            self._token_status = "refresh"
        else:
            self._token_status = "none"

        self._build_ui()
        self._refresh_token_label()

    # ── Config persistence ────────────────────────────────────────────────────
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

    # ── UI build ──────────────────────────────────────────────────────────────
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
        logo = ctk.CTkLabel(sb, text="🎯 KickBot", font=ctk.CTkFont("", 22, "bold"),
                            text_color=KICK_GREEN)
        logo.grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        sub = ctk.CTkLabel(sb, text="Soutěžní bot", font=ctk.CTkFont("", 12),
                           text_color=TEXT_DIM)
        sub.grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")

        sep = ctk.CTkFrame(sb, height=1, fg_color=BORDER)
        sep.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 20))

        # ── Nastavení ────────────────────────────────────────────────────────
        self._section(sb, "NASTAVENÍ", 3)

        self._label(sb, "Client ID", 4)
        self.entry_cid = self._entry(sb, 5, self._cfg["client_id"], show="")

        self._label(sb, "Client Secret", 6)
        self.entry_csecret = self._entry(sb, 7, self._cfg["client_secret"], show="•")

        self._label(sb, "Název kanálu (slug)", 8)
        self.entry_channel = self._entry(sb, 9, self._cfg["channel"])

        # Token status
        self.lbl_token = ctk.CTkLabel(sb, text="", font=ctk.CTkFont("", 11),
                                      wraplength=220, justify="left")
        self.lbl_token.grid(row=10, column=0, padx=16, pady=(8, 4), sticky="w")

        self.btn_auth = ctk.CTkButton(sb, text="🔑  Přihlásit bota",
            fg_color="#1e3a1e", hover_color="#2a4f2a", text_color=KICK_GREEN,
            border_color=KICK_GREEN, border_width=1,
            font=ctk.CTkFont("", 12, "bold"), height=38, corner_radius=8,
            command=self._do_auth)
        self.btn_auth.grid(row=11, column=0, padx=16, pady=(4, 16), sticky="ew")

        sep2 = ctk.CTkFrame(sb, height=1, fg_color=BORDER)
        sep2.grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 20))

        # ── Připojení ────────────────────────────────────────────────────────
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
        self.btn_disconnect.grid(row=15, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Status indikátor
        self.lbl_status = ctk.CTkLabel(sb, text="⚪ Odpojeno",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_status.grid(row=16, column=0, padx=16, pady=(0, 8), sticky="w")

        # Spacer
        sb.grid_rowconfigure(17, weight=1)

        # Odkaz na dokumentaci
        help_btn = ctk.CTkButton(sb, text="❓ Jak získat Client ID?",
            fg_color="transparent", hover_color=CARD_BG, text_color=TEXT_DIM,
            font=ctk.CTkFont("", 11), height=28, anchor="w",
            command=lambda: webbrowser.open("https://kick.com/settings/developer"))
        help_btn.grid(row=18, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=(1, 0))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=2)
        main.grid_rowconfigure(3, weight=1)

        # ── Status banner ─────────────────────────────────────────────────────
        self.banner = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12, height=64)
        self.banner.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
        self.banner.grid_propagate(False)
        self.banner.grid_columnconfigure(1, weight=1)

        self.banner_icon = ctk.CTkLabel(self.banner, text="⚪",
            font=ctk.CTkFont("", 28))
        self.banner_icon.grid(row=0, column=0, padx=(20, 12), pady=12)

        self.banner_text = ctk.CTkLabel(self.banner, text="Bot je odpojený",
            font=ctk.CTkFont("", 16, "bold"), text_color=TEXT_MID, anchor="w")
        self.banner_text.grid(row=0, column=1, sticky="w")

        self.banner_sub = ctk.CTkLabel(self.banner, text="Vyplň nastavení a klikni na Spustit bota",
            font=ctk.CTkFont("", 11), text_color=TEXT_DIM, anchor="e")
        self.banner_sub.grid(row=0, column=2, padx=20, sticky="e")

        # ── Tabulka odhadů ────────────────────────────────────────────────────
        guesses_frame = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        guesses_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        guesses_frame.grid_columnconfigure(0, weight=1)
        guesses_frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(guesses_frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Odhady hráčů",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        self.lbl_count = ctk.CTkLabel(hdr, text="0 hráčů",
                     font=ctk.CTkFont("", 11), text_color=TEXT_DIM)
        self.lbl_count.grid(row=0, column=1, sticky="e")

        # Scrollable list
        self.guess_scroll = ctk.CTkScrollableFrame(
            guesses_frame, fg_color="transparent", scrollbar_button_color=BORDER)
        self.guess_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.guess_scroll.grid_columnconfigure(0, weight=1)
        self.guess_scroll.grid_columnconfigure(1, weight=0)
        self._guess_rows = []

        # Placeholder
        self.guess_placeholder = ctk.CTkLabel(
            self.guess_scroll,
            text="Zatím žádné odhady.\nZahaj soutěž příkazem !start v chatu.",
            font=ctk.CTkFont("", 12), text_color=TEXT_DIM, justify="center")
        self.guess_placeholder.grid(row=0, column=0, columnspan=2, pady=30)

        # ── Log ───────────────────────────────────────────────────────────────
        log_frame = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=12)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_hdr = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        log_hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(log_hdr, text="Protokol",
                     font=ctk.CTkFont("", 14, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        clear_btn = ctk.CTkButton(log_hdr, text="Vymazat", width=70, height=24,
            fg_color="transparent", hover_color=BORDER,
            text_color=TEXT_DIM, font=ctk.CTkFont("", 11),
            command=self._clear_log)
        clear_btn.grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(log_frame, fg_color="transparent",
            font=ctk.CTkFont("Courier New", 11),
            text_color=TEXT_MID, wrap="word",
            scrollbar_button_color=BORDER)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    # ── Helper widgety ────────────────────────────────────────────────────────
    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("", 10, "bold"),
                     text_color=TEXT_DIM).grid(
            row=row, column=0, padx=16, pady=(0, 4), sticky="w")

    def _label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("", 12),
                     text_color=TEXT_MID).grid(
            row=row, column=0, padx=16, pady=(8, 2), sticky="w")

    def _entry(self, parent, row, default="", show=""):
        e = ctk.CTkEntry(parent, fg_color=CARD_BG, border_color=BORDER,
                         text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 12),
                         height=34, corner_radius=6, show=show)
        e.insert(0, default)
        e.grid(row=row, column=0, padx=16, pady=(0, 4), sticky="ew")
        return e

    # ── Token label ───────────────────────────────────────────────────────────
    def _refresh_token_label(self):
        if self._token_status == "valid":
            self.lbl_token.configure(text="✅ Bot je přihlášen", text_color=KICK_GREEN)
        elif self._token_status == "refresh":
            self.lbl_token.configure(text="🔄 Token bude obnoven automaticky", text_color=YELLOW_WARN)
        else:
            self.lbl_token.configure(text="⚠️ Bot není přihlášen — klikni níže", text_color=YELLOW_WARN)

    # ── Akce ─────────────────────────────────────────────────────────────────
    def _do_auth(self):
        cid = self.entry_cid.get().strip()
        cs  = self.entry_csecret.get().strip()
        if not cid or not cs:
            self._append_log("Vyplň Client ID a Client Secret!", "error")
            return
        self._save_config()
        self.btn_auth.configure(state="disabled", text="⏳ Čekám na prohlížeč ...")

        def done(ok):
            self.after(0, lambda: self.btn_auth.configure(
                state="normal", text="🔑  Přihlásit bota"))
            if ok:
                self._token_status = "valid"
                self.after(0, self._refresh_token_label)

        self.engine.do_oauth(cid, cs, done)

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
                self.after(0, lambda: self.btn_connect.configure(
                    state="disabled", text="▶  Spustit bota"))
                self.after(0, lambda: self.btn_disconnect.configure(state="normal"))
            else:
                self.after(0, lambda: self.btn_connect.configure(
                    state="normal", text="▶  Spustit bota"))
                self._append_log("Připojení selhalo.", "error")

        self.engine.connect(channel, cid, cs, connected)

    def _do_disconnect(self):
        self.engine.disconnect()
        self.btn_connect.configure(state="normal", text="▶  Spustit bota")
        self.btn_disconnect.configure(state="disabled")

    # ── Callbacks z engine ────────────────────────────────────────────────────
    def _append_log(self, msg, level="info"):
        colors = {
            "info":    TEXT_MID,
            "success": KICK_GREEN,
            "warn":    YELLOW_WARN,
            "error":   RED_ERR,
            "dim":     TEXT_DIM,
        }
        color = colors.get(level, TEXT_MID)
        ts    = datetime.now().strftime("%H:%M:%S")
        line  = f"[{ts}] {msg}\n"

        def _insert():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line)
            # Obarvi poslední řádek (aproximace — ctk textbox nepodporuje tags plně)
            self.log_box.configure(state="disabled")
            self.log_box.see("end")

        self.after(0, _insert)

    def _set_status(self, status):
        configs = {
            "idle":         ("🟢", "Bot je online",         "Čeká na !start od moderátora",        KICK_GREEN),
            "collecting":   ("🔴", "Sbírám odhady!",        "Moderátor zadá !stop pro ukončení",   "#ff4444"),
            "stopped":      ("🟡", "Sběr ukončen",          "Moderátor zadá !cislo <číslo>",        YELLOW_WARN),
            "done":         ("🏆", "Výsledky vyhlášeny!",   "Čeká na !start od moderátora",             KICK_GREEN),
            #"done":         ("🏆", "Výsledky vyhlášeny!",   "Resetuj příkazem !reset",             KICK_GREEN),
            "disconnected": ("⚪", "Odpojeno",              "Klikni na Spustit bota",              TEXT_DIM),
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
            # Smaž staré řádky
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
                row_f.grid(row=i, column=0, columnspan=2, sticky="ew",
                           padx=4, pady=1)
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


# ── Spuštění ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
