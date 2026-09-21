import io
import socket
import unittest
from unittest.mock import patch

from app.fetch import FetchError, MAX_BYTES, fetch_public, normalize_url, resolve_public


class FetchTests(unittest.TestCase):
    def test_normalization_drops_secrets_and_encodes_path(self):
        self.assertEqual(normalize_url('HTTPS://EXAMPLE.COM/über?q=secret#token'), 'https://example.com/%C3%BCber')
        self.assertEqual(normalize_url('example.com'), 'https://example.com/')

    def test_rejects_local_hosts_protocols_credentials_and_ports(self):
        for url in ['http://127.0.0.1', 'http://169.254.169.254', 'https://10.0.0.1',
                    'https://[::1]', 'https://[fc00::1]', 'http://localhost', 'https://a.internal',
                    'file:///etc/passwd', 'https://user:secret@example.com', 'https://example.com:8443',
                    'https://example.com\\@localhost', 'https://example.com/\nsecret', '2130706433']:
            with self.subTest(url=url), self.assertRaises(FetchError):
                normalize_url(url)

    def test_mixed_public_and_private_dns_is_rejected(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ['8.8.8.8', '10.0.0.4']]
        with patch('app.fetch.socket.getaddrinfo', return_value=answers), self.assertRaises(FetchError):
            resolve_public('example.com', 443)

    def test_ipv4_mapped_dns_is_rejected(self):
        answers = [(socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::ffff:127.0.0.1', 443, 0, 0))]
        with patch('app.fetch.socket.getaddrinfo', return_value=answers), self.assertRaises(FetchError):
            resolve_public('example.com', 443)

    def test_redirect_to_private_network_is_rejected_before_connection(self):
        class Redirect:
            status = 302
            def getheaders(self): return [('Location', 'http://192.168.1.1/')]
        with patch('app.fetch.resolve_public', return_value=['8.8.8.8']), patch('app.fetch.PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value = Redirect()
            with self.assertRaises(FetchError):
                fetch_public('https://example.com')
            connection.assert_called_once()
            connection.return_value.close.assert_called_once()

    def test_response_size_is_bounded(self):
        class Large:
            status = 200
            def __init__(self): self.data = io.BytesIO(b'x' * (MAX_BYTES + 100))
            def getheaders(self): return [('content-type', 'text/html')]
            def read1(self, n): return self.data.read(n)
        with patch('app.fetch.resolve_public', return_value=['8.8.8.8']), patch('app.fetch.PinnedHTTPS') as connection:
            connection.return_value.getresponse.return_value = Large()
            with self.assertRaisesRegex(FetchError, '2 MB'):
                fetch_public('https://example.com')

    def test_connect_uses_validated_ip_but_original_host_for_tls(self):
        from app.fetch import PinnedHTTPS
        with patch('app.fetch.socket.create_connection') as connect, patch('app.fetch.ssl.create_default_context') as context:
            PinnedHTTPS('example.com', '8.8.8.8', 443, 3).connect()
            connect.assert_called_once_with(('8.8.8.8', 443), 3)
            context.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='example.com')
