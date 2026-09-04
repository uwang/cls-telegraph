"""Bark configuration, HTTP requests and per-device retries."""
import hashlib
import logging
import random
import time
from urllib.parse import urlsplit

import requests

from .storage import pending_deliveries, record_push_result

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


def deliver_pending(db, endpoint, devices, stopped, retry_seconds=900):
    rows = pending_deliveries(db)
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
            record_push_result(db, row['notification_id'], row['device_id'],
                               started, elapsed, reason, retry_seconds)
            LOG.info('Bark notification=%s device=%s attempt=%s elapsed=%.2fs result=%s',
                     row['notification_id'], row['device_id'][:12], attempt + 1, elapsed, reason or 'success')
            if not reason:
                break
            if attempt < 3 and stopped.wait(random.uniform(*BACKOFF[attempt])):
                return
