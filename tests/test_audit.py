import unittest
from app.audit import run_audit
from app.fetch import FetchError, Response

PAGE = b'''<!doctype html><html lang="en"><head><title>Example</title>
<meta name="description" content="An example website"><meta name="viewport" content="width=device-width">
<link rel="canonical" href="https://example.com/">
<script type="application/ld+json">{"@type":"Organization"}</script></head>
<body><h1>Example website</h1><p>''' + b'Useful text about this business. ' * 12 + b'</p><img alt="" src="/image.png"></body></html>'


def fixture(*, robots=b'User-agent: *\nAllow: /', sitemap=b'<urlset/>', missing=False, page=PAGE, status=200):
    def fetch(url, **kwargs):
        if url.endswith(('/robots.txt', '/sitemap.xml')) and missing:
            raise FetchError('Timed out')
        if url.endswith('/robots.txt'):
            return Response(url, 200, {'content-type': 'text/plain'}, robots)
        if url.endswith('/sitemap.xml'):
            return Response(url, 200, {'content-type': 'application/xml'}, sitemap)
        return Response(url, status, {'content-type': 'text/html', 'strict-transport-security': 'max-age=31536000',
                    'content-security-policy': "default-src 'self'; frame-ancestors 'none'", 'x-content-type-options': 'nosniff'}, page)
    return fetch


class AuditTests(unittest.TestCase):
    def test_good_fixture_has_per_check_evidence(self):
        report = run_audit('example.com', fetcher=fixture())
        self.assertEqual(report['scores'], {'security': 100, 'seo': 100, 'ai': 100})
        self.assertTrue(all(c['evidence'] for c in report['checks']))

    def test_unknowns_are_excluded_not_fabricated_as_failures(self):
        report = run_audit('example.com', fetcher=fixture(missing=True))
        self.assertEqual(report['scores']['seo'], 100)
        by_code = {c['code']: c for c in report['checks']}
        self.assertEqual(by_code['sitemap']['status'], 'unknown')
        self.assertEqual(by_code['oai-searchbot']['status'], 'unknown')

    def test_ai_crawler_disallow_changes_only_observed_permission(self):
        report = run_audit('example.com', fetcher=fixture(robots=b'User-agent: OAI-SearchBot\nDisallow: /\n'))
        by_code = {c['code']: c for c in report['checks']}
        self.assertEqual(by_code['oai-searchbot']['status'], 'attention')
        self.assertEqual(by_code['perplexitybot']['status'], 'pass')
        self.assertLess(report['scores']['ai'], 100)

    def test_html_at_sitemap_url_does_not_pass(self):
        report = run_audit('example.com', fetcher=fixture(sitemap=b'<html><body>Not found</body></html>'))
        self.assertEqual(next(c for c in report['checks'] if c['code'] == 'sitemap')['status'], 'attention')

    def test_xml_entities_are_not_expanded(self):
        report = run_audit('example.com', fetcher=fixture(sitemap=b'<!DOCTYPE urlset [<!ENTITY a "x">]><urlset>&a;</urlset>'))
        self.assertEqual(next(c for c in report['checks'] if c['code'] == 'sitemap')['status'], 'attention')

    def test_error_page_never_gets_a_score(self):
        with self.assertRaisesRegex(FetchError, 'No score'):
            run_audit('example.com', fetcher=fixture(status=403))

    def test_noindex_is_observed(self):
        report = run_audit('example.com', fetcher=fixture(page=PAGE.replace(b'</head>', b'<meta name="robots" content="noindex, follow"></head>')))
        self.assertEqual(next(c for c in report['checks'] if c['code'] == 'indexable')['status'], 'attention')
