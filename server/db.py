import os
import sqlite3
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash


def get_db_path(base_dir: str) -> str:
    """Vrátí cestu k SQLite databázi projektu."""
    db_dir = os.path.join(base_dir, "db")
    os.makedirs(db_dir, exist_ok=True)

    db_path = os.path.join(db_dir, "data.db")
    return db_path


def connect(db_path: str):
    """Otevře spojení s databází a zapne foreign keys."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn


def init_db_from_sql(db_path: str, sql_files):
    """Inicializuje databázi ze seznamu SQL souborů."""
    conn = connect(db_path)
    cur = conn.cursor()

    for file_path in sql_files:
        with open(file_path, "r", encoding="utf-8") as f:
            cur.executescript(f.read())

    conn.commit()
    conn.close()


def create_user(db_path, username, password):
    """Vytvoří nového uživatele a vrátí jeho ID."""
    conn = connect(db_path)
    cur = conn.cursor()

    password_hash = generate_password_hash(password)
    cur.execute(
        "INSERT INTO users(username, password_hash) VALUES(?, ?)",
        (username, password_hash),
    )

    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    return user_id


def get_user_by_username(db_path, username):
    """Vrátí uživatele podle username."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    return row


def get_user_by_id(db_path, user_id):
    """Vrátí uživatele podle ID."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()

    return row


def verify_user_password(user_row, password):
    """Ověří heslo uživatele."""
    return check_password_hash(user_row["password_hash"], password)


def create_home(db_path, name, home_password, created_by_user_id):
    """Vytvoří domácnost a přidá tvůrce jako admina."""
    conn = connect(db_path)
    cur = conn.cursor()

    password_hash = generate_password_hash(home_password)

    cur.execute(
        "INSERT INTO homes(name, home_password_hash, created_by_user_id) VALUES(?, ?, ?)",
        (name, password_hash, created_by_user_id),
    )
    home_id = cur.lastrowid

    cur.execute(
        "INSERT INTO memberships(user_id, home_id, role) VALUES(?, ?, ?)",
        (created_by_user_id, home_id, "admin"),
    )

    conn.commit()
    conn.close()

    return home_id


def delete_home(db_path, home_id):
    """Smaže domácnost z databáze."""
    conn = connect(db_path)
    conn.execute(
        "DELETE FROM homes WHERE id = ?",
        (home_id,),
    )
    conn.commit()
    conn.close()


def get_home_by_id(db_path, home_id):
    """Vrátí domácnost podle ID."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM homes WHERE id = ?",
        (home_id,),
    ).fetchone()
    conn.close()

    return row


def list_user_homes(db_path, user_id):
    """Vrátí seznam domácností, ve kterých je uživatel."""
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT h.*, m.role FROM homes h "
        "JOIN memberships m ON m.home_id = h.id "
        "WHERE m.user_id = ? "
        "ORDER BY h.id DESC",
        (user_id,),
    ).fetchall()
    conn.close()

    return rows


def verify_home_password(home_row, home_password):
    """Ověří heslo domácnosti."""
    return check_password_hash(home_row["home_password_hash"], home_password)


def get_membership_role(db_path, user_id, home_id) -> Optional[str]:
    """Vrátí roli uživatele v domácnosti."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT role FROM memberships WHERE user_id = ? AND home_id = ?",
        (user_id, home_id),
    ).fetchone()
    conn.close()

    if row:
        return row["role"]

    return None


def is_member(db_path, user_id, home_id):
    """Zjistí, jestli je uživatel člen domácnosti."""
    role = get_membership_role(db_path, user_id, home_id)
    return role is not None


def add_member(db_path, user_id, home_id, role="member"):
    """Přidá člena do domácnosti."""
    conn = connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO memberships(user_id, home_id, role) VALUES(?, ?, ?)",
        (user_id, home_id, role),
    )
    conn.commit()
    conn.close()


def set_member_role(db_path, user_id, home_id, role):
    """Změní roli člena v domácnosti."""
    conn = connect(db_path)
    conn.execute(
        "UPDATE memberships SET role = ? WHERE user_id = ? AND home_id = ?",
        (role, user_id, home_id),
    )
    conn.commit()
    conn.close()


def remove_member(db_path, user_id, home_id):
    """Odebere člena z domácnosti."""
    conn = connect(db_path)
    conn.execute(
        "DELETE FROM memberships WHERE user_id = ? AND home_id = ?",
        (user_id, home_id),
    )
    conn.commit()
    conn.close()


def list_members(db_path, home_id):
    """Vrátí seznam členů domácnosti."""
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT u.id as user_id, u.username, m.role, m.joined_at "
        "FROM memberships m "
        "JOIN users u ON u.id = m.user_id "
        "WHERE m.home_id = ? "
        "ORDER BY CASE m.role WHEN 'admin' THEN 0 WHEN 'elder' THEN 1 ELSE 2 END, u.username",
        (home_id,),
    ).fetchall()
    conn.close()

    return rows


def count_admins(db_path, home_id):
    """Vrátí počet adminů v domácnosti."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM memberships WHERE home_id = ? AND role = 'admin'",
        (home_id,),
    ).fetchone()
    conn.close()

    if row:
        return int(row["c"])

    return 0


def count_members(db_path, home_id):
    """Vrátí počet členů v domácnosti."""
    conn = connect(db_path)
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM memberships WHERE home_id = ?",
        (home_id,),
    ).fetchone()
    conn.close()

    if row:
        return int(row["c"])

    return 0


def upsert_device(db_path, device_id, board, ip, room, home_id, last_seen):
    """Vloží nové zařízení nebo aktualizuje existující zařízení."""
    conn = connect(db_path)
    existing = conn.execute(
        "SELECT id FROM esp_devices WHERE device_id = ?",
        (device_id,),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE esp_devices SET board = ?, ip = ?, room = ?, home_id = ?, last_seen = ? WHERE device_id = ?",
            (board, ip, room, home_id, last_seen, device_id),
        )
    else:
        conn.execute(
            "INSERT INTO esp_devices(device_id, board, ip, room, home_id, last_seen) VALUES(?, ?, ?, ?, ?, ?)",
            (device_id, board, ip, room, home_id, last_seen),
        )

    conn.commit()
    conn.close()


def clear_devices_for_home(db_path, home_id):
    """Smaže všechna zařízení dané domácnosti."""
    conn = connect(db_path)
    conn.execute(
        "DELETE FROM esp_devices WHERE home_id = ?",
        (home_id,),
    )
    conn.commit()
    conn.close()


def list_devices_for_home(db_path, home_id):
    """Vrátí seznam zařízení patřících do domácnosti."""
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT * FROM esp_devices WHERE home_id = ? ORDER BY device_id",
        (home_id,),
    ).fetchall()
    conn.close()

    return rows


def insert_measurement(db_path, home_id, device_id, pin, signal, peripheral_id, value, ts):
    """Vloží jedno naměřené měření do historie."""
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO measurements(home_id, device_id, pin, signal, peripheral_id, value, ts) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (home_id, device_id, pin, signal, peripheral_id, int(value), int(ts)),
    )
    conn.commit()
    conn.close()


def get_measurements(db_path, home_id, device_id, pin, ts_from, ts_to, limit=5000):
    """Vrátí surová měření v čase pro daný pin."""
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT ts, value FROM measurements "
        "WHERE home_id = ? AND device_id = ? AND pin = ? AND ts BETWEEN ? AND ? "
        "ORDER BY ts ASC LIMIT ?",
        (home_id, device_id, pin, int(ts_from), int(ts_to), int(limit)),
    ).fetchall()
    conn.close()

    return rows
