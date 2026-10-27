import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('news_evidence_groups_candidate',
    Path(__file__).resolve().parents[1] / 'data/news_evidence_groups.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event(url='https://example.com/a', text='Original exact excerpt', **fields):
    return dict(url=url, source_text=text, **fields)


class EvidenceGroupsTests(unittest.TestCase):
    def test_same_url_retains_versions_and_each_capture(self):
        rows = [event(collected_at='later'), event(text='Updated excerpt', collected_at='earlier'),
                event(collected_at=None)]
        result = module.group_evidence(rows)
        group = result['same_url_groups'][0]
        self.assertTrue(group['has_observed_text_variants'])
        self.assertEqual([v['observation_indices'] for v in group['versions']], [[0, 2], [1]])
        self.assertEqual(result['observations'], rows)
        result['observations'][0]['source_text'] = 'changed'
        self.assertEqual(rows[0]['source_text'], 'Original exact excerpt')

    def test_identical_body_keeps_different_sources_and_times(self):
        rows = [event(source='issuer', published_at='one'),
                event(url='https://example.org/b', source='syndicator', published_at='two')]
        result = module.group_evidence(rows)
        self.assertEqual(result['exact_text_groups'][0]['observation_indices'], [0, 1])
        self.assertEqual(result['observations'], rows)

    def test_titles_hashes_and_approximate_text_never_merge(self):
        rows = [event(title='Same headline', content_sha256='claimed'),
                event(url='https://example.org/b', text='original exact excerpt',
                      title='Same headline', content_sha256='claimed'),
                event(url='https://example.org/c', text='Original exact excerpt ', title='Same headline')]
        result = module.group_evidence(rows)
        self.assertEqual(result['exact_text_groups'], [])
        self.assertEqual(result['same_url_groups'], [])

    def test_missing_text_not_revision_and_empty_not_duplicate(self):
        result = module.group_evidence([event(text=None), event(text=''), event(),
                                        event(url='https://example.org/b', text='')])
        self.assertFalse(result['same_url_groups'][0]['has_observed_text_variants'])
        self.assertEqual(result['same_url_groups'][0]['unavailable_text_indices'], [0, 1])
        self.assertEqual(result['exact_text_groups'], [])

    def test_invalid_urls_retained_but_not_grouped(self):
        rows = [event(url=None), event(url='javascript:alert(1)'), event(url='http://[')]
        result = module.group_evidence(rows)
        self.assertEqual(result['observations'], rows)
        self.assertEqual(result['same_url_groups'], [])
        self.assertEqual(result['exact_text_groups'], [])

    def test_groups_do_not_transitively_merge_different_bodies(self):
        result = module.group_evidence([event(text='v1'), event(text='v2'),
            event(url='https://example.org/b', text='v2')])
        self.assertEqual(result['exact_text_groups'][0]['observation_indices'], [1, 2])
        self.assertEqual(len(result['same_url_groups'][0]['versions']), 2)
        self.assertEqual(module.group_evidence([])['observations'], [])


if __name__ == '__main__':
    unittest.main()
