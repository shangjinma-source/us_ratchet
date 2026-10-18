"""Independent reader tests; no execution engine or production-account build."""
import copy
from decimal import Decimal, Context, Inexact, getcontext, localcontext, setcontext
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_return_six_period_account_comparison_20260923 as reader


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path, _ = reader.BOUND['benchmark']
        cls.benchmark = json.loads((reader.BASE / path).read_bytes())

    def test_actual_benchmark_uses_nav_not_rounded_equity_index(self):
        benchmark = copy.deepcopy(self.benchmark)
        for row in benchmark['nav']['rows']:
            row['equity_index'] = '99999'
        measures = reader.metrics([25000] * 107)
        result = reader.compare(benchmark, benchmark['calendar'], measures)
        self.assertEqual(result['references']['012922_native_currency_nav'], benchmark['nav']['metrics'])
        self.assertLess(Decimal(result['candidate_minus_reference']['original_incumbent']['path_return']), 0)

    def test_metric_context_denominator_and_boolean_rejection(self):
        old = getcontext().copy()
        try:
            getcontext().prec = 3
            getcontext().traps[Inexact] = True
            actual = reader.metrics(['100', '200', '50'] + ['100'] * 104)
            self.assertEqual(actual['path_max_drawdown'], '0.75')
            self.assertEqual(actual['return_interval_count'], 106)
        finally:
            setcontext(old)
        for values in ([1] * 106, [1] * 106 + [True], [1] * 106 + ['NaN']):
            with self.assertRaises(ValueError): reader.metrics(values)

    def test_future_nav_and_permission_and_changed_metric_rejected(self):
        for change in ('future', 'promotion', 'metric', 'clock'):
            benchmark = copy.deepcopy(self.benchmark)
            if change == 'future': benchmark['nav']['rows'][0]['nav_date'] = '2024-01-01'
            if change == 'promotion': benchmark['promotion_allowed'] = True
            if change == 'metric': benchmark['nav']['metrics']['path_return'] = '0'
            if change == 'clock': benchmark['decision_clock'][-1][1] = '2023-09-05'
            with self.subTest(change=change), self.assertRaises(ValueError):
                reader.compare(benchmark, benchmark['calendar'], reader.metrics([1] * 107))

    def test_full_sell_buy_class_transition_and_missing_leg(self):
        old, new = 'security:0001652044:02079K107', 'security:0001652044:02079K305'
        execution = dict(executions=[dict(session='2023-09-01', status='FILLED',
            shares_before={old: 30}, shares_after={new: 25})], trades=[
            dict(session='2023-09-01', security_id=old, share_delta=-30, transaction_cost_usd='3'),
            dict(session='2023-09-01', security_id=new, share_delta=25, transaction_cost_usd='2.5')])
        self.assertEqual(reader.share_class_transition(execution)['separate_trade_count'], 2)
        execution['trades'].pop()
        with self.assertRaises(ValueError): reader.share_class_transition(execution)

    def test_rejected_transition_keeps_class_c_and_no_fictional_conversion(self):
        old = 'security:0001652044:02079K107'
        execution = dict(executions=[dict(session='2023-09-01', status='REJECTED',
            shares_before={old: 30}, shares_after={old: 30})], trades=[])
        value = reader.share_class_transition(execution)
        self.assertFalse(value['class_conversion_inferred'])
        execution['executions'][0]['shares_after'] = {}
        with self.assertRaises(ValueError): reader.share_class_transition(execution)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError): json.loads('{"value":1,"value":2}', object_pairs_hook=reader.unique)

    def test_self_signed_candidate_rejected_before_any_read(self):
        with self.assertRaises(ValueError):
            reader.build(reader.ACCOUNT_DIRECTORY / 'account.json', '0' * 64, reader.PRODUCER_SHA)

    def raw_fixture(self):
        sid = 'security:0001652044:02079K305'
        column = 'SID_' + sid.split(':')[1] + '_' + sid.split(':')[2]
        labels = {'rows': [dict(security_id=sid, ticker='GOOGL')]}
        flags = dict.fromkeys(reader.CANDIDATE_FALSE, False)
        common = dict(source_hashes={'fixed': 'hash'}, runtime={'fixed': 'runtime'}, **flags)
        inputs = dict(calendar=['2023-09-01'], schedule=[], internal_columns={sid: column},
                      execution_contract=reader.CONTRACT, normalization_evidence=[], price_conversion_evidence={},
                      engine_input_validation=dict(frozen_price_index_validators_called=True,
                        frozen_schedule_and_contract_validators_called=True, normalized_copy_discarded=True,
                        submitted_schedule_modified=False, simulate_called=False, session_count=107,
                        security_column_count=8, decision_count=6),
                      historical_v1_engine_attempt_count=1, historical_v1_complete_ledger_count=0)
        started_ref = dict(path='fixture_started', sha256='fixture_sha')
        started = dict(schema=reader.SCHEMA + '_STARTED', automatic_retry_allowed=False,
                       input_references={r: reader.reference(r) for r in reader.INPUT_ROLES}, **inputs, **common)
        execution = dict(decisions=[dict(targets={sid: dict(ticker=column, weight=.25)})],
                         trades=[dict(security_id=sid, ticker=column, share_delta=2)],
                         daily=[dict(shares={sid: 2}, tickers={sid: column}, cash_usd=100)])
        raw = dict(schema=reader.SCHEMA + '_RAW', engine_call_count=1, started_reference=started_ref,
                   execution=execution, **common)
        restored = copy.deepcopy(execution)
        restored['decisions'][0]['targets'][sid]['ticker'] = 'GOOGL'
        restored['trades'][0]['ticker'] = 'GOOGL'
        restored['daily'][0]['tickers'][sid] = 'GOOGL'
        candidate = dict(schema=reader.SCHEMA, status='INDEPENDENT_ACCOUNTING_PASSED', engine_call_count=1,
                         execution_performed=True, started_reference=started_ref, execution=restored, **inputs, **common)
        return candidate, started, raw, labels

    def test_raw_only_label_restoration_and_mutated_cash_rejected(self):
        fixture = self.raw_fixture()
        reader.audit_raw(*fixture)
        fixture[0]['execution']['daily'][0]['cash_usd'] = 101
        with self.assertRaises(ValueError): reader.audit_raw(*fixture)

    def test_raw_source_and_boolean_engine_count_rejected(self):
        candidate, started, raw, labels = self.raw_fixture()
        raw['source_hashes'] = {'other': 'hash'}
        with self.assertRaises(ValueError): reader.audit_raw(candidate, started, raw, labels)
        candidate, started, raw, labels = self.raw_fixture()
        raw['engine_call_count'] = True
        with self.assertRaises(ValueError): reader.audit_raw(candidate, started, raw, labels)

    def test_only_candidate_audit_and_single_normalization(self):
        docs = {role: json.loads((reader.BASE / reader.BOUND[role][0]).read_bytes())
                for role in ('schedule', 'price', 'identity')}
        schedule, price, identities = (docs[k] for k in ('schedule', 'price', 'identity'))
        normalized, evidence = reader.normalization.normalized_schedule(schedule['schedule'])
        conversion = []
        for kind in ('open', 'close'):
            for day in price['calendar']:
                for row in identities['rows']:
                    value = price['matrices'][kind][day][row['ticker']]
                    with localcontext(Context(prec=160)):
                        converted = float(Decimal(value))
                        error = abs(Decimal.from_float(converted) - Decimal(value))
                    conversion.append(dict(session=day, security_id=row['security_id'], field=kind,
                        original_decimal=value, execution_float=converted, absolute_binary_float_error=str(error)))
        candidate = dict(calendar=price['calendar'], schedule=schedule['schedule'], execution_contract=reader.CONTRACT,
            security_count=8, distinct_issuer_count=7, fixed_four_security_policy=False,
            per_decision_target_counts=[len(r['targets']) for r in schedule['schedule']],
            goog_googl_relationship='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME',
            normalized_schedule=normalized, normalization_evidence=evidence, independent_decimal_accounting={'fixture': True},
            price_conversion_evidence=dict(policy='EXPLICIT_FLOAT_ONLY_AT_FROZEN_ENGINE_BOUNDARY_DECIMAL_MARKS_RETAINED_FOR_INDEPENDENT_AUDIT',cell_count=1712,cells=conversion),
            execution=dict(daily=[dict(session=d, total_value_usd=25000) for d in price['calendar']], executions=[], trades=[]))
        def fake_audit(**kwargs):
            self.assertTrue(all(isinstance(v[kind], Decimal) for day in kwargs['prices'].values()
                                for v in day.values() for kind in ('open', 'close')))
            return {'fixture': True}
        with (patch.object(reader.normalization, 'normalized_schedule', wraps=reader.normalization.normalized_schedule) as norm,
              patch.object(reader.accounting, 'audit', side_effect=fake_audit) as audit):
            reader.audit_candidate(candidate, schedule, price, identities)
            self.assertEqual(norm.call_count, 1)
            self.assertEqual(audit.call_count, 1)


if __name__ == '__main__': unittest.main()
