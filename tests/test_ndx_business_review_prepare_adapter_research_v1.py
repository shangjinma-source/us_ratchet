"""Bounded saved-fact checks; no review/apply/publication or economic engines."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_business_review_prepare_adapter_research_v1 as module


class PrepareReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = module.prepare_reviewpack()

    def test_saved_complete_scope_and_pending_policy(self):
        self.assertEqual([r['template']['ticker'] for r in self.pack['rows']],
            ['AMD', 'HON', 'EXC', 'TSLA', 'SHOP', 'CCEP', 'DASH', 'ARM', 'TRI', 'FER'])
        self.assertEqual(self.pack['independently_reconstructed_counts'],
            dict(direct_section_children=960, ccep_page_occurrences=43, fer_content_children=1155))
        for row in self.pack['rows']:
            self.assertEqual(set(row['template']), set(self.pack['template_columns']))
            self.assertIsNone(row['template']['risk_chain'])
            self.assertEqual(row['template']['status'], 'pending_review')
            for field in ('security_id', 'effective_from', 'effective_to', 'evidence_available_date', 'confidence'):
                self.assertEqual(row['template'][field], '')
            for field in module.FALSE_FIELDS:
                self.assertIs(row[field], False)
            self.assertIsNone(row['source_available_at_utc'])
            self.assertNotIn('LOCAL_RAW_FETCH_POSTDATES_ORIGINAL_SELECTION_2026_07_13', row['blockers'])
            self.assertIn('LOCAL_RAW_FETCH_POSTDATES_ORIGINAL_SELECTION_2026_07_13', row['timing_diagnostics'])
        tri, fer = self.pack['rows'][-2:]
        self.assertIsNone(tri['complete_business_evidence'])
        self.assertEqual(tri['template']['evidence_excerpt'], '')
        self.assertEqual(len(fer['original_identity_candidates']), 2)

    def test_validator_reads_real_sources_and_returns_detached(self):
        result = module.validate_reviewpack(self.pack)
        self.assertEqual(result, self.pack)
        result['rows'][0]['template']['notes'] = 'changed caller copy'
        self.assertNotEqual(result, self.pack)

    def test_validate_rejects_caller_fulltext_and_identity_changes(self):
        for change in ('quote', 'fer_identity', 'available_at'):
            bad = deepcopy(self.pack)
            if change == 'quote':
                bad['rows'][0]['complete_business_evidence']['exact_quote_text'] = bad['rows'][0]['complete_business_evidence']['exact_quote_text'][:-1]
            elif change == 'fer_identity':
                bad['rows'][-1]['original_identity_candidates'].pop()
            else:
                bad['rows'][0]['source_available_at_utc'] = bad['rows'][0]['timing_declarations']['official_acceptance_datetime_as_declared']
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.validate_reviewpack(bad)

    def test_exact_gate_rejects_missing_extra_order_and_boolean_zero(self):
        mutations = []
        bad = deepcopy(self.pack); bad.pop('rows'); mutations.append(bad)
        bad = deepcopy(self.pack); bad['extra'] = {}; mutations.append(bad)
        bad = deepcopy(self.pack); bad['rows'].reverse(); mutations.append(bad)
        for value in (True, 0, None):
            bad = deepcopy(self.pack); bad['rows'][0]['accepted'] = value; mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(ValueError):
                module._exact(bad, self.pack, 'Closed pending pack')

    def test_closed_follow_never_reads_unknown_claim(self):
        sources = module._FixedSources()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Reference must not cause IO')):
            for ref in (dict(path=str(module.ROOT / 'tmp/unknown_review_raw.html'), sha256='a' * 64),
                        dict(sources.reference(module.PLAN), extra_authority=True)):
                with self.assertRaises(ValueError):
                    sources.follow(ref)
            self.assertEqual(sources.follow(sources.reference(module.PLAN)), sources.raw[module.PLAN])

    def test_final_guard_rejects_namespace_or_byte_drift(self):
        sources = module._FixedSources()
        original_inventory = module._inventory
        first = next(iter(sources.contract['namespace_inventories']))
        def changed_inventory(folder):
            items = original_inventory(folder)
            return items + ['failure.json'] if folder == module.ROOT / first else items
        with patch.object(module, '_inventory', side_effect=changed_inventory), self.assertRaises(ValueError):
            sources.final_guard()
        original_read = Path.read_bytes
        target = module.ROOT / module.PLAN
        def changed_bytes(path):
            raw = original_read(path)
            return raw + b' ' if path == target else raw
        with patch.object(Path, 'read_bytes', changed_bytes), self.assertRaises(ValueError):
            sources.final_guard()

    def test_independent_segment_complete_unicode_and_truncation(self):
        parser = module._OriginalHTML('<html><body><div>业务 α</div><div>stop</div></body></html>'.encode())
        node = parser.node('/html/body/div[1]')
        text = module._text(node)
        segment = dict(parent_xpath='/html/body', child_index_start=0, child_index_stop_exclusive=1,
            included_children=[dict(dom_xpath='/html/body/div[1]', child_index=0,
                normalized_characters=len(text), normalized_sha256=module._sha(text.encode()))])
        self.assertEqual(module._check_segment(parser, segment)[1], text.encode())
        for key, value in [('child_index_stop_exclusive', True), ('included_children', [])]:
            bad = deepcopy(segment); bad[key] = value
            with self.assertRaises(ValueError):
                module._check_segment(parser, bad)
        bad = deepcopy(segment); bad['included_children'][0]['normalized_sha256'] = module._sha(text[:-1].encode())
        with self.assertRaises(ValueError):
            module._check_segment(parser, bad)

    def test_duplicate_nonfinite_json_and_source_contract_failure(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.assertRaises(ValueError):
                module._json(raw)
        with patch.object(module, 'CONTRACT_SHA256', '0' * 64), self.assertRaises(ValueError):
            module.prepare_reviewpack()


if __name__ == '__main__':
    unittest.main()
