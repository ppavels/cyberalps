"""Bounded, DNS-pinned public HTTP requests for passive website checks."""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5


class FetchError(ValueError):
    pass


def normalize_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise FetchError('Enter a valid website address.')
    value = value.strip()
    if any(ord(c) < 33 for c in value) or '\\' in value:
        raise FetchError('The website address contains invalid characters.')
    if '://' not in value:
        value = 'https://' + value
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise ValueError()
        if parsed.username is not None or parsed.password is not None:
            raise ValueError()
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
        port = parsed.port
        if port not in {None, 80 if parsed.scheme == 'http' else 443}:
            raise ValueError()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')):
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError()
        except ValueError:
            if ':' in host or host.replace('.', '').isdigit():
                raise
        if ':' not in host and '.' not in host:
            raise ValueError()
        host = '[' + host + ']' if ':' in host else host
        path = quote(parsed.path or '/', safe="/%:@!$&'()*+,;=-._~")
        return urlunsplit((parsed.scheme, host, path, '', ''))
    except (ValueError, UnicodeError) as exc:
        raise FetchError('Use a public HTTP or HTTPS website without credentials or custom ports.') from exc


def resolve_public(host: str, port: int) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError('The website hostname could not be resolved.') from exc
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or any(not ipaddress.ip_address(ip).is_global or
                            (getattr(ipaddress.ip_address(ip), 'ipv4_mapped', None) is not None)
                            for ip in addresses):
        raise FetchError('Private, local and reserved network addresses cannot be checked.')
    return addresses


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self.ip = ip

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), self.timeout)


class PinnedHTTPS(PinnedHTTP):
    def connect(self):
        super().connect()
        try:
            self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
        except Exception:
            self.sock.close()
            raise


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes
    elapsed_ms: int = 0

    @property
    def text(self):
        return self.body.decode('utf-8', errors='replace')


def fetch_public(value: str, *, deadline: float | None = None) -> Response:
    url = normalize_url(value)
    deadline = deadline or time.monotonic() + 20
    started = time.monotonic()
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError('The website took too long to respond.')
        parts = urlsplit(url)
        port = 443 if parts.scheme == 'https' else 80
        ips = resolve_public(parts.hostname, port)
        cls = PinnedHTTPS if port == 443 else PinnedHTTP
        conn = cls(parts.hostname, ips[0], port, min(6, remaining))
        try:
            conn.request('GET', parts.path or '/', headers={
                'User-Agent': 'CyberAlpsCheck/1.0 (passive website health check)',
                'Accept': 'text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.1',
                'Accept-Encoding': 'identity', 'Connection': 'close',
            })
            response = conn.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            if response.status in {301, 302, 303, 307, 308}:
                location = headers.get('location')
                if not location:
                    raise FetchError('The website returned an invalid redirect.')
                url = normalize_url(urljoin(url, location))
                continue
            if headers.get('content-encoding', 'identity').lower() != 'identity':
                raise FetchError('The website ignored the uncompressed response request.')
            body = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise FetchError('The website took too long to respond.')
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise FetchError('The response exceeds the 2 MB check limit.')
            return Response(url, response.status, headers, bytes(body), int((time.monotonic() - started) * 1000))
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError('Could not establish a verified connection to this website.') from exc
        finally:
            conn.close()
    raise FetchError('The website redirects too many times.')
