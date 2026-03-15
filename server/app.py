import os
import json
import time
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify

import db as dbmod
from sensor_conversions import convert_sensor_value


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = dbmod.get_db_path(BASE_DIR)
REGISTRY_PATH = os.path.join(BASE_DIR, "devices_registry.json")
PERIPHERALS_PATH = os.path.join(BASE_DIR, "peripherals.json")
OFFLINE_SECONDS = 30


app = Flask(__name__)
app.secret_key = "dev-secret-change-me"


def _atomic_write(path: str, data: dict) -> None:
    """Bezpečně zapíše JSON data do souboru."""
    temp_path = path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_path, path)


def _load_json(path: str, default: dict) -> dict:
    """Načte JSON soubor. Když neexistuje, vytvoří se výchozí."""
    if not os.path.exists(path):
        _atomic_write(path, default)
        return default

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def _load_registry():
    """Načte registry zařízení z JSON souboru."""
    registry = _load_json(REGISTRY_PATH, {"devices": {}})
    return registry


def _save_registry(reg):
    """Uloží registry zařízení do JSON souboru."""
    _atomic_write(REGISTRY_PATH, reg)


def _load_peripherals():
    """Načte definice periferií z JSON souboru."""
    peripherals = _load_json(PERIPHERALS_PATH, {})
    return peripherals


def now_ts():
    """Vrátí aktuální Unix timestamp v sekundách."""
    current_time = int(time.time())
    return current_time


def device_is_online(d):
    """Zjistí, jestli je zařízení považováno za online."""
    last_seen = int(d.get("last_seen", 0))
    diff = now_ts() - last_seen

    if diff <= OFFLINE_SECONDS:
        return True

    return False


def init_db():
    """Inicializuje databázi z SQL souborů."""
    db_dir = os.path.join(BASE_DIR, "db")
    sql_files = [
        os.path.join(db_dir, "tabusers_creator.sql"),
        os.path.join(db_dir, "tabhome_creator.sql"),
        os.path.join(db_dir, "connecting_tabs_creator.sql"),
    ]
    dbmod.init_db_from_sql(DB_PATH, sql_files)


@app.before_request
def _ensure():
    """Zajistí inicializaci databáze před každým requestem."""
    init_db()


def login_required(fn):
    """Decorator, který pustí jen přihlášeného uživatele."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_user"))

        return fn(*args, **kwargs)

    return wrapper


def home_required(fn):
    """Decorator, který pustí jen uživatele s vybranou domácností."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("home_id"):
            return redirect(url_for("login_home"))

        return fn(*args, **kwargs)

    return wrapper


def role_required(allowed_roles):
    """Decorator, který kontroluje roli uživatele v domácnosti."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            role = dbmod.get_membership_role(
                DB_PATH,
                session.get("user_id", 0),
                session.get("home_id", 0),
            )

            if role not in allowed_roles:
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def remove_home_devices_from_registry(home_id):
    """Smaže všechna zařízení domácnosti z JSON registry."""
    reg = _load_registry()
    ids_to_delete = []

    for device_id, device in reg.get("devices", {}).items():
        if device.get("home_id") == home_id:
            ids_to_delete.append(device_id)

    for device_id in ids_to_delete:
        reg["devices"].pop(device_id, None)

    _save_registry(reg)


def get_device_view_for_home(home_id):
    """Připraví data zařízení pro stránku Devices."""
    reg = _load_registry()
    db_rows = dbmod.list_devices_for_home(DB_PATH, home_id)
    output = []

    for row in db_rows:
        device_id = row["device_id"]
        json_row = reg.get("devices", {}).get(device_id, {})

        output.append({
            "id": device_id,
            "room": row["room"] or json_row.get("room", ""),
            "ip": row["ip"] or json_row.get("ip", ""),
            "board": row["board"] or json_row.get("board", ""),
            "online": device_is_online(json_row or {"last_seen": row["last_seen"] or 0}),
            "pins": json_row.get("pins", {}),
        })

    return output


def aggregate_series(series, bucket_seconds):
    """Agreguje časovou řadu do větších intervalů a vrátí průměry."""
    if not series:
        return []

    buckets = {}

    for item in series:
        ts = int(item["ts"])
        value = float(item["value"])
        bucket_ts = (ts // bucket_seconds) * bucket_seconds

        if bucket_ts not in buckets:
            buckets[bucket_ts] = {
                "sum": 0.0,
                "count": 0,
            }

        buckets[bucket_ts]["sum"] += value
        buckets[bucket_ts]["count"] += 1

    output = []
    for bucket_ts in sorted(buckets.keys()):
        avg = buckets[bucket_ts]["sum"] / buckets[bucket_ts]["count"]
        output.append({
            "ts": bucket_ts,
            "value": round(avg, 2),
        })

    return output


@app.get("/")
def index():
    """Úvodní stránka aplikace."""
    user = None
    homes = []

    if session.get("user_id"):
        user = dbmod.get_user_by_id(DB_PATH, session["user_id"])
        homes = dbmod.list_user_homes(DB_PATH, session["user_id"])

    return render_template(
        "index.html",
        user=user,
        homes=homes,
        home_id=session.get("home_id"),
    )


@app.get("/register_user")
def register_user():
    """Stránka registrace uživatele."""
    return render_template("register_user.html")


@app.post("/register_user")
def register_user_post():
    """Zpracuje registraci uživatele."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if len(username) < 3 or len(password) < 4:
        return render_template(
            "register_user.html",
            error="Username min 3, heslo min 4.",
        )

    if dbmod.get_user_by_username(DB_PATH, username):
        return render_template(
            "register_user.html",
            error="Uživatel už existuje.",
        )

    session["user_id"] = dbmod.create_user(DB_PATH, username, password)
    session.pop("home_id", None)

    return redirect(url_for("index"))


@app.get("/login_user")
def login_user():
    """Stránka přihlášení uživatele."""
    return render_template("login_user.html")


@app.post("/login_user")
def login_user_post():
    """Zpracuje přihlášení uživatele."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = dbmod.get_user_by_username(DB_PATH, username)

    if not user or not dbmod.verify_user_password(user, password):
        return render_template(
            "login_user.html",
            error="Špatné jméno nebo heslo.",
        )

    session["user_id"] = user["id"]
    session.pop("home_id", None)

    return redirect(url_for("index"))


@app.get("/logout")
def logout():
    """Odhlásí uživatele."""
    session.clear()
    return redirect(url_for("index"))


@app.get("/register_home")
@login_required
def register_home():
    """Stránka pro vytvoření domácnosti."""
    return render_template("register_home.html")


@app.post("/register_home")
@login_required
def register_home_post():
    """Zpracuje vytvoření domácnosti."""
    name = (request.form.get("name") or "").strip()
    home_password = request.form.get("home_password") or ""

    if len(name) < 2 or len(home_password) < 4:
        return render_template(
            "register_home.html",
            error="Název min 2, heslo min 4.",
        )

    session["home_id"] = dbmod.create_home(
        DB_PATH,
        name,
        home_password,
        session["user_id"],
    )

    return redirect(url_for("devices"))


@app.get("/login_home")
@login_required
def login_home():
    """Stránka pro připojení do domácnosti."""
    homes = dbmod.list_user_homes(DB_PATH, session["user_id"])
    return render_template("login_home.html", homes=homes)


@app.post("/login_home")
@login_required
def login_home_post():
    """Zpracuje připojení uživatele do domácnosti."""
    home_id_raw = (request.form.get("home_id") or "").strip()
    home_password = request.form.get("home_password") or ""

    if not home_id_raw.isdigit():
        return render_template(
            "login_home.html",
            homes=dbmod.list_user_homes(DB_PATH, session["user_id"]),
            error="Home ID musí být číslo.",
        )

    home_id = int(home_id_raw)
    home = dbmod.get_home_by_id(DB_PATH, home_id)

    if not home:
        return render_template(
            "login_home.html",
            homes=dbmod.list_user_homes(DB_PATH, session["user_id"]),
            error="Neznámá domácnost.",
        )

    if not dbmod.verify_home_password(home, home_password):
        return render_template(
            "login_home.html",
            homes=dbmod.list_user_homes(DB_PATH, session["user_id"]),
            error="Špatné heslo domácnosti.",
        )

    if not dbmod.is_member(DB_PATH, session["user_id"], home_id):
        dbmod.add_member(DB_PATH, session["user_id"], home_id, "member")

    session["home_id"] = home_id
    return redirect(url_for("devices"))


@app.get("/devices")
@login_required
@home_required
def devices():
    """Zobrazí seznam zařízení v domácnosti."""
    role = dbmod.get_membership_role(
        DB_PATH,
        session["user_id"],
        session["home_id"],
    )

    return render_template(
        "devices.html",
        devices=get_device_view_for_home(session["home_id"]),
        role=role,
        home_id=session["home_id"],
    )


@app.post("/devices/create_virtual")
@login_required
@home_required
@role_required({"admin", "elder"})
def devices_create_virtual():
    """Vytvoří nový virtual ESP skript do složky esp32_devices."""
    dev_dir = os.path.join(BASE_DIR, "esp32_devices")
    os.makedirs(dev_dir, exist_ok=True)

    max_index = -1
    for file_name in os.listdir(dev_dir):
        if file_name.startswith("virtual_esp") and file_name.endswith(".py"):
            number_text = file_name[len("virtual_esp"):-3]
            if number_text.isdigit():
                max_index = max(max_index, int(number_text))

    index = max_index + 1
    device_id = f"esp{index}"
    room = (request.form.get("room") or f"room{index}").strip()
    ip = (request.form.get("ip") or f"10.0.0.{10 + index}").strip()
    board = (request.form.get("board") or "esp32").strip()

    script = f'''import time
import random
import requests

SERVER = "http://127.0.0.1:5000"
DEVICE_ID = "{device_id}"
HOME_ID = {session["home_id"]}

IP = "{ip}"
ROOM = "{room}"
BOARD = "{board}"


def heartbeat():
    requests.post(
        f"{{SERVER}}/api/heartbeat",
        json={{
            "id": DEVICE_ID,
            "home_id": HOME_ID,
            "ip": IP,
            "room": ROOM,
            "board": BOARD
        }},
        timeout=2
    )


def push_values():
    values = {{
        "34": random.randint(0, 1023),
        "13": random.randint(0, 1),
        "35": random.randint(0, 1023),
        "12": random.randint(0, 1)
    }}

    requests.post(
        f"{{SERVER}}/api/push_values",
        json={{
            "id": DEVICE_ID,
            "values": values
        }},
        timeout=2
    )


def pull_desired_and_apply():
    response = requests.get(
        f"{{SERVER}}/api/pull_desired/{{DEVICE_ID}}",
        timeout=2
    ).json()

    if response.get("desired"):
        print("[{device_id}] desired outputs:", response["desired"])


if __name__ == "__main__":
    while True:
        try:
            heartbeat()
            push_values()
            pull_desired_and_apply()
        except Exception as e:
            print("[{device_id}] ERR:", e)

        time.sleep(5)
'''
    file_path = os.path.join(dev_dir, f"virtual_esp{index}.py")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(script)

    return redirect(url_for("devices"))


@app.get("/device/<dev_id>")
@login_required
@home_required
def device_config(dev_id):
    """Stránka konfigurace jednoho zařízení."""
    reg = _load_registry()
    dev = reg.get("devices", {}).get(dev_id)

    if not dev or dev.get("home_id") != session["home_id"]:
        abort(404)

    role = dbmod.get_membership_role(
        DB_PATH,
        session["user_id"],
        session["home_id"],
    )

    return render_template(
        "device_config.html",
        dev_id=dev_id,
        dev=dev,
        role=role,
        online=device_is_online(dev),
        peripherals=_load_peripherals(),
    )


@app.post("/device/<dev_id>/pins")
@login_required
@home_required
@role_required({"admin", "elder"})
def device_pins_update(dev_id):
    """Přidá nebo odebere pin na zařízení."""
    reg = _load_registry()
    dev = reg.get("devices", {}).get(dev_id)

    if not dev or dev.get("home_id") != session["home_id"]:
        abort(404)

    action = request.form.get("action")
    pin = (request.form.get("pin") or "").strip()

    if action == "add":
        if pin.isdigit():
            dev.setdefault("pins", {})[pin] = {
                "mode": request.form.get("mode") or "input",
                "signal": request.form.get("signal") or "digital",
                "peripheral_id": request.form.get("peripheral_id") or None,
                "value": 0,
                "desired": 0,
            }

    elif action == "remove":
        dev.get("pins", {}).pop(pin, None)

    _save_registry(reg)
    return redirect(url_for("device_config", dev_id=dev_id))


@app.post("/device/<dev_id>/pin/<pin>/set")
@login_required
@home_required
@role_required({"admin", "elder"})
def set_output_pin(dev_id, pin):
    """Nastaví výstupní hodnotu output pinu."""
    reg = _load_registry()
    dev = reg.get("devices", {}).get(dev_id)

    if not dev or dev.get("home_id") != session["home_id"]:
        abort(404)

    pin_data = dev.get("pins", {}).get(pin)

    if not pin_data or pin_data.get("mode") != "output":
        abort(400)

    try:
        value = int(request.form.get("value", "0"))
    except ValueError:
        value = 0

    if pin_data.get("signal") == "digital":
        value = 1 if value else 0
    else:
        value = max(0, min(4095, value))

    pin_data["desired"] = value
    _save_registry(reg)

    return redirect(url_for("device_config", dev_id=dev_id))


@app.get("/monitor")
@login_required
@home_required
def monitor():
    """Stránka monitoru zařízení a senzorů."""
    return render_template("monitor.html")


@app.get("/roles_manager")
@login_required
@home_required
@role_required({"admin"})
def roles_manager():
    """Správa rolí v domácnosti."""
    home_id = session["home_id"]

    return render_template(
        "roles_manager.html",
        members=dbmod.list_members(DB_PATH, home_id),
        home_id=home_id,
        admins=dbmod.count_admins(DB_PATH, home_id),
        members_count=dbmod.count_members(DB_PATH, home_id),
        me=session["user_id"],
    )


@app.post("/roles_manager/set_role")
@login_required
@home_required
@role_required({"admin"})
def roles_manager_set_role():
    """Změní roli člena domácnosti."""
    home_id = session["home_id"]
    target_uid = int(request.form.get("user_id", "0"))
    new_role = request.form.get("role", "member")

    current_role = dbmod.get_membership_role(DB_PATH, target_uid, home_id)
    admins = dbmod.count_admins(DB_PATH, home_id)

    if new_role not in ("admin", "elder", "member"):
        return redirect(url_for("roles_manager"))

    if not current_role:
        return redirect(url_for("roles_manager"))

    if current_role == "admin" and new_role in ("elder", "member") and admins <= 1:
        return redirect(url_for("roles_manager"))

    if target_uid == session["user_id"] and current_role == "admin":
        if new_role != "elder":
            return redirect(url_for("roles_manager"))

        if admins <= 1:
            return redirect(url_for("roles_manager"))

    dbmod.set_member_role(DB_PATH, target_uid, home_id, new_role)
    return redirect(url_for("roles_manager"))


@app.post("/roles_manager/kick")
@login_required
@home_required
@role_required({"admin"})
def roles_manager_kick():
    """Vyhodí člena z domácnosti."""
    home_id = session["home_id"]
    target_uid = int(request.form.get("user_id", "0"))

    if target_uid == session["user_id"]:
        return redirect(url_for("roles_manager"))

    role = dbmod.get_membership_role(DB_PATH, target_uid, home_id)
    if role == "admin" and dbmod.count_admins(DB_PATH, home_id) <= 1:
        return redirect(url_for("roles_manager"))

    dbmod.remove_member(DB_PATH, target_uid, home_id)
    return redirect(url_for("roles_manager"))


@app.post("/home/delete")
@login_required
@home_required
@role_required({"admin"})
def home_delete():
    """Smaže domácnost, ale jen pokud je admin v domácnosti sám."""
    home_id = session["home_id"]

    if dbmod.count_members(DB_PATH, home_id) != 1:
        return redirect(url_for("roles_manager"))

    if dbmod.count_admins(DB_PATH, home_id) != 1:
        return redirect(url_for("roles_manager"))

    remove_home_devices_from_registry(home_id)
    dbmod.clear_devices_for_home(DB_PATH, home_id)
    dbmod.delete_home(DB_PATH, home_id)
    session.pop("home_id", None)

    return redirect(url_for("index"))


@app.get("/hardware")
def hardware():
    """Stránka s přehledem použitého hardware."""
    boards = [
        {
            "name": "ESP32 DevKit V1",
            "image": url_for("static", filename="hw/esp32.svg"),
            "cpu": "Xtensa dual-core až 240 MHz",
            "wifi": "Ano",
            "bt": "Bluetooth Classic + BLE",
            "gpio": "Až kolem 30 použitelných GPIO",
            "adc": "12-bit ADC",
            "note": "Univerzální a často používaná vývojová deska.",
        },
        {
            "name": "ESP32-C3",
            "image": url_for("static", filename="hw/esp32_c3.svg"),
            "cpu": "RISC-V single-core až 160 MHz",
            "wifi": "Ano",
            "bt": "BLE 5",
            "gpio": "Méně pinů než klasické ESP32",
            "adc": "12-bit ADC",
            "note": "Úspornější varianta vhodná pro jednodušší zařízení.",
        },
        {
            "name": "ESP32-S3",
            "image": url_for("static", filename="hw/esp32_s3.svg"),
            "cpu": "Xtensa dual-core až 240 MHz",
            "wifi": "Ano",
            "bt": "BLE 5",
            "gpio": "Hodně GPIO podle konkrétní desky",
            "adc": "12-bit ADC",
            "note": "Silnější varianta vhodná i pro složitější projekty.",
        },
    ]

    return render_template("hardware.html", boards=boards)


@app.get("/flowchart")
def flowchart():
    """Stránka s vývojovým diagramem aplikace."""
    return render_template("flowchart.html")


@app.get("/api/monitor_data")
@login_required
@home_required
def api_monitor_data():
    """Vrátí data pro monitor v JSON formátu."""
    reg = _load_registry()
    peripherals = _load_peripherals()
    icon_map = {}

    for signal_type in peripherals:
        for mode in peripherals[signal_type]:
            for item in peripherals[signal_type][mode]:
                icon_map[item["id"]] = item.get("icon", "")

    output = []

    for device_id, device in reg.get("devices", {}).items():
        if device.get("home_id") != session["home_id"]:
            continue

        pins = []

        for pin, pin_data in device.get("pins", {}).items():
            if pin_data.get("mode") != "input":
                continue

            peripheral_id = pin_data.get("peripheral_id")
            raw_value = pin_data.get("value", 0)
            display_value = raw_value
            unit = ""

            if pin_data.get("signal") == "analog":
                display_value, unit = convert_sensor_value(peripheral_id, raw_value)

            pins.append({
                "pin": pin,
                "signal": pin_data.get("signal"),
                "peripheral_id": peripheral_id,
                "raw_value": raw_value,
                "display_value": display_value,
                "unit": unit,
                "icon": icon_map.get(peripheral_id, ""),
            })

        output.append({
            "id": device_id,
            "room": device.get("room", ""),
            "ip": device.get("ip", ""),
            "board": device.get("board", ""),
            "online": device_is_online(device),
            "pins": pins,
        })

    return jsonify({
        "ok": True,
        "devices": output,
        "peripherals": peripherals,
    })


@app.get("/api/measurements")
@login_required
@home_required
def api_measurements():
    """Vrátí historická data pro graf. Delší horizonty vrací agregované průměry."""
    device_id = (request.args.get("device_id") or "").strip()
    pin = (request.args.get("pin") or "").strip()
    horizon = (request.args.get("horizon") or "10m").strip()

    if not device_id or not pin:
        return jsonify({"ok": False, "error": "missing params"}), 400

    now = now_ts()

    if horizon == "1m":
        ts_from = now - 60
        bucket_seconds = None
    elif horizon == "10m":
        ts_from = now - 600
        bucket_seconds = 15
    else:
        ts_from = now - 86400
        bucket_seconds = 600

    rows = dbmod.get_measurements(
        DB_PATH,
        session["home_id"],
        device_id,
        pin,
        ts_from,
        now,
        5000,
    )

    series = []
    for row in rows:
        series.append({
            "ts": int(row["ts"]),
            "value": int(row["value"]),
        })

    if bucket_seconds is not None:
        series = aggregate_series(series, bucket_seconds)

    return jsonify({
        "ok": True,
        "series": series,
    })


@app.post("/api/heartbeat")
def api_heartbeat():
    """Přijme heartbeat od zařízení a zaregistruje ho."""
    data = request.get_json(force=True, silent=True) or {}
    device_id = str(data.get("id", "")).strip()
    home_id = data.get("home_id")
    ip = str(data.get("ip", "")).strip()
    room = str(data.get("room", "")).strip()
    board = str(data.get("board", "")).strip()

    if not device_id or not isinstance(home_id, int):
        return jsonify({"ok": False, "error": "missing id/home_id"}), 400

    reg = _load_registry()
    device = reg.setdefault("devices", {}).get(device_id)

    if not device:
        reg["devices"][device_id] = {
            "id": device_id,
            "home_id": home_id,
            "ip": ip,
            "room": room,
            "board": board,
            "last_seen": now_ts(),
            "pins": {},
        }
    else:
        device["home_id"] = home_id
        device["ip"] = ip or device.get("ip", "")
        device["room"] = room or device.get("room", "")
        device["board"] = board or device.get("board", "")
        device["last_seen"] = now_ts()

    dbmod.upsert_device(DB_PATH, device_id, board, ip, room, home_id, now_ts())
    _save_registry(reg)

    return jsonify({"ok": True})


@app.post("/api/push_values")
def api_push_values():
    """Přijme hodnoty pinů ze zařízení a uloží je."""
    data = request.get_json(force=True, silent=True) or {}
    device_id = str(data.get("id", "")).strip()
    values = data.get("values", {})

    if not device_id or not isinstance(values, dict):
        return jsonify({"ok": False, "error": "bad payload"}), 400

    reg = _load_registry()
    device = reg.get("devices", {}).get(device_id)

    if not device:
        return jsonify({"ok": False, "error": "unknown device"}), 404

    device["last_seen"] = now_ts()

    for pin, raw_val in values.items():
        pin = str(pin)
        pin_data = device.get("pins", {}).get(pin)

        if not pin_data:
            continue

        if pin_data.get("mode") != "input":
            continue

        signal = pin_data.get("signal") or "digital"
        peripheral_id = pin_data.get("peripheral_id")

        if signal == "digital":
            value = 1 if int(raw_val) else 0
        else:
            try:
                value = int(raw_val)
            except ValueError:
                value = 0

            value = max(0, min(1023, value))

        pin_data["value"] = value

        try:
            dbmod.insert_measurement(
                DB_PATH,
                int(device.get("home_id")),
                device_id,
                pin,
                signal,
                peripheral_id,
                value,
                now_ts(),
            )
        except Exception:
            pass

    _save_registry(reg)
    return jsonify({"ok": True})


@app.get("/api/pull_desired/<dev_id>")
def api_pull_desired(dev_id):
    """Vrátí požadované output hodnoty pro zařízení."""
    reg = _load_registry()
    device = reg.get("devices", {}).get(dev_id)

    if not device:
        return jsonify({"ok": False, "error": "unknown device"}), 404

    device["last_seen"] = now_ts()
    _save_registry(reg)

    desired = {}
    for pin, pin_data in device.get("pins", {}).items():
        if pin_data.get("mode") == "output":
            desired[pin] = int(pin_data.get("desired", 0))

    return jsonify({
        "ok": True,
        "desired": desired,
    })


if __name__ == "__main__":
    init_db()
    _load_registry()
    _load_peripherals()
    os.makedirs(os.path.join(BASE_DIR, "esp32_devices"), exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=True)
