"""Persistent, single-worker Telegram delivery independent of request handling."""
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
CHAT = os.environ.get('TELEGRAM_CHAT_ID', '').strip()


def configured():
    return bool(re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', TOKEN) and re.fullmatch(r'-?[0-9]+', CHAT))


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
        created REAL NOT NULL, next_attempt REAL NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0, sent REAL, message_id TEXT
    )''')
    if configured():
        enqueue(db, 'setup', 'telegram-enabled-v1')


def enqueue(db, kind, entity_id):
    db.execute('INSERT OR IGNORE INTO notifications (id,kind,entity_id,created) VALUES (?,?,?,?)',
               (kind + ':' + entity_id, kind, entity_id, time.time()))


def cleanup(db):
    db.execute("DELETE FROM notifications WHERE kind='audit' AND entity_id NOT IN (SELECT id FROM audits)")
    db.execute("DELETE FROM notifications WHERE kind='lead' AND entity_id NOT IN (SELECT id FROM leads)")


def clip(value, limit):
    value = ''.join(c for c in str(value) if c in '\n\t' or (ord(c) >= 32 and c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'))
    return value if len(value) <= limit else value[:limit] + '…'


def message(db, row, origin):
    if row['kind'] == 'setup':
        return '🏔️ CyberAlps\n\nУведомления подключены. Сюда будут приходить новые запросы на анализ сайта и заявки из контактной формы.'
    table = 'audits' if row['kind'] == 'audit' else 'leads'
    record = db.execute('SELECT * FROM ' + table + ' WHERE id=?', (row['entity_id'],)).fetchone()
    if not record:
        return None
    stamp = datetime.fromtimestamp(record['created'], ZoneInfo('Europe/Zurich')).strftime('%d.%m.%Y %H:%M')
    if row['kind'] == 'audit':
        return f"🏔️ CyberAlps · Запрос на анализ\n\nСайт: {clip(record['url'], 600)}\nВремя: {stamp} (Швейцария)\nЗаявка: {record['id'][:8]}"
    return (f"🏔️ CyberAlps · Новая заявка\n\nИмя: {clip(record['name'], 100)}\n"
            f"Email: {clip(record['email'], 254)}\nСайт: {clip(record['url'], 600) or 'не указан'}\n"
            f"\nСообщение:\n{clip(record['message'], 1000)}\n\nВремя: {stamp} (Швейцария)\n"
            f"Заявка: {record['id'][:8]}\nПолный текст: {origin}/admin")


def send(text):
    request = urllib.request.Request('https://api.telegram.org/bot' + TOKEN + '/sendMessage',
        data=json.dumps({'chat_id': CHAT, 'text': text, 'link_preview_options': {'is_disabled': True}}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read(65536))
        except (ValueError, OSError):
            data = {}
        return None, min(86400, max(10, int(data.get('parameters', {}).get('retry_after', 60))))
    if not data.get('ok') or not isinstance(data.get('result', {}).get('message_id'), int):
        return None, 60
    return str(data['result']['message_id']), 0


def deliver_one(connect, origin):
    if not configured():
        return False
    with connect() as db:
        row = db.execute('SELECT * FROM notifications WHERE sent IS NULL AND next_attempt<=? ORDER BY created LIMIT 1', (time.time(),)).fetchone()
        if not row:
            return False
        text = message(db, row, origin)
        if text is None:
            db.execute('DELETE FROM notifications WHERE id=?', (row['id'],))
            return True
        db.execute('UPDATE notifications SET attempts=attempts+1, next_attempt=? WHERE id=?', (time.time()+60, row['id']))
    try:
        message_id, retry = send(text)
    except Exception:
        # Never log Telegram URLs, credentials or contact contents.
        message_id, retry = None, 60
    with connect() as db:
        if message_id is not None:
            db.execute('UPDATE notifications SET sent=?,message_id=? WHERE id=?', (time.time(), message_id, row['id']))
        else:
            delay = max(retry, min(3600, 10 * 2 ** min(row['attempts'], 9)))
            db.execute('UPDATE notifications SET next_attempt=? WHERE id=?', (time.time()+delay, row['id']))
    return True


def worker(connect, origin):
    while True:
        try:
            deliver_one(connect, origin)
        except sqlite3.Error:
            pass
        time.sleep(2)
