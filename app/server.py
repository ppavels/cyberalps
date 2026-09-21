"""Small bounded web server with a single audit worker and local SQLite storage."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .audit import run_audit
from .fetch import FetchError, normalize_url

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('DATA_DIR', str(ROOT / 'data')))
ORIGIN = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
REVISION = os.environ.get('CYBERALPS_REVISION', 'development')
ADMIN = os.environ.get('ADMIN_PASSWORD', '')
JOBS = queue.Queue(maxsize=12)
RATE = {}
RATE_LOCK = threading.Lock()
RATE_SALT = secrets.token_bytes(32)


def connect():
    connection = sqlite3.connect(DATA / 'cyberalps.sqlite3', timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with connect() as db:
        db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS audits (
            id TEXT PRIMARY KEY, url TEXT NOT NULL, created REAL NOT NULL,
            status TEXT NOT NULL, stage TEXT NOT NULL, result TEXT, error TEXT
          );
          CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY, created REAL NOT NULL, name TEXT NOT NULL,
            email TEXT NOT NULL, url TEXT NOT NULL, message TEXT NOT NULL,
            language TEXT NOT NULL, audit_id TEXT, status TEXT NOT NULL DEFAULT 'new'
          );
        ''')
        db.execute("UPDATE audits SET status='error', error='The service restarted. Please run the check again.' WHERE status IN ('queued','running')")
    cleanup()


def cleanup():
    with connect() as db:
        db.execute('DELETE FROM audits WHERE created < ?', (time.time() - 86400,))
        db.execute('DELETE FROM leads WHERE created < ?', (time.time() - 30 * 86400,))


def worker():
    while True:
        try:
            audit_id, url = JOBS.get(timeout=300)
        except queue.Empty:
            cleanup()
            continue
        try:
            def progress(stage):
                with connect() as db:
                    db.execute("UPDATE audits SET status='running', stage=? WHERE id=?", (stage, audit_id))
            result = run_audit(url, progress=progress)
            with connect() as db:
                db.execute("UPDATE audits SET status='done', stage='done', result=? WHERE id=?", (json.dumps(result), audit_id))
        except Exception as exc:
            message = str(exc) if isinstance(exc, FetchError) else 'The check could not be completed. Please try again later.'
            with connect() as db:
                db.execute("UPDATE audits SET status='error', error=? WHERE id=?", (message, audit_id))
        finally:
            JOBS.task_done()
            cleanup()


def rate_allowed(address, kind):
    now = time.monotonic()
    key = (hashlib.sha256(RATE_SALT + address.encode()).hexdigest(), kind)
    with RATE_LOCK:
        for old in [k for k, v in RATE.items() if not v or v[-1] < now - 3600]:
            del RATE[old]
        history = [v for v in RATE.get(key, []) if v > now - 3600]
        limit = 5 if kind == 'audit' else 3
        if len(RATE) >= 10000 or len(history) >= limit:
            return False
        RATE[key] = history + [now]
        return True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(20)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'CyberAlps'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, *args):
        pass

    def send(self, status, data=b'', mime='application/json; charset=utf-8', extra=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if self.path.startswith('/assets/') else 'no-store')
        if self.path.startswith(('/api/', '/admin')):
            self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > 8192 or self.headers.get_content_type() != 'application/json':
            raise ValueError('Send a JSON request smaller than 8 KB.')
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError('A JSON object is required.')
        return data

    def authorized(self):
        if not ADMIN:
            self.send(503, {'error': 'Administration is unavailable.'})
            return False
        wanted = 'Basic ' + base64.b64encode(('owner:' + ADMIN).encode()).decode()
        if not hmac.compare_digest(self.headers.get('Authorization', ''), wanted):
            self.send(401, {'error': 'Sign in required.'}, extra={'WWW-Authenticate': 'Basic realm="CyberAlps", charset="UTF-8"'})
            return False
        return True

    def valid_origin(self):
        origin = self.headers.get('Origin', '')
        expected = ORIGIN or ('http://' + self.headers.get('Host', ''))
        if not origin or origin != expected:
            self.send(403, {'error': 'Submit this form from the CyberAlps website.'})
            return False
        return True

    def client_address_key(self):
        address = self.client_address[0]
        if os.environ.get('TRUST_PROXY') == '1':
            candidate = self.headers.get('X-Real-IP', '')
            try:
                address = str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
        return address

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            try:
                with connect() as db:
                    db.execute('SELECT 1').fetchone()
                return self.send(200, {'ok': True, 'revision': REVISION, 'queue': JOBS.qsize()})
            except sqlite3.Error:
                return self.send(503, {'ok': False})
        if re.fullmatch(r'/api/audits/[a-f0-9]{32}', path):
            with connect() as db:
                row = db.execute('SELECT * FROM audits WHERE id=? AND created>?', (path.split('/')[-1], time.time()-86400)).fetchone()
            if not row:
                return self.send(404, {'error': 'This report expired or does not exist.'})
            data = dict(row)
            if data['result']:
                data['result'] = json.loads(data['result'])
            return self.send(200, data)
        if path == '/api/admin/leads':
            if not self.authorized():
                return
            with connect() as db:
                leads = [dict(row) for row in db.execute('SELECT * FROM leads ORDER BY created DESC LIMIT 200')]
            return self.send(200, leads)
        if path in {'/admin', '/admin/', '/admin.html'} and not self.authorized():
            return
        if path.startswith('/api/'):
            return self.send(404, {'error': 'Not found.'})
        if path == '/':
            return self.send(302, b'', extra={'Location': '/de/'})
        if path == '/robots.txt':
            text = 'User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\n'
            if ORIGIN:
                text += f'Sitemap: {ORIGIN}/sitemap.xml\n'
            return self.send(200, text, 'text/plain; charset=utf-8')
        if path == '/sitemap.xml':
            if not ORIGIN:
                return self.send(503, {'error': 'Canonical domain is not configured.'})
            from html import escape
            urls = ''.join(f'<url><loc>{escape(ORIGIN)}/{lang}/</loc></url>' for lang in ['de', 'en'])
            return self.send(200, '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+urls+'</urlset>', 'application/xml')
        root = (ROOT / 'dist').resolve()
        target = (root / path.lstrip('/')).resolve()
        if root not in target.parents or '/ssr/' in path:
            return self.send(404, {'error': 'Not found.'})
        if target.is_dir():
            target /= 'index.html'
        if not target.is_file() and path in {'/admin', '/admin/'}:
            target = root / 'admin.html'
        if not target.is_file():
            return self.send(404, 'Page not found.', 'text/plain; charset=utf-8')
        data = target.read_bytes()
        if target.suffix == '.html':
            from html import escape
            data = data.replace(b'__PUBLIC_ORIGIN__', escape(ORIGIN, quote=True).encode())
        return self.send(200, data, mimetypes.guess_type(target.name)[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.valid_origin():
            return
        path = urlsplit(self.path).path
        try:
            data = self.json_body()
            if path == '/api/audits':
                if data.get('consent') is not True:
                    raise ValueError('Confirm that you own or manage this website.')
                url = normalize_url(data.get('url'))
                if not rate_allowed(self.client_address_key(), 'audit'):
                    return self.send(429, {'error': 'The hourly check limit has been reached. Please try again later.'}, extra={'Retry-After': '3600'})
                audit_id = secrets.token_hex(16)
                with connect() as db:
                    db.execute('INSERT INTO audits VALUES (?,?,?,?,?,?,?)', (audit_id, url, time.time(), 'queued', 'queued', None, None))
                try:
                    JOBS.put_nowait((audit_id, url))
                except queue.Full:
                    with connect() as db:
                        db.execute('DELETE FROM audits WHERE id=?', (audit_id,))
                    return self.send(503, {'error': 'All check slots are busy. Please try again shortly.'}, extra={'Retry-After': '60'})
                return self.send(202, {'id': audit_id, 'status': 'queued'})
            if path == '/api/leads':
                if data.get('website'):
                    return self.send(200, {'ok': True})
                if data.get('consent') is not True:
                    raise ValueError('Consent is required to handle your request.')
                name, email, message = [str(data.get(key, '')).strip() for key in ['name', 'email', 'message']]
                if not 2 <= len(name) <= 100 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email) or len(email) > 254 or not 10 <= len(message) <= 3000:
                    raise ValueError('Check your name, email and message (10–3000 characters).')
                if not rate_allowed(self.client_address_key(), 'lead'):
                    return self.send(429, {'error': 'Please try again later.'})
                site = normalize_url(data['url']) if data.get('url') else ''
                audit_id = data.get('auditId', '')
                if not re.fullmatch(r'[a-f0-9]{32}', str(audit_id)):
                    audit_id = ''
                with connect() as db:
                    db.execute('INSERT INTO leads (id,created,name,email,url,message,language,audit_id) VALUES (?,?,?,?,?,?,?,?)',
                               (secrets.token_hex(16), time.time(), name, email, site, message, 'de' if data.get('language') == 'de' else 'en', audit_id))
                return self.send(201, {'ok': True})
            if re.fullmatch(r'/api/admin/leads/[a-f0-9]{32}', path):
                if not self.authorized():
                    return
                lead_id = path.split('/')[-1]
                with connect() as db:
                    if data.get('action') == 'delete':
                        db.execute('DELETE FROM leads WHERE id=?', (lead_id,))
                    elif data.get('action') == 'done':
                        db.execute("UPDATE leads SET status='done' WHERE id=?", (lead_id,))
                    else:
                        raise ValueError('Unknown action.')
                return self.send(200, {'ok': True})
            return self.send(404, {'error': 'Not found.'})
        except (ValueError, TypeError) as exc:
            return self.send(400, {'error': str(exc)[:300]})
        except (sqlite3.Error, OSError):
            return self.send(503, {'error': 'The service is temporarily unavailable.'})


def main():
    if ORIGIN and not re.fullmatch(r'https://[a-z0-9.-]+', ORIGIN):
        raise RuntimeError('PUBLIC_BASE_URL must be an HTTPS origin without a path.')
    initialize()
    threading.Thread(target=worker, daemon=True, name='audit-worker').start()
    server = Server(('0.0.0.0', int(os.environ.get('PORT', '3002'))), Handler)
    print('CyberAlps listening; revision=' + REVISION, flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
