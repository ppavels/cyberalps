#!/usr/bin/env python3
"""Read-only verification of the public deployment and the shared private site."""
import json
import os
import socket
import time
import urllib.error
import urllib.request

EXPECTED = os.environ['EXPECTED_REVISION']


def request(url):
    try:
        response = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'CyberAlpsDeploymentCheck/1.0'}), timeout=12)
    except urllib.error.HTTPError as response:
        return response.code, dict(response.headers.items()), response.read()
    with response:
        return response.status, dict(response.headers.items()), response.read()


def check():
    addresses = sorted({item[4][0] for item in socket.getaddrinfo('cyberalps.ch', 443, type=socket.SOCK_STREAM)})
    if '185.183.157.51' not in addresses:
        raise RuntimeError('The confirmed IPv4 address is missing from DNS: ' + ', '.join(addresses))
    code, headers, body = request('https://cyberalps.ch/api/health')
    assert code == 200 and json.loads(body).get('revision') == EXPECTED, 'Waiting for the expected CyberAlps revision'
    for lang, text in [('de', b'Sicher.'), ('en', b'Secure.')]:
        code, headers, body = request(f'https://cyberalps.ch/{lang}/')
        assert code == 200 and text in body, 'The language page is not ready'
        assert b'__PUBLIC_ORIGIN__' not in body and b'https://cyberalps.ch/' in body
    code, headers, body = request('https://cyberalps.ch/admin')
    assert code == 401, 'The request inbox must require authentication'
    code, headers, body = request('https://preisli.ch/')
    assert code == 401, 'Preisli must remain private'
    assert 'noindex' in {k.lower(): v for k, v in headers.items()}.get('x-robots-tag', '')
    code, headers, body = request('https://preisli.ch/robots.txt')
    assert code == 200 and b'Disallow: /' in body
    assert request('https://preisli.ch/sitemap.xml')[0] == 410
    print('PASS: cyberalps.ch HTTPS, exact revision, DE/EN, private inbox and Preisli privacy.', flush=True)


def check_own_audit():
    request = urllib.request.Request('https://cyberalps.ch/api/audits',
        data=json.dumps({'url': 'https://cyberalps.ch/en/', 'consent': True}).encode(),
        headers={'Origin': 'https://cyberalps.ch', 'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=15) as response:
        assert response.status == 202
        audit_id = json.load(response)['id']
    for _ in range(45):
        with urllib.request.urlopen('https://cyberalps.ch/api/audits/' + audit_id, timeout=12) as response:
            report = json.load(response)
        if report['status'] == 'error':
            raise RuntimeError('The deployed audit failed: ' + report['error'])
        if report['status'] == 'done':
            assert report['result']['url'] == 'https://cyberalps.ch/en/'
            assert len(report['result']['checks']) >= 15
            print('PASS: real audit of our own website; scores=' + json.dumps(report['result']['scores']))
            return
        time.sleep(2)
    raise RuntimeError('The deployed audit did not finish in time.')


if __name__ == '__main__':
    last = None
    for attempt in range(60):
        try:
            check()
            break
        except (OSError, ValueError, AssertionError, RuntimeError) as error:
            last = str(error)
            print(f'Waiting for rollout ({attempt + 1}/60): {last}', flush=True)
            time.sleep(10)
    else:
        raise SystemExit('Live verification did not complete: ' + str(last))
    check_own_audit()
