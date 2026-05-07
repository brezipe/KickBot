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


