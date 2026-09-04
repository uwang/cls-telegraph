"""Persistent archive history and per-device Bark outbox (no device secrets on disk)."""
import hashlib
import json
import logging
import random
import sqlite3
import time
from urllib.parse import urlsplit

import requests

LOG = logging.getLogger(__name__)
SESSION = requests.Session()
BACKOFF = ((2, 4), (6, 10), (15, 25))


def device_id(key):
    return hashlib.sha256(key.encode()).hexdigest()


def bark_config(environ):
    keys = list(dict.fromkeys(k.strip() for k in environ.get('BARK_DEVICE_KEYS', '').split(',') if k.strip()))
    base = environ.get('BARK_URL', 'https://api.day.app').strip().rstrip('/')
    parsed = urlsplit(base)
    if keys and (parsed.scheme not in ('http', 'https') or not parsed.netloc
                 or parsed.username or parsed.password or parsed.query or parsed.fragment
                 or parsed.path not in ('', '/')):
        raise ValueError('BARK_URL 必须是服务基础地址，不包含设备 key、路径或查询参数')
    return base + '/push', {device_id(k): k for k in keys}


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS archive_log (
            id INTEGER PRIMARY KEY, date TEXT NOT NULL, started_at REAL NOT NULL,
            finished_at REAL, status TEXT NOT NULL, path TEXT, bytes INTEGER,
            item_count INTEGER, error TEXT);
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL,
            status TEXT NOT NULL, UNIQUE(date, kind));
        CREATE TABLE IF NOT EXISTS deliveries (
            notification_id INTEGER NOT NULL, device_id TEXT NOT NULL,
            status TEXT NOT NULL, next_attempt REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(notification_id, device_id));
        CREATE TABLE IF NOT EXISTS push_log (
            id INTEGER PRIMARY KEY, notification_id INTEGER NOT NULL,
            device_id TEXT NOT NULL, attempted_at REAL NOT NULL,
            elapsed REAL NOT NULL, status TEXT NOT NULL, error TEXT);
    ''')
    return db


def notify(db, day, kind, body, devices):
    cursor = db.execute('INSERT OR IGNORE INTO notifications(date,kind,title,body,created_at,status) VALUES(?,?,?,?,?,?)',
                        (str(day), kind, '财联社电报归档' + ('成功' if kind == 'success' else '失败'),
                         body, time.time(), 'pending' if devices else 'disabled'))
    if cursor.rowcount:
        db.executemany('INSERT INTO deliveries(notification_id,device_id,status) VALUES(?,?,?)',
                       [(cursor.lastrowid, device, 'pending') for device in devices])


def start_archive(db, day):
    with db:
        return db.execute('INSERT INTO archive_log(date,started_at,status) VALUES(?,?,?)',
                          (str(day), time.time(), 'running')).lastrowid


def finish_archive(db, attempt, day, devices, path=None, error=None):
    count = None
    size = None
    if path is not None:
        size = path.stat().st_size
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.startswith('> 共 ') and line.rstrip().endswith(' 条'):
                    count = int(line.split()[2])
                    break
    with db:
        db.execute('UPDATE archive_log SET finished_at=?,status=?,path=?,bytes=?,item_count=?,error=? WHERE id=?',
                   (time.time(), 'failed' if error else 'success', str(path) if path else None,
                    size, count, error, attempt))
        if not error:
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('last_success', str(day)))
            # A recovered archive makes undelivered failure alerts obsolete.
            db.execute("UPDATE deliveries SET status='superseded' WHERE status='pending' AND notification_id IN "
                       "(SELECT id FROM notifications WHERE date=? AND kind='failure')", (str(day),))
            db.execute("UPDATE notifications SET status='superseded' WHERE date=? AND kind='failure' AND status='pending'", (str(day),))
        body = (f'{day} 归档失败：{error}；将自动重试。' if error else
                f'{day} 已归档，{count if count is not None else "未知"} 条，{size} 字节。\n{path}')
        notify(db, day, 'failure' if error else 'success', body, devices)


def deliver_pending(db, endpoint, devices, stopped, retry_seconds=900):
    rows = db.execute("SELECT d.*,n.title,n.body FROM deliveries d JOIN notifications n ON n.id=d.notification_id "
                      "WHERE d.status='pending' AND d.next_attempt<=? ORDER BY n.id", (time.time(),)).fetchall()
    for row in rows:
        key = devices.get(row['device_id'])
        if stopped.is_set():
            return
        if key is None:
            continue  # Preserve pending state if configuration temporarily drops a device.
        for attempt in range(4):
            started = time.time()
            reason = None
            try:
                response = SESSION.post(endpoint, json={'device_key': key, 'title': row['title'],
                                        'body': row['body'], 'group': 'cls.archive'}, timeout=(5, 15))
                if response.status_code != 200:
                    reason = f'HTTP {response.status_code}'
                else:
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get('code') != 200:
                        reason = 'Bark 业务状态非 200'
            except (requests.RequestException, ValueError) as exc:
                # Never persist exception text: URLs, response bodies and proxy credentials may contain secrets.
                reason = type(exc).__name__
            elapsed = time.time() - started
            with db:
                db.execute('INSERT INTO push_log(notification_id,device_id,attempted_at,elapsed,status,error) VALUES(?,?,?,?,?,?)',
                           (row['notification_id'], row['device_id'], started, elapsed,
                            'failed' if reason else 'success', reason))
                db.execute('UPDATE deliveries SET status=?,next_attempt=? WHERE notification_id=? AND device_id=?',
                           ('pending' if reason else 'success', time.time() + retry_seconds,
                            row['notification_id'], row['device_id']))
                if not reason:
                    db.execute("UPDATE notifications SET status='success' WHERE id=? AND NOT EXISTS "
                               "(SELECT 1 FROM deliveries WHERE notification_id=? AND status!='success')",
                               (row['notification_id'], row['notification_id']))
            LOG.info('Bark notification=%s device=%s attempt=%s elapsed=%.2fs result=%s',
                     row['notification_id'], row['device_id'][:12], attempt + 1, elapsed, reason or 'success')
            if not reason:
                break
            if attempt < 3 and stopped.wait(random.uniform(*BACKOFF[attempt])):
                return


def show_status(db):
    for table in ('archive_log', 'notifications', 'deliveries', 'push_log'):
        order = 'notification_id DESC' if table == 'deliveries' else 'id DESC'
        rows = db.execute(f'SELECT * FROM {table} ORDER BY {order} LIMIT 20').fetchall()
        print(json.dumps({table: [dict(r) for r in rows]}, ensure_ascii=False, indent=2))
