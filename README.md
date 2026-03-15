
# Smart Home – Secondary school project

Projekt chytré domácnosti postavený na Flasku, SQLite a virtuálních ESP32 zařízeních.

## Co projekt umí
- registrace a přihlášení uživatele
- vytváření domácností
- připojení uživatelů do domácností
- role `admin`, `elder`, `member`
- správa zařízení a pinů
- kombinace periferií podle typu pinu přes `peripherals.json`
- přehled zařízení v jedné stránce **Devices**
- monitor analogových i digitálních vstupů
- grafy s více horizonty: `1 min`, `10 min`, `1 den`
- agregaci delších horizontů pomocí průměrů
- přepočty analogových hodnot na reálnější jednotky
- lokální `chart.js` ve složce `static`, takže graf funguje i bez internetu
- stránku s hardware přehledem
- vývojový diagram jako obrázek

## Struktura projektu
```text
smart_home/
  server/
    app.py
    db.py
    sensor_conversions.py
    devices_registry.json
    peripherals.json
    db/
      data.db
      tabusers_creator.sql
      tabhome_creator.sql
      connecting_tabs_creator.sql
      erm_diagram.jpg
    esp32_devices/
      virtual_esp0.py
      virtual_esp1.py
    templates/
      layout.html
      index.html
      register_user.html
      login_user.html
      register_home.html
      login_home.html
      devices.html
      device_config.html
      monitor.html
      roles_manager.html
      hardware.html
      flowchart.html
    static/
      styles.css
      app.js
      chart.js
      flowchart.png
      hw/
        esp32.svg
        esp32_c3.svg
        esp32_s3.svg
```

## Instalace
1. Otevři terminál.
2. Přesuň se do složky `server`.
3. Vytvoř virtuální prostředí:
```bash
python -m venv venv
```

4. Aktivuj virtuální prostředí:
- Windows:
```bash
venv\Scripts\activate
```
- Linux:
```bash
source venv/bin/activate
```

5. Nainstaluj balíčky:
```bash
pip install -r requirements.txt
```

## Spuštění serveru
Ve složce `server` spusť:
```bash
python app.py
```

Pak otevři prohlížeč:http://127.0.0.1:5000




## Jak s aplikací pracovat
### 1. Registrace a přihlášení
- klikni na **Register**
- vytvoř si uživatelský účet
- potom se přihlas přes **Login**

### 2. Vytvoření domácnosti
- klikni na **Create home**
- zadej název a heslo domácnosti
- po vytvoření se automaticky staneš `admin`

### 3. Připojení do domácnosti
- klikni na **Join/select home**
- zadej `Home ID` a heslo domácnosti
- pokud v domácnosti ještě nejsi, přidáš se jako `member`

### 4. Zařízení
Na stránce **Devices**:
- uvidíš všechna zařízení domácnosti
- můžeš otevřít konfiguraci zařízení
- jako `admin` nebo `elder` můžeš vytvořit nový soubor `virtual_espX.py`
- virtual zařízení se tváří stejně jako normální devices

### 5. Spuštění virtual ESP
Příklad:
```bash
python server/esp32_devices/virtual_esp0.py
```

Před spuštěním zkontroluj:
- `HOME_ID`
- `IP`
- `ROOM`
- `BOARD`

### 6. Přidání pinů
Na stránce **Device config**:
- přidej číslo pinu
- zvol `input` / `output`
- zvol `analog` / `digital`
- vyber periferii podle nabídky

### 7. Monitor
Na stránce **Monitor**:
- filtruj místnost
- filtruj zařízení
- filtruj typ signálu
- u analogových vstupů klikni na **Open**
- vyber horizont:
  - `1 min`
  - `10 min`
  - `1 den`

## Přepočty analogových hodnot
Přepočty jsou v souboru:
```text
server/sensor_conversions.py
```

Použité přepočty:
- `temperature` → °C přes beta model termistoru
- `light_level` → lux
- `humidity` → %
- `noise` → orientační dB

## Jak funguje graf
- `1 min` → zobrazí syrová data
- `10 min` → rozdělí data do menších intervalů a zobrazí průměry
- `1 den` → rozdělí data do větších intervalů a zobrazí průměry

Tím pádem graf není přeplněný.

## Role
### Member
- může jen číst data

### Elder
- může nastavovat zařízení a piny

### Admin
- může měnit role
- může vyhazovat členy
- může předat roli admina jinému uživateli
- když existuje jiný admin, může sám sebe snížit na `elder`
- když je v domácnosti sám, může smazat celou domácnost


