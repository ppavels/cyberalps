"""Evidence-based technical checks, not a vulnerability or ranking guarantee."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

from .fetch import FetchError, fetch_public, normalize_url


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.meta = {}
        self.canonical = ''
        self.lang = ''
        self.h1 = 0
        self.images = 0
        self.images_missing_alt = 0
        self.json_ld = []
        self.mixed = []
        self.in_title = False
        self.in_json = False
        self.buffer = ''
        self.text_parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style'}:
            self.skip += 1
        if tag == 'html':
            self.lang = attrs.get('lang', '') or ''
        if tag == 'title':
            self.in_title = True
        if tag == 'h1':
            self.h1 += 1
        if tag == 'meta':
            key = (attrs.get('name') or attrs.get('property') or '').lower()
            self.meta[key] = attrs.get('content') or ''
        if tag == 'link' and 'canonical' in (attrs.get('rel') or '').lower().split():
            self.canonical = attrs.get('href') or ''
        if tag == 'img':
            self.images += 1
            self.images_missing_alt += 'alt' not in attrs
        if tag in {'script', 'img', 'iframe', 'link', 'source', 'video', 'audio'}:
            for key in ['src', 'href', 'srcset']:
                if 'http://' in (attrs.get(key) or '').lower():
                    self.mixed.append(attrs[key][:160])
        if tag == 'script' and (attrs.get('type') or '').lower() == 'application/ld+json':
            self.in_json = True
            self.buffer = ''

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script' and self.in_json:
            self.json_ld.append(self.buffer)
            self.in_json = False
        if tag in {'script', 'style'}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_json:
            self.buffer += data
        if not self.skip and data.strip():
            self.text_parts.append(data.strip())


def run_audit(value, fetcher=fetch_public, progress=lambda _: None):
    url = normalize_url(value)
    deadline = time.monotonic() + 45
    progress('page')
    response = fetcher(url, deadline=deadline)
    if response.status != 200:
        raise FetchError(f'The page returned HTTP {response.status}. No score was generated.')
    if not any(t in response.headers.get('content-type', '').lower() for t in ('text/html', 'application/xhtml+xml')):
        raise FetchError('This URL does not return an HTML webpage.')
    page = Page()
    page.feed(response.text)
    headers = response.headers
    checks = []

    def add(code, category, passed, evidence, weight=1):
        checks.append({'code': code, 'category': category,
                       'status': 'unknown' if passed is None else 'pass' if passed else 'attention',
                       'evidence': str(evidence)[:350], 'weight': weight})

    secure = urlsplit(response.url).scheme == 'https'
    progress('checks')
    add('https', 'security', secure, response.url, 3)
    add('hsts', 'security', bool(headers.get('strict-transport-security')), headers.get('strict-transport-security', 'Not present'), 2)
    csp = headers.get('content-security-policy', '')
    add('csp', 'security', bool(csp), csp or 'Not present', 2)
    add('nosniff', 'security', headers.get('x-content-type-options', '').lower() == 'nosniff', headers.get('x-content-type-options', 'Not present'))
    frame = headers.get('x-frame-options', '')
    add('framing', 'security', frame.upper() in {'DENY', 'SAMEORIGIN'} or 'frame-ancestors' in csp.lower(), frame or ('frame-ancestors in CSP' if 'frame-ancestors' in csp.lower() else 'Not present'))
    add('mixed', 'security', not page.mixed if secure else None, f'{len(page.mixed)} HTTP resource references')
    add('title', 'seo', bool(page.title.strip()), page.title.strip() or 'Not present', 2)
    description = page.meta.get('description', '').strip()
    add('description', 'seo', bool(description), description or 'Not present')
    add('h1', 'seo', page.h1 == 1, f'{page.h1} H1 elements')
    add('canonical', 'seo', bool(page.canonical), page.canonical or 'Not present')
    directives = (page.meta.get('robots', '') + ',' + page.meta.get('googlebot', '') + ',' + headers.get('x-robots-tag', '')).lower()
    import re
    tokens = re.split(r'[\s,;:]+', directives)
    add('indexable', 'seo', not any(x in tokens for x in ['noindex', 'none']), directives.strip(',') or 'No noindex directive observed', 3)
    add('viewport', 'seo', 'width=device-width' in page.meta.get('viewport', '').replace(' ', '').lower(), page.meta.get('viewport', 'Not present'))
    add('alt', 'seo', page.images_missing_alt == 0, f'{page.images_missing_alt} of {page.images} images have no alt attribute')
    add('language', 'ai', bool(page.lang), page.lang or 'Not present')
    valid = 0
    for item in page.json_ld:
        try:
            parsed = json.loads(item)
            if isinstance(parsed, (dict, list)) and parsed:
                valid += 1
        except (ValueError, TypeError):
            pass
    add('structured', 'ai', valid > 0, f'{valid} parseable JSON-LD blocks; schema accuracy not validated', 2)
    readable = len(' '.join(page.text_parts))
    add('readable', 'ai', readable >= 200, f'{readable} text characters in the initial HTML; heuristic threshold: 200', 2)
    progress('discovery')
    parts = urlsplit(response.url)
    origin = urlunsplit((parts.scheme, parts.netloc, '', '', ''))
    try:
        robots = fetcher(origin + '/robots.txt', deadline=deadline)
        is_robots = robots.status == 200 and 'text/html' not in robots.headers.get('content-type', '').lower()
        add('robots', 'seo', is_robots, f'HTTP {robots.status}')
        if is_robots:
            parser = RobotFileParser()
            parser.parse(robots.text.splitlines())
            add('googlebot', 'seo', parser.can_fetch('Googlebot', response.url), 'robots.txt rule for Googlebot', 2)
            for agent in ['OAI-SearchBot', 'PerplexityBot']:
                add(agent.lower(), 'ai', parser.can_fetch(agent, response.url), f'robots.txt permission for {agent}; actual access not verified')
        elif robots.status in {404, 410}:
            for agent in ['OAI-SearchBot', 'PerplexityBot']:
                add(agent.lower(), 'ai', True, f'No robots.txt found (HTTP {robots.status}); no rule observed')
        else:
            for agent in ['OAI-SearchBot', 'PerplexityBot']:
                add(agent.lower(), 'ai', None, f'robots.txt could not be interpreted (HTTP {robots.status})')
    except FetchError:
        add('robots', 'seo', None, 'Could not retrieve robots.txt')
        for agent in ['OAI-SearchBot', 'PerplexityBot']:
            add(agent.lower(), 'ai', None, 'Could not evaluate robots.txt')
    try:
        sitemap = fetcher(origin + '/sitemap.xml', deadline=deadline)
        valid_map = False
        if sitemap.status == 200 and b'<!DOCTYPE' not in sitemap.body.upper() and b'<!ENTITY' not in sitemap.body.upper():
            try:
                root = ET.fromstring(sitemap.body)
                valid_map = root.tag.split('}')[-1] in {'urlset', 'sitemapindex'}
            except ET.ParseError:
                pass
        add('sitemap', 'seo', valid_map, f'/sitemap.xml: HTTP {sitemap.status}; XML sitemap detected: {valid_map}')
    except FetchError:
        add('sitemap', 'seo', None, 'Could not retrieve /sitemap.xml')
    scores = {}
    for category in ['security', 'seo', 'ai']:
        observed = [c for c in checks if c['category'] == category and c['status'] != 'unknown']
        possible = sum(c['weight'] for c in observed)
        scores[category] = round(100 * sum(c['weight'] for c in observed if c['status'] == 'pass') / possible) if possible else None
    return {'url': response.url, 'checkedAt': datetime.now(timezone.utc).isoformat(),
            'scores': scores, 'checks': checks, 'pageBytes': len(response.body),
            'fetchMs': response.elapsed_ms, 'title': page.title.strip()[:200],
            'methodology': 'Weighted technical checklist v1; unknown checks excluded. Single page plus robots.txt and /sitemap.xml. No JavaScript rendering, penetration test, Core Web Vitals, or AI-answer measurement.'}
