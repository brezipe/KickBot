## Vytvořeno pro: [https://ministrmystery.cz](https://ministrmystery.cz)

python3 -m venv venv

Win:

PS C:\xx\bot> . .\venv\Scripts\Activate.ps1

DEBUG mod v PS:

$py = (Get-Command python).Source; Start-Process powershell -ArgumentList "-NoExit","-Command","& '$py' '$PWD\kick_bot_test.py'"; python .\kick_bot_gui.py


Linux:

$ source ./venv/bin/activate



pip install -f requirements.txt

python build_exe.py


dist/ Tady je exe




## Chat přes Centrifugo (od 10/2026)

Kick přestal používat Pusher (starý klíč `32cbd69e4b950bf97679` hlásí „not in this cluster“).
Bot teď čte chat přes Centrifugo:

1. token hosta: `POST https://web.kick.com/api/v1/realtime/auth/connection` s `{"client_id": "<uuid>"}`,
2. websocket `wss://realtime.us-west-2.platform.kick.com/connection/websocket` (záloha us-east-1)
   s hlavičkou `Origin: https://kick.com` (jiný Origin → 403),
3. `{"connect": {"token": …, "name": "js"}}`, pak `{"subscribe": {"channel": "chatrooms.<chatroom_id>.v2"}}`,
4. ping serveru `{}` každých 25 s → odpověď `{}`, token platí ~45 min a minutu předem se obnoví (`refresh`).

Zprávy mají stejný tvar jako dřív (`App\\Events\\ChatMessageEvent`). Posílání do chatu jde dál přes oficiální API.

## Sestavení exe přes GitHub

Při pushi do repozitáře GitHub Actions sestaví exe na Windows (`.github/workflows/build-exe.yml`).
Stažení: záložka **Actions** → poslední běh **Build exe** → **Artifacts** → `KickBot-exe`.
