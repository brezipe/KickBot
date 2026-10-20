## Vytvořeno pro: [https://ministrmystery.cz](https://ministrmystery.cz)

# KickTip

Aplikace (dřív KickBot) má v záhlaví dvě záložky a může běžet jen v jedné instanci:

- **Tipovačka** je tipovačka čísla, funguje jako dřív. Tipy sbírá jen mezi
  *Spustit tipovačku* (nebo `!start`) a *Stop*.
- **Počet zpráv** (KickCounter) počítá zprávy každého diváka **od spuštění bota**. Tlačítko *Odeslat do chatu*
  pošle nejaktivnější diváky a *Vynulovat počítadlo* začne počítat znovu.
  Vlastní zprávy bota se nepočítají.

Nastavení počítadla je ve stejném `bot_config.json` (✏️ Upravit texty a příkazy):

- `counter.top_n`: kolik nejaktivnějších poslat do chatu (výchozí 3),
- `counter.delay_s` + `counter.burst`: každý divák má zásobník `burst` zpráv (výchozí 2),
  který se doplňuje o 1 zprávu za `delay_s` sekund (výchozí 5). Občas 2 zprávy rychle za sebou
  projdou, trvalý spam je omezen na 1 zprávu za 5 s. `burst` 1 znamená přísně 1 za 5 s,
  `delay_s` 0 znamená počítat každou zprávu.
- `counter.duplicity_s`: stejná zpráva zopakovaná do tolika sekund se nepočítá
  (výchozí 60, `0` = vypnuto),
- `zpravy.counter_top` (`{seznam}` = `🥇 user [počet] | 🥈 …`) a `zpravy.counter_prazdno`.

## Zprávy z webu (mm.nereknu.cz)

Když běží bot, každých `web_zpravy.interval_s` sekund (výchozí 10) se zeptá webu na čekající
zprávy (třeba nová objednávka v obchodě), napíše je do chatu a webu potvrdí, že jsou odeslané:

- `GET  {api_url}pending/` → `{"messages": [{"id", "text", "created"}]}`
- `POST {api_url}<id>/sent/` → `{"ok": true}`
- hlavička `Authorization: Bearer <klic>`

V `bot_config.json` stačí vyplnit `web_zpravy.klic`. Výchozí `api_url` je `https://mm.nereknu.cz/api/chat/`.
Když chat nejde, zpráva se zkusí v dalším kole. Když selže jen potvrzení, zpráva se do chatu
znovu nenapíše.

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
Stažení: záložka **Actions** → poslední běh **Build exe** → **Artifacts** → `KickTip-exe`.
