import unittest,json
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
from docs.candidates.downside_bounded_execution_supplement_20261105 import extend_execution_evidence
from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends
from docs.candidates import qqq_risk_budget_account_runner as kernel
ROOT=Path(__file__).resolve().parents[1]


def inputs(window):
    recent=window=='2024_2026';base='old_continuous_baseline_20261026_v9' if recent else 'recent_continuous_baseline_20261026_v7';price='old_window_execution_prices_20261026' if recent else 'recent_execution_prices_20261026'
    read=lambda p:json.loads((ROOT/p).read_bytes())
    return read('tmp/'+base+'/execution_inputs.json'),read('tmp/'+price+'/execution_prices_v1.json'),read('tmp/trend_'+window+'_20261026_v1/execution_inputs.json')['action_review']


class SupplementTests(unittest.TestCase):
    def test_nine_paired_execution_events_and_exact_absence_subintervals(self):
        total=0
        for window in ('2021_2023','2024_2026'):
            d,p,r=inputs(window);old=deepcopy(d)
            out,review,pins,audit=extend_execution_evidence(root=ROOT,document=d,prices=p,review=r)
            self.assertEqual(d,old);total+=audit['added_dividends']
            for row in audit['review_rows']:
                if row['status']=='REVIEWED_NO_ACTION_FOR_PERIOD':
                    self.assertGreaterEqual(row['start_exclusive'],row['original_scope_start']);self.assertEqual(row['end_inclusive'],row['original_scope_end']);continue
                events=[e for e in out['dividend_events'] if e['security_id']==row['security_id'] and e['ex_date']==row['ex_date']]
                self.assertEqual(len(events),1);self.assertEqual(F(events[0]['amount_per_share']),F(row['amount_per_share']))
                for observation in row['observed_provider_events']:
                    event=dict(observation,security_id=row['security_id'])
                    gate=dict(unmapped_events=[event],missing_action_streams=[])
                    self.assertTrue(admit_reviewed_dividends(gate,review,out['dividend_events'])['admitted'])
                    self.assertFalse(admit_reviewed_dividends(gate,review,[])['admitted'])
        self.assertEqual(total,9)

    def test_wrong_existing_amount_rejected(self):
        d,p,r=inputs('2021_2023');out,review,_,audit=extend_execution_evidence(root=ROOT,document=d,prices=p,review=r)
        out['dividend_events'][-1]['amount_per_share']='999'
        with self.assertRaisesRegex(ValueError,'EXISTING_DIVIDEND_CONFLICT'):extend_execution_evidence(root=ROOT,document=out,prices=p,review=review)

    def test_generated_nominal_dividend_reaches_real_book_cash(self):
        d,p,r=inputs('2021_2023');_,_,_,audit=extend_execution_evidence(root=ROOT,document=d,prices=p,review=r);event=audit['events'][0];sid=event['security_id']
        sessions=d['assembled']['session_dates'];start=sessions.index(event['ex_date'])-2;end=sessions.index(event['payment_date']);days=sessions[start:end+1]
        closes=dict.fromkeys(days,'10');plans=[dict(decision_date=days[0],search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id=sid,price='10')],source_hashes={})]
        assembled=dict(session_dates=days,monthly_inputs=plans,close_prices={sid:closes},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={},distribution_events=[],distribution_fractional_cash_values={})
        bars={sid:{day:dict(open='10',high='10',low='10',close='10') for day in days}}
        with patch.object(kernel,'decide_continuous_guided_for_account',return_value={'decision_date':days[0],'target_quantities':{sid:4},'investable_equity':'100'}),patch.object(kernel,'rerank',side_effect=lambda x:x):
            book=kernel.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='100',fee_bps='0',slippage_bps='5',max_new_searches=1,dividend_events=[event])
        self.assertEqual(book['status'],'COMPLETE',book.get('reason'))
        self.assertEqual(F(book['daily_ledger'][-1]['cash']),F('59.98')+4*F(event['amount_per_share']))
        self.assertEqual(F(book['daily_ledger'][-1]['dividend_receivable']),0)


if __name__=='__main__':unittest.main()
