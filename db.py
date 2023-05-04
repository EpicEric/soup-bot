import datetime
import sqlite3
import typing

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
    res = cur.execute('SELECT user_id, count FROM dinkdonk WHERE server_id = ?', (str(server_id),))
    values = res.fetchall()
    cur.close()
    return values
