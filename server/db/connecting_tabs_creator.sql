CREATE TABLE IF NOT EXISTS memberships (
  user_id INTEGER NOT NULL,
  home_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','elder','member')),
  joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, home_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(home_id) REFERENCES homes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS esp_devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id TEXT NOT NULL UNIQUE,
  board TEXT,
  ip TEXT,
  room TEXT,
  home_id INTEGER,
  last_seen INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(home_id) REFERENCES homes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  home_id INTEGER NOT NULL,
  device_id TEXT NOT NULL,
  pin TEXT NOT NULL,
  signal TEXT NOT NULL CHECK(signal IN ('digital','analog')),
  peripheral_id TEXT,
  value INTEGER NOT NULL,
  ts INTEGER NOT NULL,
  FOREIGN KEY(home_id) REFERENCES homes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_measurements_lookup
ON measurements(home_id, device_id, pin, ts);
