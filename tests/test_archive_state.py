import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import cls_telegraph as cli

from archive import storage as state
from archive import bark


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'archive.sqlite3'
        self.db = state.connect(self.path)
        self.addCleanup(lambda: self.db.close())
        self.devices = {bark.device_id(k): k for k in ('secret-device-one', 'secret-device-two')}
        self.stopped = Mock()
        self.stopped.is_set.return_value = False
        self.stopped.wait.return_value = False

    def queue(self):
        with self.db:
            state.notify(self.db, '2026-08-30', 'success', 'test', '', self.devices)

    def test_partial_delivery_survives_restart_and_only_retries_failed_device(self):
        self.queue()
        ok = Mock(status_code=200)
        ok.json.return_value = {'code': 200}
        bad = Mock(status_code=503)
        with patch.object(bark.SESSION, 'post', side_effect=[ok, bad, bad, bad, bad]) as send:
            bark.deliver_pending(self.db, 'https://api.day.app/push', self.devices, self.stopped, 0)
        self.assertEqual(send.call_count, 5)
        self.db.close()
        self.db = state.connect(self.path)
        with patch.object(bark.SESSION, 'post', return_value=ok) as send:
            bark.deliver_pending(self.db, 'https://api.day.app/push', self.devices, self.stopped)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.kwargs['json']['device_key'], 'secret-device-two')
        self.assertEqual(self.db.execute('SELECT status FROM notifications').fetchone()[0], 'success')
        with patch.object(bark.SESSION, 'post') as send:
            bark.deliver_pending(self.db, 'https://api.day.app/push', self.devices, self.stopped)
            send.assert_not_called()

    def test_invalid_response_and_secret_exception_are_not_success(self):
        self.queue()
        bad = Mock(status_code=200)
        bad.json.return_value = {'code': 400}
        with patch.object(bark.SESSION, 'post', side_effect=[bad, requests.ConnectionError('secret-device-one')] * 4):
            bark.deliver_pending(self.db, 'https://api.day.app/push', self.devices, self.stopped)
        self.assertEqual(self.db.execute("SELECT count(*) FROM push_log WHERE status='failed'").fetchone()[0], 8)
        self.assertNotIn('secret-device', '\n'.join(self.db.iterdump()))
        with patch.object(bark.SESSION, 'post') as send:
            bark.deliver_pending(self.db, 'https://api.day.app/push', self.devices, self.stopped)
            send.assert_not_called()  # Cross-cycle backoff is persisted.

    def test_archive_failure_dedup_and_recovery_transaction(self):
        day = date(2026, 8, 30)
        for _ in range(2):
            attempt = state.start_archive(self.db, day)
            state.finish_archive(self.db, attempt, day, self.devices, error='TimeoutExpired')
        self.assertEqual(self.db.execute('SELECT count(*) FROM notifications').fetchone()[0], 1)
        target = Path(self.tmp.name) / '2026-08-30.md'
        target.write_text('# 财联社电报\n\n> 共 123 条\n', encoding='utf-8')
        attempt = state.start_archive(self.db, day)
        state.finish_archive(self.db, attempt, day, self.devices, path=target)
        self.assertEqual(self.db.execute("SELECT value FROM meta WHERE key='last_success'").fetchone()[0], str(day))
        self.assertEqual(self.db.execute('SELECT item_count FROM archive_log WHERE id=?', (attempt,)).fetchone()[0], 123)
        self.assertEqual(self.db.execute("SELECT status FROM notifications WHERE kind='failure'").fetchone()[0], 'superseded')
        self.assertEqual(self.db.execute("SELECT count(*) FROM deliveries WHERE status='pending'").fetchone()[0], 2)
        title, body = self.db.execute("SELECT title,body FROM notifications WHERE kind='success'").fetchone()
        self.assertEqual(title, '财联社2026-08-30')
        self.assertEqual(body, '已归档电报 123 条')

    def test_disabled_bark_and_config_validation(self):
        with self.db:
            state.notify(self.db, '2026-08-30', 'success', 'test', '', {})
        self.assertEqual(self.db.execute('SELECT status FROM notifications').fetchone()[0], 'disabled')
        with self.assertRaises(ValueError):
            bark.bark_config({'BARK_URL': 'https://api.day.app/secret', 'BARK_DEVICE_KEYS': 'secret'})
        _, keys = bark.bark_config({'BARK_DEVICE_KEYS': 'one,one,two'})
        self.assertEqual(len(keys), 2)


class FetchRetryTests(unittest.TestCase):
    def test_network_retry_preserves_page_cursor(self):
        good = Mock()
        good.json.return_value = {'data': {'roll_data': []}}
        with patch.object(cli.requests, 'get', side_effect=[requests.ReadTimeout(), good]) as get, \
             patch.object(cli._time, 'sleep'):
            self.assertEqual(cli.fetch_v1(last_time=123), [])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs['params'], get.call_args_list[1].kwargs['params'])

    def test_malformed_response_retries_and_exhaustion_raises(self):
        response = Mock()
        response.json.return_value = {'data': {}}
        with patch.dict(os.environ, {'FETCH_RETRIES': '2'}), \
             patch.object(cli.requests, 'get', return_value=response) as get, \
             patch.object(cli._time, 'sleep'):
            with self.assertRaises(ValueError):
                cli.fetch_v1()
        self.assertEqual(get.call_count, 2)
