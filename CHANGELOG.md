# KickTip — změny podle verzí

Verze se zvedá ručně v `kick_bot_gui.py` (`APP_VERSION`) s každou změnou. GitHub pak sestaví
`dist/KickTip_v<verze>.exe` a vytvoří Release `v<verze>` s exe ke stažení a s popisem níže.
Čas sestavení je v záhlaví okna („sestaveno …“).

## 1.4.0 — 30. 10. 2026
- Nový příkaz **`!b`**: kdo ho napíše do chatu, bot mu odpoví, kolik má MMB na webu
  („💰 @nick má na webu 550 MMB“). Když divák v tabulce MMB není, bot mu to napíše.
- Limit proti spamu pro jednoho diváka: nejdřív za 3 s a nejvýš 3× za minutu
  (`web_zpravy.body_pauza_s`, `web_zpravy.body_max_za_minutu`). Další pokusy bot jen zapíše do logu.
- Příkaz a texty jdou změnit v `bot_config.json` (`prikazy.body`, `zpravy.body`, `zpravy.body_nenalezen`).
  Do stávajícího `bot_config.json` se doplní samy.
- Data bere z webu `/api/body/` se stejným klíčem jako zprávy z webu (`web_zpravy.klic`).
- Čísla verzí (1.4.0 místo času sestavení), Release na GitHubu s exe a tímhle popisem.

## 1.3.0 — 25. 10. 2026
- Statistika streamu: tlačítko a příkaz `!statistika` (objednávky, hry, odehraný čas, kdo vydělal / projebal,
  největší gembler, celkový obrat MMB) z webu `/api/stats/`.

## 1.2.0 — 20. 10. 2026
- KickBot přejmenovaný na **KickTip**, záložky Tipovačka a Počet zpráv.
- **Počet zpráv** (KickCounter): počítá zprávy diváků od spuštění bota, zásobník zpráv proti spamu,
  ignoruje opakované zprávy, tlačítko Odeslat do chatu.
- Aplikace může běžet jen jednou.
- **Zprávy z webu**: bot píše do chatu objednávky z obchodu ministrmystery.cz (`/api/chat/`).

## 1.1.0 — 14. 10. 2026
- Chat přes Centrifugo (Kick změnil realtime server).
- Exe se sestavuje na GitHubu (Actions).

## 1.0.0 — 7. 5. 2026
- KickBot: tipovačka čísla (`!start`, `!stop`, `!cislo`), tlačítka start / stop / výsledky,
  testovací režim se simulací diváků, kontrola konfigurace.
