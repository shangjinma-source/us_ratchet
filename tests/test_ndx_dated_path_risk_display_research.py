from copy import deepcopy
from datetime import date, timedelta
import unittest
from backtest import ndx_dated_path_risk_display_research as core


def fixture(*, first=False, task_id=None, missing=False):
    tid = task_id or (core.FIRST if first else '2' * 64)
    start = date(2026, 3, 20)
    days = [(start + timedelta(days=i)).isoformat() for i in range(180) if (start + timedelta(days=i)).weekday() < 5]
    calendar = days[:126] + ['2026-09-21']
    def ref(name, pointer=None):
        out = dict(path=name, sha256='a' * 64)
        if pointer is not None:
            out['json_pointer'] = pointer
        return out
    values = ['1'] * 127
    metrics = dict(normalized_values_exact=values, maximum_drawdown={'exact': '0'})
    tracks, preserved, roles = {}, {}, {}
    for role in ('candidate', 'incumbent'):
        positions = [dict(security_id=role + str(i), ticker='T' + str(i), issuer_id='I' + str(i), target_weight=float(i)) for i in range(2)]
        sids = [p['security_id'] for p in positions]
        labels = {sids[0]: None, sids[1]: 'conditional_chain'}
        account = dict(daily=[dict(session=d, shares={}, cash_usd=25000.0, total_value_usd=25000.0,
            risk={'checks': {'ALL_CASH': False}, 'all_passed': False}, risk_chains={}, risk_chain_observation_dates={}) for d in calendar],
            decisions=[{'status': 'NO_PLAN'}], executions=[])
        continuous = dict(positions_preserved=positions, path=[dict(session=d, normalized_value={'numerator': '1', 'denominator': '1'},
            security_rows=[{'security_id': sid, 'contribution_after_cost': {'numerator': '0', 'denominator': '1'}} for sid in sids]) for d in calendar])
        preserved[role] = dict(integer_account=account, continuous_track=continuous)
        roles[role] = dict(risk_chains_by_decision={calendar[0]: labels}, original_ticker_by_security={p['security_id']:p['ticker'] for p in positions}, schedule=[{'targets': deepcopy(positions)}])
        for kind, original in (('integer', account), ('continuous', continuous)):
            name = role + '_' + kind
            base = '/account' if kind == 'integer' else '/tracks/' + role
            source = ref(role + '-account' if kind == 'integer' else 'shared-continuous', None if first else base)
            track = dict(status='AVAILABLE', source_reference=source, stored_values_exact=['25000'] * 127 if kind == 'integer' else values,
                metrics=deepcopy(metrics), value_encoding='first wording' if first else 'new wording')
            if first:
                track['path_pointer'] = base + ('/daily' if kind == 'integer' else '/path')
            else:
                track['original_account_preserved' if kind == 'integer' else 'original_track_preserved'] = original
            tracks[name] = track
    if missing:
        tracks['candidate_integer'] = dict(status='NOT_EXECUTED_NONPOSITIVE_TARGET', metrics=None, stored_values_exact=None,
            source_reference=None, original_account_preserved=None, missing_evidence={'reason': 'Original zero slot'})
    modes = {}
    for mode in core.MODES:
        original = dict(observations=[dict(session=d, normalized_value_exact='1', original_alignment_row={'publication': None}) for d in calendar])
        modes[mode] = dict(metrics=deepcopy(metrics), source_reference=ref('nav', None if first else '/metrics'))
        modes[mode]['original_mode' if first else 'original_mode_preserved'] = original
        if first:
            modes[mode]['path_pointer'] = '/metrics/modes/' + mode
    flags = dict.fromkeys(core.AUTHORITY, False)
    comparison = dict(schema='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1' if first else 'DATED_PER_TASK_PARTIAL_ECONOMIC_DIAGNOSTIC_V1',
        calendar=calendar, tracks=tracks, nav_modes=modes, mode_order=list(core.MODES), modes_retained_separately=True,
        saved_paths_preserved=preserved, evaluation_interval_previously_used_for_fitting=True, **flags)
    document_ref = ref(tid + '-comparison')
    inputs_ref = ref(tid + '-inputs')
    return dict(task_id=tid, document=dict(schema='SOURCE_BOUND_DATED_FIRST_ECONOMIC_COMPARISON_V1' if first else 'SOURCE_BOUND_DATED_PER_TASK_ECONOMIC_COMPARISON_V1', numerical_task_id=tid, comparison=comparison, **flags),
        document_reference=document_ref, audit_reference=ref(tid + '-audit'),
        audit=dict(schema='DATED_COMPARISON_INDEPENDENT_READBACK_V1' if first else 'DATED_PER_TASK_COMPARISON_INDEPENDENT_READBACK_V1', status='PASS', numerical_task_id=tid, comparison_reference=deepcopy(document_ref), **flags),
        inputs_document=dict(schema='DATED_ACCOUNT_INPUT_DOCUMENT_V1', inputs=dict(original_task={'numerical_task_id':tid}, calendar=deepcopy(calendar), candidate_engine_normalization_evidence={'original_zero_kept': True}, limitations=['LATE_RISK'],
            original_fit_result={'targets': {p['security_id']: {k:p[k] for k in ('ticker','issuer_id','target_weight')} for p in preserved['candidate']['continuous_track']['positions_preserved']}},
            original_incumbent_definition=deepcopy(preserved['incumbent']['continuous_track']['positions_preserved']), **roles), original_provenance_and_missing=[{'gap':'UNVERIFIED'}], preserved_evidence_sidecars={'all7':'preserved'}, **flags),
        inputs_reference=inputs_ref, input_audit=dict(schema='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1', status='PASS', inputs_reference=deepcopy(inputs_ref)), input_audit_reference=ref(tid + '-input-audit'))


class Tests(unittest.TestCase):
    def test_first_and_new_exact_copy_shared_identity_and_no_mutation(self):
        a, b = fixture(first=True), fixture()
        before = deepcopy((a, b))
        first, new = core.project_saved_comparison(**a), core.project_saved_comparison(**b)
        result = core.collect_projections([first, new])
        self.assertEqual(len(result['shared_paths']), 4)
        self.assertEqual(result['task_count'], 2)
        self.assertEqual(first['tracks']['candidate_integer']['path'], a['document']['comparison']['saved_paths_preserved']['candidate']['integer_account']['daily'])
        self.assertEqual((a, b), before)
        self.assertEqual(first['target_evidence']['candidate']['rows'][0]['original_position']['target_weight'], 0.0)
        self.assertEqual(first['target_evidence']['candidate']['rows'][0]['risk_chain_status'], 'UNKNOWN')
        first['target_evidence']['candidate']['rows'][0]['original_position']['ticker'] = 'mutated'
        self.assertEqual((a, b), before)

    def test_missing_integer_distinct_from_real_no_plan_cash(self):
        full = core.project_saved_comparison(**fixture())
        missing = core.project_saved_comparison(**fixture(missing=True))
        self.assertEqual(full['tracks']['candidate_integer']['decisions'], [{'status':'NO_PLAN'}])
        self.assertEqual(full['tracks']['candidate_integer']['risk_rows'][0]['stock_denominator_status'], 'NO_POSITIVE_STOCK')
        self.assertIsNone(missing['tracks']['candidate_integer']['path'])
        self.assertEqual(len(missing['tracks']['candidate_integer']['calendar_slots']), 127)
        self.assertTrue(all(r['value'] is None for r in missing['tracks']['candidate_integer']['calendar_slots']))

    def test_saved_integer_risk_and_dates_copied_without_reclassification(self):
        args = fixture()
        day = args['document']['comparison']['tracks']['candidate_integer']['original_account_preserved']['daily'][1]
        day.update(shares={'candidate1':3}, risk={'actual_weights':{'candidate1':1.0}, 'checks':{'MAX_SINGLE_WEIGHT':False}, 'risk_chain_top1_weight':1.0},
            risk_chains={'candidate1':'conditional_chain'}, risk_chain_observation_dates={'candidate1':'2026-03-20'})
        out = core.project_saved_comparison(**args)
        projected = out['tracks']['candidate_integer']['risk_rows'][1]
        self.assertEqual(projected['saved_risk'], day['risk'])
        self.assertEqual(projected['security_exposures'][0]['ticker'], 'T1')
        self.assertFalse(out['risk_recomputed'])

    def test_missing_dates_false_authority_source_conflicts_and_shared_tamper(self):
        for mode in ('date', 'flag', 'ticker', 'reference'):
            args = fixture()
            if mode == 'date': args['document']['comparison']['tracks']['candidate_continuous']['original_track_preserved']['path'].pop()
            elif mode == 'flag': args['audit']['point_in_time_verified'] = 0
            elif mode == 'ticker': args['inputs_document']['inputs']['candidate']['original_ticker_by_security']['candidate1'] = 'ENGINE_ALIAS'
            else: args['input_audit']['inputs_reference']['sha256'] = 'f' * 64
            with self.subTest(mode=mode), self.assertRaises(ValueError): core.project_saved_comparison(**args)
        first = core.project_saved_comparison(**fixture(first=True))
        second = core.project_saved_comparison(**fixture())
        second['tracks']['incumbent_integer']['path'][1]['cash_usd'] = 1
        with self.assertRaises(ValueError): core.collect_projections([first, second])
        with self.assertRaises(ValueError): core.collect_projections([first, first])


if __name__ == '__main__':
    unittest.main()
