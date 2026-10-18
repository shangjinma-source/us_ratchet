"""Synthetic independent mapping coverage and re-signed display attacks."""
from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch
import json
from pathlib import Path
import subprocess
import unittest
from backtest import ndx_multidecision_h_workbook_display_v2_research as producer
from backtest import ndx_multidecision_h_workbook_display_inspection_v2_research as checker
from scripts import ndx_multidecision_h_workbook_inspection_v2_20261008 as cells


def fixture():
    calendar = [(date(2026, 1, 1) + timedelta(days=n)).isoformat() for n in range(120)]
    references = {k: dict(path=k, sha256='a' * 64) for k in ('presentation', 'supplement', 'diagnostics', 'chain')}
    inputref = dict(path='inputs', sha256='b' * 64)
    ratio = dict(numerator='1', denominator='1')
    metrics, curves, holdings, paths, diagnostic_paths = [], [], [], [], []
    bundles = {'candidate': [None] * 16, 'control': [None] * 16}
    for index in range(16):
        mode = ('严格', '向前')[index // 8];lane = ('收益', '尾部', '回撤', '目标')[(index % 8) // 2];track = ('连续', '整股')[index % 2]
        for label, role in (('候选', 'candidate'), ('原八只控制', 'control')):
            blocked = role == 'candidate' and index < 8
            status = 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT' if blocked else 'SAVED_PATH_DIAGNOSTIC'
            metrics.append([index, mode, lane, track, label, status, None if blocked else '1/10', None if blocked else '0.3333333333333333', None if blocked else '1/20'])
            if blocked: continue
            curves.extend([[index, mode, lane, track, label, session, str(120 + n) + '/120'] for n, session in enumerate(calendar)])
            raw_day = dict(session=calendar[-1], risk=dict(actual_weights={'sid': .7}, effective_n=1))
            if index % 2: raw_day['shares'] = {'sid': 7}
            else: raw_day['holdings'] = {'sid': {'shares': 7.0}}
            bundles[role][index] = dict(document=dict(result=dict(daily=[raw_day])))
            holdings.append([role, index, mode, lane, track, calendar[-1], 'sid', 'REAL.X', 'issuer', 'INTERNAL', '7', 'identity', 'raw'])
    for mode in ('严格', '向前'):
        curves.extend([[None, mode, None, None, '012922参考', session, '1/1'] for session in calendar])
    for role in ('candidate', 'control'):
        for index in range(16):
            blocked = role == 'candidate' and index < 8
            basis = 'DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION' if index % 2 else ('ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS' if role == 'control' else 'PREVIOUSLY_AUDITED_CANDIDATE_CONTINUOUS_DERIVED_CHAIN_WEIGHTS')
            paths.append(dict(role=role, track_index=index, rows=None if blocked else [dict(session=calendar[-1], basis=basis, chain_weights={'chain': ratio})]))
    for index in (8, 10, 12, 14):
        rows = []
        for n, session in enumerate(calendar):
            values = dict.fromkeys(('hhi', 'effective_n', 'top1_weight', 'top3_weight', 'minimum_single_weight', 'risk_chain_top1_weight'), ratio)
            diagnostic = dict(session=session, status='DERIVED', security_weights={'sid': ratio}, metrics=values,
                              chain_weights={'chain': ratio}, label_observations={'sid': dict(label='chain', observation_session=calendar[0])})
            rows.append(dict(daily_index=n, diagnostic=diagnostic, source_locator_tokens={'sid': ['original', n]}))
        diagnostic_paths.append(dict(track_index=index, coordinate=['FX', 'LANE', 'CONTINUOUS'], projection=dict(rows=rows)))
    def table(name, rows=None):
        width = len(rows[0]) if rows else 1
        return dict(name=name, headers=['证据' + str(i) for i in range(width)], rows=[] if rows is None else rows)
    original = [table('表' + str(i)) for i in range(11)]
    original[1] = table('已存路径指标', metrics);original[5] = table('已存归一轨迹', curves)
    saved = [table('原表' + str(i)) for i in range(6)];saved[3] = table('每日SID原持仓', holdings)
    body = dict(point_in_time_verified=False, promotion_allowed=False)
    presentation = dict(schema='MULTIDECISION_PATH_PRESENTATION_DOCUMENT_V1', input_references=dict(candidate_inputs=inputref), presentation=dict(**body, tables=original))
    supplement = dict(schema='MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1', supplement=dict(**body, tables=saved, calendar=calendar, references=dict(candidate_inputs=inputref), original_raw_bundles_preserved=bundles))
    diagnostics = dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1', **body, input_references=dict(inputs=inputref), paths=diagnostic_paths)
    chain = dict(schema='MULTIDECISION_DAILY_CHAIN_DOCUMENT_V1', projection=dict(**body, calendar=calendar, paths=paths,
                 references={k: references[k] for k in ('supplement', 'diagnostics')}, tables=[table('链' + str(i)) for i in range(3)] + [table('未执行阻断轨道')]))
    return dict(presentation_document=presentation, supplement_document=supplement, diagnostics_document=diagnostics, chain_document=chain, references=references)


class Tests(unittest.TestCase):
    def test_independent_complete_mapping_without_producer_calls(self):
        args = fixture();display = producer.build_display(**args)
        with patch.object(producer, 'build_display', side_effect=AssertionError('Producer forbidden')), \
             patch.object(producer, 'approximate', side_effect=AssertionError('Producer numeric helper forbidden')):
            result = checker.inspect_display(display=display, **args)
        self.assertEqual((result['table_count'], result['chart_count'], result['original_curve_row_count']), (25, 16, 3120))
        self.assertEqual(result['final_sid_row_count'], 24)
        self.assertEqual([len(x['series']) for x in checker.chart_expectations(display)], [2] * 8 + [3] * 8)

    def test_all_view_and_curve_mutations_are_rejected(self):
        args = fixture();display = producer.build_display(**args)
        changes = [lambda d: d['tables'][0]['rows'][0].__setitem__(6, '0%'),
                   lambda d: d['tables'][0]['rows'][-1].__setitem__(12, '原值'),
                   lambda d: d['tables'][1]['rows'][-1].__setitem__(6, 'INTERNAL'),
                   lambda d: d['tables'][1]['rows'][-1].__setitem__(9, '1'),
                   lambda d: d['charts'][0]['rows'][0].append(0),
                   lambda d: d['charts'][-1]['rows'][-1].__setitem__(-1, 0.0),
                   lambda d: d['charts'][-1]['rows'].pop(),
                   lambda d: d['charts'][-1]['source_series_keys'][0].__setitem__(4, '原八只控制'),
                   lambda d: d['tables'][-1]['rows'].pop(),
                   lambda d: d['tables'][7]['rows'].pop(),
                   lambda d: d['references']['chain'].update(sha256='f' * 64),
                   lambda d: d.update(financial_recomputation_performed=True)]
        for i, change in enumerate(changes):
            with self.subTest(attack=i):
                altered = deepcopy(display);change(altered)
                with self.assertRaises(ValueError): checker.inspect_display(display=altered, **args)

    def test_all_43_sheet_layouts_and_long_unicode_match_without_export(self):
        args = fixture();display = producer.build_display(**args)
        display['tables'][2] = dict(name='精确长文本', headers=['原JSON', '文字'], rows=[['甲🙂' * 1113265, '=literal']])
        builder = Path('scripts/ndx_multidecision_h_workbook_v2_20261008.mjs').resolve()
        node = Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
        script = ('import {sheets,subtitle} from ' + json.dumps(builder.as_uri()) + ';'
                  'let raw="";for await(const part of process.stdin)raw+=part;'
                  'process.stdout.write(JSON.stringify(sheets(JSON.parse(raw)).map(t=>[t.name,t.chart?t.note:subtitle,t.headers,t.rows])));')
        result = subprocess.run([str(node), '--input-type=module', '-e', script], input=json.dumps(display).encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        expected = cells.expected_sheets(display)
        self.assertEqual(json.loads(result.stdout), [list(row) for row in expected])
        self.assertEqual(len(expected), 43)
        self.assertEqual(''.join(row[-1] for row in expected[-1][3]), display['tables'][2]['rows'][0][0])

    def test_actual_k_counts_only_positive_original_quantities(self):
        args = fixture()
        bundles = args['supplement_document']['supplement']['original_raw_bundles_preserved']
        bundles['control'][0]['document']['result']['daily'][-1]['holdings'] = {'sid': {'shares': 1.0}, 'zero': {'shares': 0.0}, 'second': {'shares': .5}}
        bundles['control'][1]['document']['result']['daily'][-1]['shares'] = {'zero': 0}
        display = producer.build_display(**args)
        self.assertEqual(display['tables'][0]['rows'][1][6], 2)
        self.assertEqual(display['tables'][0]['rows'][3][6], 0)
        self.assertIsNone(display['tables'][0]['rows'][0][6])
        checker.inspect_display(display=display, **args)
        for row, wrong in ((0, 0), (1, 1), (3, 1), (1, True)):
            with self.subTest(row=row, wrong=wrong):
                changed = deepcopy(display);changed['tables'][0]['rows'][row][6] = wrong
                with self.assertRaises(ValueError): checker.inspect_display(display=changed, **args)


if __name__ == '__main__': unittest.main()
