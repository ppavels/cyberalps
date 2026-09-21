import base64
import http.client
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from app import server


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = patch.multiple(server, DATA=Path(self.temp.name), ORIGIN='https://cyberalps.example',
                                     ADMIN='test-only-password', JOBS=queue.Queue(maxsize=1), RATE={})
        self.config.start()
        server.initialize()
        self.httpd = server.Server(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.config.stop()
        self.temp.cleanup()

    def request(self, path, data=None, auth=False, origin='https://cyberalps.example'):
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=3)
        headers = {'Content-Type': 'application/json', 'Origin': origin}
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode(b'owner:test-only-password').decode()
        connection.request('POST' if data is not None else 'GET', path, body=json.dumps(data) if data is not None else None, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        result = response.status, dict(response.getheaders()), json.loads(raw) if 'application/json' in response.getheader('Content-Type', '') else raw
        connection.close()
        return result

    def test_origin_and_consent_are_required(self):
        self.assertEqual(self.request('/api/audits', {'url': 'example.com', 'consent': True}, origin='https://elsewhere.example')[0], 403)
        self.assertEqual(self.request('/api/audits', {'url': 'example.com'})[0], 400)
        self.assertEqual(self.request('/api/audits', {'url': '127.0.0.1', 'consent': True})[0], 400)

    def test_full_queue_does_not_leave_orphan_report(self):
        self.assertEqual(self.request('/api/audits', {'url': 'example.com', 'consent': True})[0], 202)
        self.assertEqual(self.request('/api/audits', {'url': 'example.org', 'consent': True})[0], 503)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audits').fetchone()[0], 1)

    def test_contact_request_is_private_and_can_be_managed(self):
        lead = {'name': 'Test Client', 'email': 'client@example.com', 'message': 'Please review the website.', 'consent': True}
        self.assertEqual(self.request('/api/leads', lead)[0], 201)
        self.assertEqual(self.request('/api/admin/leads')[0], 401)
        code, headers, data = self.request('/api/admin/leads', auth=True)
        self.assertEqual(code, 200)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(data[0]['email'], lead['email'])
        url = '/api/admin/leads/' + data[0]['id']
        self.assertEqual(self.request(url, {'action': 'done'})[0], 401)
        self.assertEqual(self.request(url, {'action': 'done'}, auth=True)[0], 200)
        self.assertEqual(self.request('/api/admin/leads', auth=True)[2][0]['status'], 'done')
        self.assertEqual(self.request(url, {'action': 'delete'}, auth=True)[0], 200)
        self.assertEqual(self.request('/api/admin/leads', auth=True)[2], [])

    def test_all_admin_page_paths_require_authentication(self):
        for path in ['/admin', '/admin/', '/admin.html']:
            self.assertEqual(self.request(path)[0], 401)

    def test_rate_limit_and_expiry(self):
        for _ in range(5): self.assertTrue(server.rate_allowed('192.0.2.1', 'audit'))
        self.assertFalse(server.rate_allowed('192.0.2.1', 'audit'))
        self.assertTrue(server.rate_allowed('192.0.2.2', 'audit'))
        with server.connect() as db:
            db.execute('INSERT INTO audits VALUES (?,?,?,?,?,?,?)', ('a'*32, 'https://example.com/', time.time()-86500, 'done', 'done', '{}', None))
            db.execute('INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?)', ('b'*32, time.time()-31*86400, 'Client', 'client@example.com', '', 'test', 'en', '', 'new'))
        self.assertEqual(self.request('/api/audits/'+'a'*32)[0], 404)
        server.cleanup()
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM audits').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 0)
