import datetime
import subprocess
import shutil
import re
import os
import sys

# 1. Vygenerování verze podle aktuálního času (např. 26.04.30.1420)
new_version = datetime.datetime.now().strftime("%y%m%d.%H%M")
print(f"--- Generuji verzi: {new_version} ---")

# 2. Aktualizace BUILD_VERSION v kick_bot_gui.py
main_script = "kick_bot_gui.py"

if os.path.exists(main_script):
    with open(main_script, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'BUILD_VERSION\s*=\s*".*?"', f'BUILD_VERSION = "{new_version}"', content)

    with open(main_script, "w", encoding="utf-8") as f:
        f.write(content)
    print("--- Verze v kick_bot_gui.py aktualizována ---")
else:
    print("CHYBA: kick_bot_gui.py nenalezen!")
    exit()

# 3. Spuštění PyInstaller
print("--- Spouštím PyInstaller... ---")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",
    "--noconsole",
    "-y",
    "--name", "KickBot",
    "--collect-all", "customtkinter",
    "--collect-all", "darkdetect",
    "--collect-all", "tkinter",
    "--hidden-import", "curl_cffi",
    "--hidden-import", "websocket",
    "--hidden-import", "requests",
]

if os.path.exists("icon.ico"):
    cmd += ["--icon", "icon.ico", "--add-data", "icon.ico;."]

cmd.append(main_script)

try:
    subprocess.run(cmd, check=True)
    print("--- PyInstaller dokončen, zipuji výstup... ---")
    zip_out = os.path.join("dist", "KickBot")
    shutil.make_archive(zip_out, "zip", os.path.join("dist", "KickBot"))
    print(f"\n--- HOTOVO! dist/KickBot.zip (verze {new_version}) ---")
except subprocess.CalledProcessError:
    print("\n--- CHYBA: PyInstaller selhal! ---")
