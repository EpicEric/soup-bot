import datetime
import sqlite3
import typing

DINKDONK_RESET_PRIVILEGE_MINIMUM = 50

conn = None


def init():
  global conn
  conn = sqlite3.connect('discord_bot.db')

def set_timezone_for_user_id(user_id: int, tz: typing.Optional[str], timestamp: typing.Optional[datetime.datetime] = None):
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

def get_timezone_for_user_id(user_id: int) -> typing.Optional[str]:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT tz FROM users WHERE id = ?', (str(user_id),))
    value = res.fetchone()
    cur.close()
    return value[0] if value else None

def save_dinkdonk_for_user(user_id: int, server_id: int, timestamp: typing.Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO dinkdonk (server_id, user_id, count, last_modified) VALUES (?, ?, ?, ?) ON CONFLICT(server_id, user_id) DO UPDATE SET count = dinkdonk.count + 1, last_modified = excluded.last_modified', (str(server_id), str(user_id), 1, timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')))
    res = cur.execute('SELECT count FROM dinkdonk WHERE server_id = ? AND user_id = ?', (str(server_id), str(user_id)))
    value = res.fetchone()
    cur.close()
    return value[0]

def get_dinkdonks_for_server(server_id: int):
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT user_id, count FROM dinkdonk WHERE server_id = ? AND count > 0', (str(server_id),))
    values = res.fetchall()
    cur.close()
    return values

def check_if_has_reset_privilege(user_id: int, server_id: int) -> bool:
  if not conn:
    raise ValueError('DB not initialized!')
  with conn:
    cur = conn.cursor()
    res = cur.execute('SELECT user_id, count FROM dinkdonk WHERE server_id = ? AND count >= ?', (str(server_id), DINKDONK_RESET_PRIVILEGE_MINIMUM))
    values = res.fetchall()
    cur.close()
    if len(values) == 0:
      return False
    max_user_id, max_count  = values[0]
    for curr_user_id, curr_count in values[1:]:
      if curr_count > max_count:
        if max_user_id == str(user_id):
          return False
        max_user_id, max_count = curr_user_id, curr_count
      elif curr_count == max_count and curr_user_id == str(user_id):
        max_user_id = curr_user_id
    return max_user_id == str(user_id)

def clear_server_dinkdonks(server_id: int, timestamp: typing.Optional[datetime.datetime] = None):
  if not conn:
    raise ValueError('DB not initialized!')
  if not timestamp:
    timestamp = datetime.datetime.utcnow()
  else:
    timestamp = datetime.datetime.utcfromtimestamp(timestamp.timestamp())
  with conn:
    cur = conn.cursor()
    cur.execute('UPDATE dinkdonk SET count = 0, last_modified = ? WHERE server_id = ?', (timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'), str(server_id)))
    cur.close()
