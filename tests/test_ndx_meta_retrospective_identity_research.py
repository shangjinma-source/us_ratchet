from copy import deepcopy
import json
from pathlib import Path
import unittest

from backtest import ndx_meta_retrospective_identity_research as meta
from scripts import ndx_meta_retrospective_identity_research as recipe


class MetaRetrospectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=recipe.build_report()

    def test_full_original_training_dates_and_actual_daily_symbols(self):
        projection=self.report['projection'];rows={row['session']:row for row in projection['rows']}
        self.assertEqual(projection['row_count'],1177)
        self.assertEqual(len(projection['full_training_date_coverage']),15)
        self.assertTrue(all(not row['missing_dates'] and row['earlier_close_available'] for row in projection['full_training_date_coverage']))
        self.assertEqual(rows['2022-01-12']['ticker'],'FB')
        self.assertEqual(rows['2022-06-06']['ticker'],'FB')
        self.assertEqual(rows['2022-06-08']['ticker'],'FB')
        self.assertEqual(rows['2022-06-09']['ticker'],'META')
        self.assertTrue(all(row['security_id']==meta.SID and row['declared_share_ratio']==1 for row in rows.values()))

    def test_decision_before_rename_fills_next_open_with_new_actual_label(self):
        execution=self.report['decision_to_fill_rename']['execution']
        decision=execution['decisions'][0]
        self.assertEqual(decision['decision_date'],'2022-06-08')
        self.assertEqual(decision['targets'][meta.SID]['ticker'],'FB')
        trade=execution['trades'][0]
        self.assertEqual(trade['session'],'2022-06-09')
        self.assertEqual(trade['ticker'],'META')
        self.assertEqual(trade['security_id'],meta.SID)
        self.assertAlmostEqual(trade['price_usd'],194.27999877929688)

    def test_between_decisions_rename_does_not_change_shares_cash_or_create_action(self):
        execution=self.report['between_decisions_rename']['execution']
        daily={row['session']:row for row in execution['daily']}
        self.assertEqual(daily['2022-06-08']['shares'],daily['2022-06-09']['shares'])
        self.assertEqual(daily['2022-06-08']['cash_usd'],daily['2022-06-09']['cash_usd'])
        self.assertEqual(daily['2022-06-08']['tickers'][meta.SID],'FB')
        self.assertEqual(daily['2022-06-09']['tickers'][meta.SID],'META')
        self.assertFalse(any(row['session']=='2022-06-09' for row in execution['trades']))
        self.assertEqual(execution['corporate_actions'],[])

    def test_label_projection_preserves_frozen_economic_outputs_exactly(self):
        for key in ('decision_to_fill_rename','between_decisions_rename'):
            report=self.report[key];display=report['execution'];numeric=report['untranslated_numeric_execution']
            self.assertEqual(display['summary'],numeric['summary'])
            for before,after in zip(numeric['daily'],display['daily']):
                for field in ('cash_usd','shares','prices','total_value_usd'):
                    self.assertEqual(before[field],after[field])
            for before,after in zip(numeric['trades'],display['trades']):
                for field in ('share_delta','price_usd','transaction_cost_usd'):
                    self.assertEqual(before[field],after[field])

    def test_wrong_pre_rename_ticker_and_changed_bound_projection_rejected(self):
        schedule=[dict(decision_date='2022-06-08',execution_date='2022-06-09',
            targets={meta.SID:dict(issuer_id=meta.ISSUER,ticker='META',target_weight=1.)})]
        with self.assertRaisesRegex(ValueError,'daily actual ticker'):
            meta.simulate_bound_meta(projection=self.report['projection'],schedule=schedule,calendar=['2022-06-08','2022-06-09'])
        changed=deepcopy(self.report['projection']);changed['rename_event']['fact_effective_date']='2022-06-08'
        with self.assertRaisesRegex(ValueError,'independently rebuilt'):
            meta.simulate_bound_meta(projection=changed,schedule=schedule,calendar=['2022-06-08','2022-06-09'])

    def test_receipts_stay_2026_old_fb_cache_is_not_consumed(self):
        projection=self.report['projection']
        self.assertEqual(projection['rename_event']['publication_date'],'2022-06-03')
        self.assertEqual(projection['rename_event']['fact_effective_date'],'2022-06-09')
        self.assertTrue(projection['rename_event']['received_at_utc'].startswith('2026-'))
        self.assertTrue(projection['price_received_at_utc'].startswith('2026-'))
        self.assertFalse(any(Path(path).name=='FB.csv' for path in projection['source_hashes']))
        self.assertFalse(projection['point_in_time_verified'])
        self.assertFalse(projection['historical_provider_binding_certified'])
        self.assertFalse(projection['primary_issuer_cik_adjudicated'])
        meta.nominal.verify(self.report['source_hashes'])

    def test_real_split_neutral_returns_and_all_context_predecessors(self):
        projection=self.report['projection']
        returns=projection['split_neutral_price_returns']
        self.assertEqual(returns['output_return_count'],1176)
        self.assertEqual(returns['explicit_event_cell_count'],1177)
        self.assertEqual(returns['unfinalized_sessions'],['2026-09-11'])
        self.assertEqual(returns['completed_return_count'],1175)
        self.assertFalse(returns['unfinalized_rows_training_use_allowed'])
        self.assertTrue(all(row['session']<'2026-09-11' for row in projection['completed_session_price_returns']))
        self.assertFalse(returns['dividend_cash_flows_included'])
        indexed={row['session']:row for row in returns['rows']}
        rename=indexed['2022-06-09']
        self.assertEqual((rename['previous_ticker'],rename['ticker']),('FB','META'))
        self.assertEqual(rename['applied_share_ratio'],'1')
        self.assertAlmostEqual(rename['price_return'],184/196.63999938964844-1)
        for coverage, bound in zip(projection['full_training_date_coverage'],projection['context_research_return_inputs']):
            payload=bound['input']
            self.assertEqual(coverage['adjacent_observed_previous_close_count'],len(payload['rows']))
            self.assertEqual(payload['rows'],[indexed[day] for day in payload['return_calendar']])
            for day, previous in coverage['previous_date_by_return_date'].items():
                self.assertEqual(previous,projection['calendar'][projection['calendar'].index(day)-1])
            import hashlib
            raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),bound['input_sha256'])
            self.assertFalse(payload['original_context_rewritten'])

    def test_unfinalized_day_rejected_by_accounting_entry(self):
        with self.assertRaisesRegex(ValueError,'Unfinalized'):
            meta.simulate_bound_meta(projection=self.report['projection'],schedule=[],
                calendar=['2026-09-10','2026-09-11'])


if __name__=='__main__':unittest.main()
