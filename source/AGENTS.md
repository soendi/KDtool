# KDtool - Projektkonventionen

## Build & Deployment

### EXE bauen
```powershell
py -3.14 -m PyInstaller --onefile --noconsole --icon=KDtool.ico --add-data "KDtool.ico;." --add-data "C:\Users\sonde\AppData\Local\Programs\Python\Python314\tcl\tcl8.6;_tcl_data" --add-data "C:\Users\sonde\AppData\Local\Programs\Python\Python314\tcl\tk8.6;_tk_data" --noconfirm KDtool.py
```

### Nach dem Build
- `KDtool.exe` aus `dist\` in Projektordner kopieren
- `version.txt` im Projektordner erstellen mit Inhalt = `splash_version` aus `source\KDtool.py`
- `KDtool.exe` kopieren nach:
  - `G:\Meine Ablage\Arbeit\Firmen\07 Keller Duerr\KDtool\KDtool.exe`
- `version.txt` kopieren nach:
  - `G:\Meine Ablage\Arbeit\Firmen\07 Keller Duerr\KDtool\version.txt`
- Vorhandene Dateien überschreiben
- Build-Artefakte (`__pycache__`, `build`, `dist`, `*.spec`) löschen

### Version
- `splash_version` in `source\KDtool.py` = einzige Versionsnummer

## Projektstruktur
- `source\KDtool.py` - Hauptquellcode
- `source\KDtool.ico` - App-Icon
- `KDtool.exe` - gebaute EXE (Projektordner-Version)
- `version.txt` - Versionsnummer für Update-Prüfung

## Wichtige Konventionen
- Tabs: Netzwerkeinstellungen, Netzwerkgeräte, Drucker, Windows, Internet, Fernwartung, Kasse, Daten übermitteln, Info
- Passwortgeschützte Tabs: Datenträgerbereinigung, Zusatzfunktionen (nur bei password_ok=True)
- Splash-Version = einzige Versionsnummer
- TODO: Standardwert `version_str="260524"` in `start_gui()` (Zeile ~1851) ebenfalls auf `260525` setzen
- Firmendaten aus PSQL-Dumps via pg_restore
- Alle Labels im Netzwerk-Tab width=22
- Email-Subject auto-generiert: "PC-Informationen / {firma}, {plz} {ort} / {pc}, {datum}"
