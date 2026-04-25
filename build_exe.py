"""
build_exe.py — vytvoří KickBot.exe pomocí PyInstaller

Spuštění (na Windows):
    pip install pyinstaller
    python build_exe.py
"""

import subprocess
import sys

cmd = [
    "pyinstaller",
    "--onefile",                     # vše v jednom .exe
    "--windowed",                    # žádné konzolové okno
    "--name", "KickBot",
    "--icon", "icon.ico",            # ikona (pokud existuje)
    # Skryté importy které PyInstaller nedetekuje automaticky
    "--hidden-import", "customtkinter",
    "--hidden-import", "curl_cffi",
    "--hidden-import", "websocket",
    "--hidden-import", "requests",
    "--collect-all", "customtkinter",
    "kick_bot_gui.py",
]

# Pokud icon.ico neexistuje, odeber parametry s ikonou
import os
if not os.path.exists("icon.ico"):
    cmd = [c for c in cmd if "icon" not in c.lower() and "ico" not in c.lower()]

print("Spouštím PyInstaller ...")
print(" ".join(cmd))
result = subprocess.run(cmd)
if result.returncode == 0:
    print("\n✅ Hotovo! Soubor KickBot.exe najdeš ve složce dist/")
else:
    print("\n❌ Build selhal. Zkontroluj výpis výše.")
