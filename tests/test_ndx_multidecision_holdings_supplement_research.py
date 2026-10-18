"""Full-domain synthetic saved records; no financial engines or real points."""
from copy import deepcopy
from datetime import date, timedelta
import unittest
from backtest import ndx_multidecision_holdings_supplement_research as module


def fixture():
    refs = {key: dict(path=key, sha256='a' * 64) for key in ('candidate_inputs', 'control_inputs', 'candidate_execution', 'control_execution')}
    calendar = [(date(2026, 1, 1) + timedelta(days=n)).isoformat() for n in range(120)]
    control = [dict(security_id=f'control-{i}', ticker=f'REAL{i}', issuer_id=f'issuer-{i}', target_weight=0.125, risk_chain=f'chain{i}') for i in range(8)]
    documents = {}; raw_documents = {}
    for role in ('candidate', 'control'):
        input_rows = []; execution_rows = []; bundles = []
        for lane_index in range(8):
            mode, lane = module.MODES[lane_index // 4], module.LANES[lane_index % 4]
            identities = control if role == 'control' else [dict(security_id='candidate-1', ticker='REALC', issuer_id='issuer-c')]
            targets = {item['security_id']: dict(ticker=f'INTERNAL_{n}', issuer_id=item['issuer_id'], target_weight=item.get('target_weight', 1.0)) for n, item in enumerate(identities)}
            schedule = [dict(decision_date=calendar[n], execution_date=calendar[n + 1], targets=deepcopy(targets)) for n in range(0, 120, 20)]
            tracks = []
            for offset, kind in enumerate(module.TRACKS):
                index = lane_index * 2 + offset
                blocked = role == 'candidate' and lane_index < 4
                reasons = [{'reason': 'SAVED_SOURCE_BLOCKED'}] if blocked else []
                tracks.append(dict(track=kind, blocking_reasons=reasons, engine_binding=dict(keyword_arguments=dict(schedule=deepcopy(schedule), closes=dict(index=calendar)))))
                start = dict(path=f'{role}-{index}-started', sha256='b' * 64)
                rawref = dict(path=f'{role}-{index}-raw', sha256='c' * 64)
                row = dict(track_index=index, fx_mode=mode, lane=lane, track=kind, blocking_reasons=reasons,
                    outcome='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT' if blocked else 'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK',
                    raw_reference=None if blocked else rawref, call_invoked=not blocked, started_reference=start)
                execution_rows.append(row)
                if blocked:
                    bundles.append(None);continue
                daily = []
                for n, session in enumerate(calendar):
                    day = dict(session=session)
                    if kind == 'CONTINUOUS':
                        day['holdings'] = {} if n == 0 else {sid: dict(shares=1.25, ticker=t['ticker'], issuer_id=t['issuer_id']) for sid, t in targets.items()}
                    else:
                        day.update(shares={} if n == 0 else dict.fromkeys(targets, 2), tickers={} if n == 0 else {sid: t['ticker'] for sid, t in targets.items()}, risk_chains={'original': 'chain'}, risk_chain_observation_dates={'original': calendar[0]})
                    if role == 'control' or kind == 'WHOLE_LOT': day['risk'] = {'all_passed': False, 'original_marker': f'{role}/{index}/{n}'}
                    daily.append(day)
                raw = dict(schema='MULTIDECISION_ACCOUNT_RAW_RETURN_V1' if role == 'candidate' else 'MULTIDECISION_INCUMBENT_ACCOUNT_RAW_RETURN_V1', returned=True, call_invoked=True, error=None,
                    input_references=dict(inputs=refs[role + '_inputs']), started_reference=start, result=dict(daily=daily), point_in_time_verified=False, promotion_allowed=False)
                bundles.append(dict(reference=rawref, document=raw))
            original_schedule = deepcopy(schedule)
            for entry in original_schedule:
                for item in identities: entry['targets'][item['security_id']]['ticker'] = item['ticker']
            input_rows.append(dict(fx_mode=mode, lane=lane, coordinate_indexes=list(range(lane_index, 48, 8)), tracks=tracks, source_slots=[dict(coordinate_preserved=i) for i in identities], original_targets_schedule=original_schedule))
        body = dict(coordinate_count=48, lane_count=8, track_count=16, rows=input_rows)
        if role == 'control': body['original_control_preserved'] = dict(complete_original_definition=dict(securities=control))
        documents[role + '_inputs'] = dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1' if role == 'candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1', inputs=body, point_in_time_verified=False, promotion_allowed=False)
        documents[role + '_execution'] = dict(schema='MULTIDECISION_ACCOUNT_EXECUTION_RESULT_V1' if role == 'candidate' else 'MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_RESULT_V1',
            status='ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK', failure=None, input_references=dict(inputs=refs[role + '_inputs']), rows=execution_rows, point_in_time_verified=False, promotion_allowed=False)
        raw_documents[role] = bundles
    return dict(**documents, references=refs, raw_documents=raw_documents)


class Tests(unittest.TestCase):
    def test_complete_saved_projection_no_mutation_or_risk_inference(self):
        args = fixture(); before = module.text(args)
        value = module.build_supplement(**args)
        self.assertEqual(module.text(args), before)
        self.assertEqual(value['counts'], dict(returned_paths=24, blocked_paths=8, daily_rows=2880, saved_risk_rows=2400, missing_risk_rows=480))
        tables = {t['name']: t for t in value['tables']}
        self.assertEqual(len(tables['控制原目标']['rows']), 384)
        self.assertEqual(len(tables['未执行阻断轨道']['rows']), 8)
        risk = tables['每日原风险与缺口']['rows']
        self.assertEqual(sum(row[7] is None for row in risk), 480)
        self.assertEqual(value['original_raw_bundles_preserved'], args['raw_documents'])
        self.assertTrue(all(not value[key] for key in module.FALSE))
        self.assertTrue(all(row[7] != row[9] for row in tables['每日SID原持仓']['rows'] if row[6] is not None))

    def test_truncation_identity_alias_and_blocked_laundering_rejected(self):
        for attack in ('day', 'sid', 'alias', 'rawref', 'blocked', 'risk', 'target', 'boolindex', 'realidentity'):
            with self.subTest(attack=attack):
                args = fixture()
                raw = args['raw_documents']['candidate'][8]['document']
                if attack == 'day': raw['result']['daily'].pop()
                elif attack == 'sid': raw['result']['daily'][1]['holdings']['unknown'] = dict(shares=1, ticker='X', issuer_id='X')
                elif attack == 'alias': raw['result']['daily'][1]['holdings']['candidate-1']['ticker'] = 'FAKE'
                elif attack == 'rawref': args['raw_documents']['candidate'][8]['reference'] = dict(raw['started_reference'], sha256='e' * 64)
                elif attack == 'blocked': args['raw_documents']['candidate'][0] = deepcopy(args['raw_documents']['candidate'][8])
                elif attack == 'risk': del args['raw_documents']['control'][0]['document']['result']['daily'][1]['risk']
                elif attack == 'target': args['control_inputs']['inputs']['rows'][0]['tracks'][0]['engine_binding']['keyword_arguments']['schedule'][0]['targets']['control-0']['target_weight'] = 0.5
                elif attack == 'boolindex': args['control_execution']['rows'][0]['track_index'] = False
                else: args['candidate_inputs']['inputs']['rows'][4]['original_targets_schedule'][0]['targets']['candidate-1']['ticker'] = 'WRONG_REAL'
                with self.assertRaises(ValueError): module.build_supplement(**args)


if __name__ == '__main__':
    unittest.main()
