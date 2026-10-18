import copy
import unittest
from backtest import ndx_observation_gap_ledger_research as module


def ref(name):
    return {'path': name, 'sha256': module.digest(name)}


def fixture(session='2026-09-25', capture='2026-10-02T14:26:00+00:00'):
    parent = {'manifest_reference': ref('manifest'), 'event_prefix_reference': ref('events'),
        'session_projection_reference': ref('sessions'), 'event_count': 66, 'session_count': 60,
        'last_session': '2026-09-24', 'event_tail_sha256': 'a'*64}
    row = {'session': session, 'recorded_at_utc': capture,
        'conservative_close_utc': session+'T20:00:00+00:00',
        'conservative_seal_deadline_utc': '2026-10-02T13:30:00+00:00',
        'classification': 'LATEST_ROW_SEAL_DEADLINE_MISSED', 'decision_eligible': False,
        'first_observed_at_historical_close_claimed': False}
    classified = {'schema': 'OBSERVATION_GAP_RECOVERY_CLASSIFICATION_V1',
        'last_sealed_session': parent['last_session'], 'observed_at_utc': capture,
        'timeliness_candidate': None, 'pending_classifications': [row],
        'missed_or_ineligible_row_count': 1,
        **{key: False for key in ('canonical_calendar_append_allowed', 'candidate_seal_allowed',
        'cohort_registration_allowed', 'retrospective_backfill_allowed', 'point_in_time_verified', 'promotion_allowed')}}
    document = {'schema': 'CURRENT_SOURCE_GAP_CLASSIFICATION_CAPTURE_V1',
        'captured_at_utc': capture, 'classification': classified,
        'parent_references': {'calendar_manifest': parent['manifest_reference'], 'calendar_events': parent['event_prefix_reference']},
        'captured_source_references': {ticker: ref(ticker+session) for ticker in ('QQQ', 'SPY')},
        'pending_source_rows': {ticker: {session: {'Date': session, 'Close': '1'}} for ticker in ('QQQ', 'SPY')},
        **{key: False for key in ('old_calendar_mutated', 'calendar_append_allowed', 'candidate_seal_allowed',
                                 'cohort_registration_allowed', 'promotion_allowed', 'live_mutation_allowed')}}
    return dict(parent_binding=parent, classification_capture=document,
                classification_reference=ref('classification'+session), recorded_at_utc='2026-10-03T00:00:00+00:00')


class LedgerTests(unittest.TestCase):
    def test_chain_append_preserves_prefix_and_permissions(self):
        args = fixture(); original = copy.deepcopy(args)
        first = module.append_missed_observations(**args)
        self.assertEqual(args, original)
        self.assertEqual(first['events'][0]['event_sequence'], 67)
        self.assertEqual(first['events'][0]['previous_event_sha256'], 'a'*64)
        next_args = fixture('2026-09-28'); next_args['existing_ledger'] = first
        second = module.append_missed_observations(**next_args)
        self.assertEqual(second['events'][:1], first['events'])
        self.assertEqual(second['events'][1]['previous_event_sha256'], first['terminal_event_sha256'])
        self.assertEqual(second['old_last_observed_session_unchanged'], '2026-09-24')
        for key in ('observed_session_increment', 'fresh_session_increment', 'seal_increment', 'cohort_increment'):
            self.assertEqual(second[key], 0)
        self.assertTrue(module.validate_gap_ledger(ledger=second, parent_binding=args['parent_binding']))

    def test_duplicate_and_parent_drift(self):
        args = fixture(); ledger = module.append_missed_observations(**args)
        with self.assertRaises(ValueError): module.append_missed_observations(**args, existing_ledger=ledger)
        args['parent_binding']['event_tail_sha256'] = 'b'*64
        with self.assertRaises(ValueError): module.append_missed_observations(**args, existing_ledger=ledger)

    def test_hash_resigning_cannot_grant_permission(self):
        args = fixture(); ledger = module.append_missed_observations(**args)
        ledger['events'][0]['fresh_observation'] = True
        event = ledger['events'][0]; event.pop('event_sha256'); event['event_sha256'] = module.digest(event)
        ledger.pop('ledger_sha256'); ledger['ledger_sha256'] = module.digest(ledger)
        with self.assertRaises(ValueError): module.validate_gap_ledger(ledger=ledger, parent_binding=args['parent_binding'])

    def test_false_timeliness_clock_and_types(self):
        for mutation in (
            lambda a: a.update(recorded_at_utc='2026-10-01T00:00:00+00:00'),
            lambda a: a['parent_binding'].update(event_count=True),
            lambda a: a['classification_capture']['classification'].update(timeliness_candidate={}),
            lambda a: a['classification_capture']['classification']['pending_classifications'][0].update(decision_eligible=0),
            lambda a: a['classification_capture']['classification']['pending_classifications'][0].update(conservative_seal_deadline_utc='2026-10-03T13:30:00+00:00'),
        ):
            args = fixture(); mutation(args)
            with self.assertRaises(ValueError): module.append_missed_observations(**args)

    def test_raw_date_and_capture_time_contradictions(self):
        args = fixture(); args['classification_capture']['pending_source_rows']['QQQ']['2026-09-25']['Date']='2026-09-24'
        with self.assertRaises(ValueError): module.append_missed_observations(**args)

    def test_capture_cannot_move_backwards(self):
        first = module.append_missed_observations(**fixture())
        args = fixture('2026-09-28', '2026-10-02T14:25:00+00:00')
        with self.assertRaisesRegex(ValueError, 'backwards'):
            module.append_missed_observations(**args, existing_ledger=first)

    def test_bool_integer_substitutions_rejected_even_resigned(self):
        args = fixture()
        for key, value in [('fresh_observation', 0), ('observed_session_increment', False)]:
            for resign in (False, True):
                ledger = module.append_missed_observations(**args)
                ledger[key] = value
                if resign:
                    ledger.pop('ledger_sha256')
                    ledger['ledger_sha256'] = module.digest(ledger)
                with self.assertRaises(ValueError):
                    module.validate_gap_ledger(ledger=ledger, parent_binding=args['parent_binding'])
        args=fixture(); args['classification_capture']['classification']['observed_at_utc']='2026-10-02T14:27:00+00:00'
        with self.assertRaises(ValueError): module.append_missed_observations(**args)


if __name__ == '__main__': unittest.main()
