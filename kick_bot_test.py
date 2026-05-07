"""
Kick Bot Test Simulator
Simuluje zprávy z Kick chatu pro testování kick_bot_gui.py v DEBUG módu.
Instalace: pip install customtkinter requests
Spuštění:  python kick_bot_test.py
"""

import json, threading
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
import requests

TEST_CONFIG_FILE = Path("bot_test_config.json")

DEFAULT_TEST_CONFIG = {
    "target_url":  "http://localhost:7879/simulate",
    "num_users":   3,
    "users":       [],
}

KICK_GREEN  = "#53FC18"
DARK_BG     = "#0d0d0d"
PANEL_BG    = "#141414"
CARD_BG     = "#1a1a1a"
BORDER      = "#2a2a2a"
TEXT_DIM    = "#666666"
TEXT_MID    = "#aaaaaa"
TEXT_BRIGHT = "#f0f0f0"
YELLOW_WARN = "#ffcc00"
RED_ERR     = "#ff4444"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


def load_test_config() -> dict:
    import copy
    cfg = copy.deepcopy(DEFAULT_TEST_CONFIG)
    if TEST_CONFIG_FILE.exists():
        try:
            user = json.loads(TEST_CONFIG_FILE.read_text(encoding="utf-8"))
            for k in ("target_url", "num_users", "users"):
                if k in user:
                    cfg[k] = user[k]
        except Exception:
            pass
    return cfg


def save_test_config(cfg: dict):
    TEST_CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kick Bot Test Simulator")
        self.geometry("820x620")
        self.minsize(640, 440)
        self.configure(fg_color=DARK_BG)

        self._cfg       = load_test_config()
        self._user_rows = []  # list of dicts: frame, name Entry, msg Entry, mod BooleanVar

        self._build_ui()
        self._apply_num_users(int(self._cfg.get("num_users", 3)))

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=2)   # users area
        self.grid_rowconfigure(4, weight=1)   # log area

        # Header
        hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="🧪 Kick Bot Test Simulator",
                     font=ctk.CTkFont("", 18, "bold"), text_color=KICK_GREEN
                     ).grid(row=0, column=0, padx=20, pady=14, sticky="w")
        ctk.CTkLabel(hdr, text="Simulátor Kick chatu pro DEBUG mód",
                     font=ctk.CTkFont("", 11), text_color=TEXT_DIM
                     ).grid(row=0, column=1, padx=4, pady=14, sticky="w")

        # Toolbar: URL + počet uživatelů
        bar = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=46)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="Cíl:", font=ctk.CTkFont("", 11),
                     text_color=TEXT_MID).grid(row=0, column=0, padx=(16, 6), pady=9)
        self.entry_url = ctk.CTkEntry(bar, fg_color=PANEL_BG, border_color=BORDER,
                                      text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 12),
                                      height=28, corner_radius=5)
        self.entry_url.insert(0, self._cfg.get("target_url", DEFAULT_TEST_CONFIG["target_url"]))
        self.entry_url.grid(row=0, column=1, padx=(0, 10), pady=9, sticky="ew")

        ctk.CTkLabel(bar, text="Uživatelů (1–10):", font=ctk.CTkFont("", 11),
                     text_color=TEXT_MID).grid(row=0, column=2, padx=(0, 6), pady=9)
        self.entry_num = ctk.CTkEntry(bar, fg_color=PANEL_BG, border_color=BORDER,
                                      text_color=TEXT_BRIGHT,
                                      font=ctk.CTkFont("", 12, "bold"),
                                      width=46, height=28, corner_radius=5)
        self.entry_num.insert(0, str(self._cfg.get("num_users", 3)))
        self.entry_num.grid(row=0, column=3, padx=(0, 6), pady=9)

        ctk.CTkButton(bar, text="Použít", width=70, height=28,
                      fg_color=KICK_GREEN, hover_color="#45d614", text_color="#000",
                      font=ctk.CTkFont("", 11, "bold"), corner_radius=5,
                      command=self._on_apply_users
                      ).grid(row=0, column=4, padx=(0, 6), pady=9)
        ctk.CTkButton(bar, text="💾 Uložit", width=80, height=28,
                      fg_color="transparent", hover_color=BORDER, text_color=TEXT_MID,
                      border_color=BORDER, border_width=1,
                      font=ctk.CTkFont("", 11), corner_radius=5,
                      command=self._save_cfg
                      ).grid(row=0, column=5, padx=(0, 16), pady=9)

        # Záhlaví sloupců
        col_hdr = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0, height=28)
        col_hdr.grid(row=2, column=0, sticky="new")   # sticky="new" = jen horní okraj
        col_hdr.grid_propagate(False)
        col_hdr.grid_columnconfigure(1, weight=1)
        col_hdr.grid_columnconfigure(2, weight=2)
        ctk.CTkLabel(col_hdr, text="#",
                     font=ctk.CTkFont("", 10), text_color=TEXT_DIM, width=32
                     ).grid(row=0, column=0, padx=(12, 4))
        ctk.CTkLabel(col_hdr, text="Jméno",
                     font=ctk.CTkFont("", 10), text_color=TEXT_DIM
                     ).grid(row=0, column=1, sticky="w", padx=4)
        ctk.CTkLabel(col_hdr, text="Zpráva",
                     font=ctk.CTkFont("", 10), text_color=TEXT_DIM
                     ).grid(row=0, column=2, sticky="w", padx=4)
        ctk.CTkLabel(col_hdr, text="Mod",
                     font=ctk.CTkFont("", 10), text_color=TEXT_DIM, width=36
                     ).grid(row=0, column=3, padx=4)
        ctk.CTkLabel(col_hdr, text="",
                     width=90).grid(row=0, column=4)

        # Scrollovatelná oblast uživatelů
        self.users_scroll = ctk.CTkScrollableFrame(self, fg_color=DARK_BG,
                                                    scrollbar_button_color=BORDER)
        self.users_scroll.grid(row=2, column=0, sticky="nsew", padx=0, pady=(30, 0))
        self.users_scroll.grid_columnconfigure(0, weight=1)

        # Oddělovač
        ctk.CTkFrame(self, fg_color=BORDER, height=1,
                     corner_radius=0).grid(row=3, column=0, sticky="ew")

        # Log
        log_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_hdr = ctk.CTkFrame(log_frame, fg_color="transparent", height=32)
        log_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 0))
        log_hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(log_hdr, text="Protokol",
                     font=ctk.CTkFont("", 12, "bold"), text_color=TEXT_BRIGHT
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(log_hdr, text="Vymazat", width=70, height=22,
                      fg_color="transparent", hover_color=BORDER, text_color=TEXT_DIM,
                      font=ctk.CTkFont("", 10), command=self._clear_log
                      ).grid(row=0, column=1, sticky="e")

        self.log_box = ctk.CTkTextbox(log_frame, fg_color="transparent",
                                      font=ctk.CTkFont("Courier New", 11),
                                      text_color=TEXT_MID, wrap="word",
                                      scrollbar_button_color=BORDER, height=110)
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.log_box.configure(state="disabled")

    # ── Uživatelé ─────────────────────────────────────────────────────────────
    def _on_apply_users(self):
        try:
            n = max(1, min(10, int(self.entry_num.get().strip())))
        except ValueError:
            n = 3
        self.entry_num.delete(0, "end")
        self.entry_num.insert(0, str(n))
        self._apply_num_users(n)

    def _apply_num_users(self, n: int):
        while len(self._user_rows) > n:
            row_data = self._user_rows.pop()
            row_data["frame"].destroy()
        saved = self._cfg.get("users", [])
        while len(self._user_rows) < n:
            idx    = len(self._user_rows)
            name   = saved[idx]["name"] if idx < len(saved) else f"Hráč{idx + 1}"
            is_mod = saved[idx].get("is_mod", False) if idx < len(saved) else False
            self._add_user_row(idx, name, is_mod)

    def _add_user_row(self, idx: int, default_name: str = "", default_mod: bool = False):
        row_f = ctk.CTkFrame(self.users_scroll,
                             fg_color=CARD_BG if idx % 2 == 0 else PANEL_BG,
                             corner_radius=6, height=48)
        row_f.grid(row=idx, column=0, sticky="ew", padx=6, pady=2)
        row_f.grid_propagate(False)
        row_f.grid_columnconfigure(1, weight=1)
        row_f.grid_columnconfigure(2, weight=2)

        ctk.CTkLabel(row_f, text=str(idx + 1), font=ctk.CTkFont("", 11),
                     text_color=TEXT_DIM, width=32
                     ).grid(row=0, column=0, padx=(10, 4), pady=10)

        name_e = ctk.CTkEntry(row_f, fg_color=DARK_BG, border_color=BORDER,
                               text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 12),
                               height=30, corner_radius=5, placeholder_text="Jméno")
        name_e.insert(0, default_name)
        name_e.grid(row=0, column=1, padx=(0, 6), pady=9, sticky="ew")

        msg_e = ctk.CTkEntry(row_f, fg_color=DARK_BG, border_color=BORDER,
                              text_color=TEXT_BRIGHT, font=ctk.CTkFont("", 12),
                              height=30, corner_radius=5, placeholder_text="Zpráva do chatu…")
        msg_e.grid(row=0, column=2, padx=(0, 6), pady=9, sticky="ew")
        msg_e.bind("<Return>", lambda e, i=idx: self._send(i))

        mod_var = ctk.BooleanVar(value=default_mod)
        ctk.CTkCheckBox(row_f, text="", variable=mod_var,
                        width=28, checkbox_width=18, checkbox_height=18,
                        fg_color=KICK_GREEN, hover_color="#45d614"
                        ).grid(row=0, column=3, padx=(0, 4), pady=10)

        ctk.CTkButton(row_f, text="Odeslat", width=84, height=30,
                      fg_color="#1e3a1e", hover_color="#2a4f2a",
                      text_color=KICK_GREEN, border_color=KICK_GREEN, border_width=1,
                      font=ctk.CTkFont("", 11, "bold"), corner_radius=5,
                      command=lambda i=idx: self._send(i)
                      ).grid(row=0, column=4, padx=(0, 10), pady=9)

        self._user_rows.append({"frame": row_f, "name": name_e,
                                 "msg": msg_e, "mod": mod_var})

    # ── Odesílání ─────────────────────────────────────────────────────────────
    def _send(self, idx: int):
        row    = self._user_rows[idx]
        name   = row["name"].get().strip() or f"Hráč{idx + 1}"
        msg    = row["msg"].get().strip()
        is_mod = row["mod"].get()

        if not msg:
            self._log(f"[{idx+1}] {name}: prázdná zpráva — přeskočeno.", "warn")
            return

        badges  = [{"type": "moderator"}] if is_mod else []
        payload = {
            "sender":  {"username": name, "identity": {"badges": badges}},
            "content": msg,
        }
        url = self.entry_url.get().strip()

        def post():
            try:
                r = requests.post(url, json=payload, timeout=5)
                badge_str = " [MOD]" if is_mod else ""
                if r.ok:
                    self._log(f"[{idx+1}] ✅ {name}{badge_str} → \"{msg}\"", "success")
                else:
                    self._log(
                        f"[{idx+1}] ❌ HTTP {r.status_code} — {name}{badge_str}: \"{msg}\"",
                        "error")
            except Exception as e:
                self._log(f"[{idx+1}] ❌ Spojení selhalo: {e}", "error")

        threading.Thread(target=post, daemon=True).start()

    # ── Config ────────────────────────────────────────────────────────────────
    def _save_cfg(self):
        users = [{"name": r["name"].get().strip(), "is_mod": r["mod"].get()}
                 for r in self._user_rows]
        cfg = {
            "target_url": self.entry_url.get().strip(),
            "num_users":  len(self._user_rows),
            "users":      users,
        }
        save_test_config(cfg)
        self._log("💾 Konfigurace uložena do bot_test_config.json", "info")

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log(self, msg: str, level: str = "info"):
        colors = {"success": KICK_GREEN, "error": RED_ERR,
                  "warn": YELLOW_WARN, "info": TEXT_MID}
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"

        def _insert():
            self.log_box.configure(state="normal")
            start = self.log_box.index("end-1c")
            self.log_box.insert("end", line)
            end   = self.log_box.index("end-1c")
            tag   = f"c_{level}"
            self.log_box.tag_config(tag, foreground=colors.get(level, TEXT_MID))
            self.log_box.tag_add(tag, start, end)
            self.log_box.configure(state="disabled")
            self.log_box.see("end")

        self.after(0, _insert)

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
