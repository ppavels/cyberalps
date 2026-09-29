import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app import server, notifications
from scripts import auto_update


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = patch.multiple(server, DATA=Path(self.directory.name))
        self.settings.start()
        self.credentials = patch.multiple(notifications, TOKEN='123:test_token', CHAT='456')
        self.credentials.start()
        server.initialize()

    def tearDown(self):
        self.credentials.stop()
        self.settings.stop()
        self.directory.cleanup()

    def test_setup_is_sent_once_across_restarts(self):
        with patch.object(notifications, 'send', return_value=('77', 0)) as send:
            self.assertTrue(notifications.deliver_one(server.connect, 'https://cyberalps.ch'))
            self.assertIn('🏔️ CyberAlps', send.call_args.args[0])
            server.initialize()
            self.assertFalse(notifications.deliver_one(server.connect, 'https://cyberalps.ch'))
            send.assert_called_once()

    def test_delivery_failure_survives_restart_and_retries(self):
        with patch.object(notifications, 'send', side_effect=OSError('secret URL must never be logged')):
            notifications.deliver_one(server.connect, 'https://cyberalps.ch')
        server.initialize()
        with server.connect() as db:
            row = db.execute('SELECT * FROM notifications').fetchone()
            self.assertIsNone(row['sent'])
            self.assertEqual(row['attempts'], 1)
            self.assertGreater(row['next_attempt'], time.time())
            db.execute('UPDATE notifications SET next_attempt=0')
        with patch.object(notifications, 'send', return_value=('78', 0)):
            self.assertTrue(notifications.deliver_one(server.connect, 'https://cyberalps.ch'))
        with server.connect() as db:
            self.assertIsNotNone(db.execute('SELECT sent FROM notifications').fetchone()[0])

    def test_contact_plain_text_is_bounded_and_deleted_events_are_removed(self):
        with server.connect() as db:
            db.execute('INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?)', ('a'*32, time.time(), '<b>Client</b>', 'client@example.com', '', '😀'*3000, 'en', '', 'new'))
            notifications.enqueue(db, 'lead', 'a'*32)
            row = db.execute("SELECT * FROM notifications WHERE kind='lead'").fetchone()
            text = notifications.message(db, row, 'https://cyberalps.ch')
            self.assertIn('🏔️ CyberAlps · Новая заявка', text)
            self.assertIn('<b>Client</b>', text)
            self.assertLess(len(text.encode('utf-16-le'))//2, 4096)
            db.execute('DELETE FROM leads')
            notifications.cleanup(db)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE kind='lead'").fetchone()[0], 0)

    def test_telegram_request_has_fixed_recipient_and_no_markup(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true,"result":{"message_id":123}}'
        with patch('urllib.request.urlopen', return_value=response) as request:
            self.assertEqual(notifications.send('<b>customer input</b>'), ('123', 0))
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body['chat_id'], '456')
        self.assertNotIn('parse_mode', body)
        self.assertTrue(body['link_preview_options']['is_disabled'])

    def test_disabled_delivery_does_not_call_telegram(self):
        with patch.object(notifications, 'TOKEN', ''), patch.object(notifications, 'send') as send:
            self.assertFalse(notifications.deliver_one(server.connect, 'https://cyberalps.ch'))
            send.assert_not_called()

    def test_configuration_is_copied_once_without_logging_secrets(self):
        env = Path(self.directory.name)/'production.env'
        env.write_text('PUBLIC_BASE_URL=https://cyberalps.ch\nADMIN_PASSWORD=existing\n')
        with patch.object(auto_update, 'ROOT', Path('/opt/cyberalps')), patch.object(auto_update, 'ENV', env), patch.object(auto_update, 'command', side_effect=['container-id', 'TELEGRAM_BOT_TOKEN=123:test_token\nTELEGRAM_CHAT_ID=456']) as command, patch('builtins.print') as output:
            self.assertTrue(auto_update.configure_shared_telegram())
            self.assertFalse(auto_update.configure_shared_telegram())
            self.assertEqual(command.call_count, 2)
            self.assertNotIn('test_token', str(output.call_args_list))
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertIn('ADMIN_PASSWORD=existing', env.read_text())
