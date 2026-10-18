"""Synthetic V3 envelopes; no capture entrypoint, observations or output files."""
from copy import deepcopy
from hashlib import sha256
import unittest

from backtest import ndx_forward_gap_parent_capture_research_v3 as module
from backtest import ndx_prospective_gap_history_research_v3 as gap
from test_ndx_prospective_gap_history_research_v3 import fixture as gap_fixture, reference


def fixture(new_dates=(), start='2026-10-09T21:00:00+00:00', end=None):
    old = gap_fixture()
    h = gap.extend_gap_history(**old)
    refs = {role: reference('v3/' + role) for role in module.ROLES}
    refs['reader_reference']['sha256'] = module.PARENT_READER_SHA256
    inputs = dict(parent={role: old['parent'][role] for role in module.ROLES},
                  capture={role: old['capture'][role] for role in module.ROLES}, pure=reference('pure'))
    sources = deepcopy(h['source_hashes'])
    module.inventory_references(inputs, sources)
    wrapper = dict(schema='SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3', history=h,
                   input_references=inputs, source_hashes=deepcopy(sources),
                   **dict.fromkeys(module.WRAPPER_FALSE, False))
    pub = dict(schema='PROSPECTIVE_GAP_HISTORY_PUBLICATION_V3',
               status='PUBLISHED_GAP_EXTENSION_PENDING_INDEPENDENT_READBACK',
               history_reference=refs['reference'], started_reference=reference('started'),
               input_references=deepcopy(inputs), source_hashes=deepcopy(sources),
               **dict.fromkeys(module.WRAPPER_FALSE, False))
    audit_sources = deepcopy(sources)
    for ref in refs.values():
        module.merge(audit_sources, ref)
    module.merge(audit_sources, reference('producer'))
    audit = dict(schema='PROSPECTIVE_GAP_HISTORY_INDEPENDENT_READBACK_V3',
                 status='PURE_GAP_HISTORY_READBACK_PASS', history_reference=refs['reference'],
                 publication_reference=refs['publication_reference'],
                 reader_sha256=refs['reader_reference']['sha256'], input_references=deepcopy(inputs),
                 producer_reference=reference('producer'), source_hashes=audit_sources,
                 entire_history_independently_reconstructed=True, publisher_called=False,
                 new_pure_called=False, current_live_cache_read_or_reverified=False,
                 counts={key: h[key] for key in ('parent_typed_row_count', 'typed_row_count',
                      'observation_count', 'new_observation_count', 'new_missed_observation_count',
                      'last_observed_session', 'last_accounted_session',
                      'first_actual_observed_session_by_month')},
                 **dict.fromkeys(module.WRAPPER_FALSE, False))
    current = {ticker: raw + b''.join((d + ',10,12,8,10,100\n').encode() for d in new_dates)
               for ticker, raw in old['source_bytes'].items()}
    arguments = dict(parent=dict(document=wrapper, publication=pub, readback=audit, **refs),
        source_bytes=current, source_references={ticker: dict(path='new/' + ticker,
            sha256=sha256(raw).hexdigest()) for ticker, raw in current.items()},
        accounted_baseline_bytes=old['source_bytes'], actual_baseline_bytes=old['baseline_bytes'],
        capture_started_at=start, capture_completed_at=end or start,
        tzif_bytes=old['tzif_bytes'], tzif_reference=h['tzif_reference'])
    return arguments


def resign(arguments, ticker):
    arguments['source_references'][ticker]['sha256'] = sha256(arguments['source_bytes'][ticker]).hexdigest()


def replace_digest(value, old, new):
    if type(value) is dict:
        for key, item in value.items():
            if item == old:
                value[key] = new
            else:
                replace_digest(item, old, new)
    elif type(value) is list:
        for item in value:
            replace_digest(item, old, new)


class ForwardGapCaptureTests(unittest.TestCase):
    def test_no_new_preserves_full_v3(self):
        a = fixture(); before = deepcopy(a)
        p = module.plan_gap_parent_capture(**a)
        self.assertEqual(a, before)
        self.assertEqual(p['status'], 'NO_NEW_SESSION')
        self.assertEqual(p['known_typed_rows'], a['parent']['document']['history']['known_typed_rows'])
        self.assertEqual(p['last_observed_session'], '2026-10-02')
        self.assertEqual(p['last_accounted_session'], '2026-10-07')
        self.assertEqual(p['first_actual_observed_session_by_month']['2026-10'], '2026-10-02')
        self.assertNotEqual(p['baseline_references'], p['accounted_baseline_references'])
        self.assertTrue(all(p[key] is False for key in module.FLAGS))
        self.assertNotIn('original_csv_bytes_base64', str(p))

    def test_after_close_candidate_and_real_late_remain_facts(self):
        for start in ('2026-10-08T20:00:00+00:00', '2026-10-12T21:00:00+00:00'):
            p = module.plan_gap_parent_capture(**fixture(['2026-10-08'], start))
            self.assertEqual(p['status'], 'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
            self.assertEqual(p['candidate_session'], '2026-10-08')
            self.assertFalse(p['timeliness_verified'])

    def test_cross_close_and_reverse_clock(self):
        p = module.plan_gap_parent_capture(**fixture(['2026-10-08'],
            '2026-10-08T19:59:59+00:00', '2026-10-08T20:00:01+00:00'))
        self.assertEqual(p['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
        with self.assertRaises(ValueError):
            module.plan_gap_parent_capture(**fixture(start='2026-10-09T21:00:00+00:00', end='2026-10-09T20:00:00+00:00'))

    def test_multiple_asymmetric_revision(self):
        a = fixture(['2026-10-08', '2026-10-09'])
        self.assertIn(dict(reason='MULTIPLE_UNACCOUNTED_SESSIONS'), module.plan_gap_parent_capture(**a)['diagnostics'])
        a = fixture(['2026-10-08']); a['source_bytes']['SPY'] = a['accounted_baseline_bytes']['SPY']; resign(a, 'SPY')
        self.assertIn(dict(reason='ASYMMETRIC_NEW_SESSION_DATES'), module.plan_gap_parent_capture(**a)['diagnostics'])
        a = fixture(); a['source_bytes']['QQQ'] = a['source_bytes']['QQQ'].replace(b',10,', b',11,', 1); resign(a, 'QQQ')
        self.assertEqual(module.plan_gap_parent_capture(**a)['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')

    def test_pending_and_unfinished_rejected(self):
        for key in ('pending_source_sessions', 'excluded_not_completed_source_sessions'):
            a = fixture(); a['parent']['document']['history'][key] = [{'session': '2026-10-08'}]
            with self.assertRaisesRegex(ValueError, 'BASELINE_HAS_UNACCOUNTED_SUFFIX'):
                module.plan_gap_parent_capture(**a)

    def test_schema_authority_counts_month_anchor_inventory(self):
        changes = [lambda a: a['parent']['readback'].update(status='PASS'),
            lambda a: a['parent']['readback']['counts'].update(observation_count=True),
            lambda a: a['parent']['document'].update(future_independent_oos=0),
            lambda a: a['parent']['document']['history']['first_actual_observed_session_by_month'].update({'2026-10':'2026-10-05'}),
            lambda a: a['parent']['document']['history']['parent_attempt_inventory'].clear(),
            lambda a: a['parent']['readback'].update(reader_sha256='f'*64),
            lambda a: a['source_references']['QQQ'].update(sha256='f'*64)]
        for change in changes:
            a = fixture(); change(a)
            with self.assertRaises(ValueError): module.plan_gap_parent_capture(**a)

    def test_missing_or_duplicate_and_full_actual_byte_prefix(self):
        a = fixture(); a['source_bytes']['QQQ'] += a['source_bytes']['QQQ'].splitlines(keepends=True)[-1]; resign(a, 'QQQ')
        with self.assertRaises(ValueError): module.plan_gap_parent_capture(**a)

    def test_re_signed_actual_newline_and_same_count_wrong_baseline_scope(self):
        a = fixture(); old = sha256(a['actual_baseline_bytes']['QQQ']).hexdigest()
        a['actual_baseline_bytes']['QQQ'] = a['actual_baseline_bytes']['QQQ'].rstrip(b'\n') + b'\r\n'
        replace_digest(a['parent'], old, sha256(a['actual_baseline_bytes']['QQQ']).hexdigest())
        with self.assertRaisesRegex(ValueError, 'complete baseline prefix'):
            module.plan_gap_parent_capture(**a)
        a = fixture(); old = sha256(a['accounted_baseline_bytes']['QQQ']).hexdigest()
        a['accounted_baseline_bytes']['QQQ'] = a['accounted_baseline_bytes']['QQQ'].replace(b'2026-10-07', b'2026-10-08')
        replace_digest(a['parent'], old, sha256(a['accounted_baseline_bytes']['QQQ']).hexdigest())
        with self.assertRaisesRegex(ValueError, 'BASELINE_HAS_UNACCOUNTED_SUFFIX'):
            module.plan_gap_parent_capture(**a)

    def test_missing_source_claim_and_path_conflict(self):
        a = fixture(); h = a['parent']['document']['history']; ref = h['baseline_references']['QQQ']
        del a['parent']['document']['source_hashes'][ref['path']]
        del a['parent']['publication']['source_hashes'][ref['path']]
        with self.assertRaises(ValueError): module.plan_gap_parent_capture(**a)
        a = fixture(['2026-10-08'])
        a['source_references']['QQQ']['path'] = a['parent']['reference']['path']
        with self.assertRaisesRegex(ValueError, 'Conflicting source path'):
            module.plan_gap_parent_capture(**a)
        a = fixture(); a['actual_baseline_bytes']['QQQ'] = a['actual_baseline_bytes']['QQQ'].rstrip(b'\n') + b'\r\n'
        ref = a['parent']['document']['history']['baseline_references']['QQQ']
        # A raw hash lie must fail even when interpreted rows remain identical.
        with self.assertRaises(ValueError): module.plan_gap_parent_capture(**a)


if __name__ == '__main__':
    unittest.main()
