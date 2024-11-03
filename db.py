import datetime
import sqlite3
from typing import Optional, List, Tuple

import utils

DINKDONK_RESET_PRIVILEGE_MINIMUM = 50

conn = None


def init():
  global conn
  conn = sqlite3.connect('discord_bot.db')

def set_timezone_for_user_id(user_id: int, tz: Optional[str], timestamp: Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO users (id, tz, last_modified) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET tz = excluded.tz, last_modified = excluded.last_modified', (str(user_id), tz, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    cur.close()

def get_timezone_for_user_id(user_id: int) -> Optional[str]:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT tz FROM users WHERE id = ?', (str(user_id),))
    value: Optional[Tuple[str]] = res.fetchone()
    cur.close()
    return value[0] if value else None

def save_dinkdonk_for_user(user_id: int, server_id: int, from_user_id: Optional[int] = None, timestamp: Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO dinkdonk (server_id, user_id, count, lifetime_count, should_alert, last_modified) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(server_id, user_id) DO UPDATE SET count = dinkdonk.count + 1, lifetime_count = dinkdonk.lifetime_count + 1, last_modified = excluded.last_modified', (str(server_id), str(user_id), 1, 1, 0, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    if from_user_id:
      cur.execute('INSERT INTO cross_dinkdonks (server_id, to_user_id, from_user_id, count, last_modified) VALUES (?, ?, ?, ?, ?) ON CONFLICT(server_id, to_user_id, from_user_id) DO UPDATE SET count = cross_dinkdonks.count + 1, last_modified = excluded.last_modified', (str(server_id), str(user_id), str(from_user_id), 1, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    res = cur.execute('SELECT count FROM dinkdonk WHERE server_id = ? AND user_id = ?', (str(server_id), str(user_id)))
    value: Tuple[int] = res.fetchone()
    cur.close()
    return value[0]

def get_all_dinkdonks_for_user(user_id: int, server_id: int) -> Tuple[int, int]:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT count, lifetime_count FROM dinkdonk WHERE user_id = ? AND server_id = ?', (str(user_id), str(server_id)))
    value: Optional[Tuple[int, int]] = res.fetchone()
    cur.close()
    return value if value else (0, 0)

def get_cross_dinkdonks_at_user(user_id: int, server_id: int):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT from_user_id, count FROM cross_dinkdonks WHERE to_user_id = ? AND server_id = ?', (str(user_id), str(server_id)))
    values: List[Tuple[str, int]] = res.fetchall()
    cur.close()
    return values

def get_dinkdonks_for_server(server_id: int):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT user_id, count FROM dinkdonk WHERE server_id = ? AND count > 0', (str(server_id),))
    values: List[Tuple[str, int]] = res.fetchall()
    cur.close()
    return values

def toggle_dinkdonk_alerts(user_id: int, server_id: int, timestamp: Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO dinkdonk (server_id, user_id, count, lifetime_count, should_alert, last_modified) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(server_id, user_id) DO UPDATE SET should_alert = MAX(0, 1 - dinkdonk.should_alert)', (str(server_id), str(user_id), 0, 0, 1, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    cur.close()

def get_dinkdonk_should_alert(user_id: int, server_id: int):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT should_alert FROM dinkdonk WHERE server_id = ? AND user_id = ?', (str(server_id), str(user_id)))
    value: Tuple[int] = res.fetchone()
    cur.close()
    return bool(value[0]) if value else False

def check_if_has_reset_privilege(user_id: int, server_id: int, threshold: int = None) -> bool:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    user_id = str(user_id)
    cur = conn.cursor()
    res = cur.execute('SELECT user_id, count FROM dinkdonk WHERE server_id = ? AND count >= ?', (str(server_id), DINKDONK_RESET_PRIVILEGE_MINIMUM))
    values = res.fetchall()
    cur.close()
    if len(values) == 0:
      return False
    max_user_id, max_count = values[0]
    for curr_user_id, curr_count in values[1:]:
      if curr_count >= max_count:
        max_user_id, max_count = curr_user_id, curr_count
    return (threshold is not None and max_count >= threshold) or max_user_id == user_id

def clear_server_dinkdonks(server_id: int, timestamp: Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('UPDATE dinkdonk SET count = 0, last_modified = ? WHERE server_id = ?', (timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'), str(server_id)))
    cur.execute('UPDATE cross_dinkdonks SET count = 0, last_modified = ? WHERE server_id = ?', (timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'), str(server_id)))
    cur.close()

def get_dd_cache(server_id: int) -> Optional[datetime.datetime]:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT value FROM dinkdonk_cache WHERE server_id = ?', (str(server_id),))
    value: Optional[Tuple[int]] = res.fetchone()
    cur.close()
    if value and value[0]:
      return datetime.datetime.fromtimestamp(value[0])
    return None

def set_dd_cache(server_id: int, value: Optional[datetime.datetime]):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO dinkdonk_cache (server_id, value) VALUES (?, ?) ON CONFLICT(server_id) DO UPDATE SET value = excluded.value', (str(server_id), utils.datetime_to_timestamp(value) if value else None))
    cur.close()

def set_availability_for_user(server_id: int, user_id: int, on_date: datetime.date, is_available: bool, description: str, timestamp: Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO availability (server_id, user_id, on_date, is_available, description, last_modified) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(server_id, user_id, on_date) DO UPDATE SET is_available = excluded.is_available, description = excluded.description, last_modified = excluded.last_modified', (str(server_id), str(user_id), on_date.isoformat(), int(is_available), description, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    cur.close()

def get_availabilities_for_date(server_id: int, on_date: datetime.date):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT user_id, is_available, description FROM availability WHERE server_id = ? AND on_date = ?', (str(server_id), on_date))
    values: List[Tuple[str, int, str]] = res.fetchall()
    cur.close()
    return values
