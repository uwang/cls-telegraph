"""SQLite archive history and persistent notification outbox."""
import json
import sqlite3
import time


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


def notify(db, day, kind, title, body, devices):
    cursor = db.execute('INSERT OR IGNORE INTO notifications(date,kind,title,body,created_at,status) VALUES(?,?,?,?,?,?)',
                        (str(day), kind, title, body, time.time(), 'pending' if devices else 'disabled'))
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
        if error:
            title, body = '财联社电报归档失败', f'{day} 归档失败：{error}；将自动重试。'
        else:
            title, body = f'财联社{day}', f'已归档电报 {count if count is not None else "未知"} 条'
        notify(db, day, 'failure' if error else 'success', title, body, devices)


def show_status(db):
    for table in ('archive_log', 'notifications', 'deliveries', 'push_log'):
        order = 'notification_id DESC' if table == 'deliveries' else 'id DESC'
        rows = db.execute(f'SELECT * FROM {table} ORDER BY {order} LIMIT 20').fetchall()
        print(json.dumps({table: [dict(r) for r in rows]}, ensure_ascii=False, indent=2))


def pending_deliveries(db):
    return db.execute("SELECT d.*,n.title,n.body FROM deliveries d JOIN notifications n ON n.id=d.notification_id "
                      "WHERE d.status='pending' AND d.next_attempt<=? ORDER BY n.id", (time.time(),)).fetchall()


def record_push_result(db, notification_id, device, started, elapsed, reason, retry_seconds):
    with db:
        db.execute('INSERT INTO push_log(notification_id,device_id,attempted_at,elapsed,status,error) VALUES(?,?,?,?,?,?)',
                   (notification_id, device, started, elapsed,
                    'failed' if reason else 'success', reason))
        db.execute('UPDATE deliveries SET status=?,next_attempt=? WHERE notification_id=? AND device_id=?',
                   ('pending' if reason else 'success', time.time() + retry_seconds,
                    notification_id, device))
        if not reason:
            db.execute("UPDATE notifications SET status='success' WHERE id=? AND NOT EXISTS "
                       "(SELECT 1 FROM deliveries WHERE notification_id=? AND status!='success')",
                       (notification_id, notification_id))
