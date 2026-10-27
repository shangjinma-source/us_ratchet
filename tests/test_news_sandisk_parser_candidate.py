import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('sandisk_candidate',
    Path(__file__).resolve().parents[1] / 'data/news_sandisk_parser.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
URL = 'https://www.sandisk.com/company/newsroom/press-releases/2026/sample'


def page(body=None):
    body = body or 'Sandisk Corporation (NASDAQ: SNDK) announces a conference call. This release gives a schedule only and no earnings figures.'
    return f'''<html><head><link rel="canonical" href="{URL}">
    <meta name="article:published_time" content="2026-09-29T21:30:00+00:00"></head>
    <body><div><h1>Company conference announcement</h1><p>MILPITAS - September 29, 2026</p>
    <div class="para-text">{body}</div></div><a href="/company/newsroom">Newsroom</a>
    <a href="https://untrusted.example/newsroom">Other</a></body></html>'''.encode()


class SandiskParserTests(unittest.TestCase):
    def test_structural_body_and_observed_links(self):
        result = module.parse_release(page(), URL, '2026-10-27T00:00:00+00:00')
        self.assertEqual(result['event']['tickers'], ['SNDK'])
        self.assertIn('schedule only', result['event']['source_text'])
        self.assertEqual(result['observed_newsroom_links'], ['https://www.sandisk.com/company/newsroom'])
        self.assertEqual(result['event']['analysis_status'], 'NOT_ANALYZED')

    def test_future_date_wrong_origin_and_bot_page_rejected(self):
        for raw, url, date in [(page(), URL, '2026-09-01T00:00:00+00:00'),
            (page(), URL.replace('www.sandisk.com', 'fake.example'), '2026-10-27T00:00:00+00:00'),
            (b'<h1>Verify human</h1>', URL, '2026-10-27T00:00:00+00:00')]:
            with self.assertRaises(ValueError):
                module.parse_release(raw, url, date)

    def test_no_issuer_and_conflicting_date_rejected(self):
        for raw in [page().replace(b'Sandisk', b'OtherCo'), page().replace(b'September 29,', b'September 28,')]:
            with self.assertRaises(ValueError):
                module.parse_release(raw, URL, '2026-10-27T00:00:00+00:00')

    def test_no_ticker_product_body_allowed_but_navigation_not_body(self):
        result = module.parse_release(page().replace(b'(NASDAQ: SNDK)', b''), URL,
                                      '2026-10-27T00:00:00+00:00')
        self.assertEqual(result['event']['ticker_association'], 'fixed_official_issuer_mapping_not_body_ticker_mention')
        raw = page().replace(b'Sandisk', b'OtherCo').replace(b'<body>', b'<body><nav>Sandisk</nav>')
        with self.assertRaises(ValueError):
            module.parse_release(raw, URL, '2026-10-27T00:00:00+00:00')
        with self.assertRaises(ValueError):
            module.parse_release(page().replace(URL.encode(), (URL+'-wrong').encode()), URL,
                                 '2026-10-27T00:00:00+00:00')

    def test_generic_title_and_truncation(self):
        result = module.parse_release(page('Sandisk (NASDAQ:SNDK) ' + 'Details ' * 1000), URL,
                                      '2026-10-27T00:00:00+00:00')
        self.assertEqual(len(result['event']['source_text']), 6000)
        self.assertEqual(len(result['event']['uncertainty']), 2)


if __name__ == '__main__':
    unittest.main()
