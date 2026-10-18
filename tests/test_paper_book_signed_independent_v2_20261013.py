"""Changed v2 flow semantics only; prior OHLC/ledger groups are not replayed."""
from pathlib import Path
import hashlib,types,unittest
from copy import deepcopy
from fractions import Fraction as F
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'backtest/return_priority_paper_continuous_book_research.py';raw=SOURCE.read_bytes();assert hashlib.sha256(raw).hexdigest()=='53f5e13f51464831322935ec693e7d3bd1e72a416354f7a4e6af0bde5890b1d3'
s=types.ModuleType('independent_signedv2');exec(compile(raw,str(SOURCE),'exec'),s.__dict__)


def fixture():
    days=['2026-02-02','2026-02-03','2026-02-04']
    return dict(calendar=days,open_prices={d:{}for d in days},close_prices={d:{}for d in days},metadata={'A':dict(ticker='A',issuer_id='I',risk_chain='C')},initial_shares={},initial_cash=120,fee_bps=10,minimum_cash_buffer=0,decisions=[],cash_events=[dict(id='withdraw1',session=days[0],amount=-20),dict(id='deposit',session=days[1],amount=50),dict(id='withdraw2',session=days[2],amount=-75)],risk_parameters=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),enforce_initial_target_risk=False,declared_price_basis='CONDITIONAL_ONLY_CASH')


class ChangedSignedFlows(unittest.TestCase):
    def test_signed_flows_insufficient_precommit_and_no_cagr_or_duplicate_ticker(self):
        f=fixture();r=s.simulate_paper_book(**f);self.assertEqual([F(x['cash'])for x in r['daily_rows']],[F(100),F(150),F(75)]);self.assertTrue(all(F(x['cumulative_time_weighted_return'])==0 for x in r['daily_rows']));self.assertIsNone(r['cagr']);self.assertFalse(r['annualization_performed']);self.assertEqual(r['performance_measure'],'FLOW_ADJUSTED_DAILY_CHAIN_TWR_WITHOUT_ANNUALIZATION');self.assertEqual(r['consumed_cash_event_ids'],['withdraw1','deposit','withdraw2'])
        bad=fixture();bad['cash_events'][1]['amount']=-121;r=s.simulate_paper_book(**bad);self.assertEqual(r['reason'],'EXTERNAL_WITHDRAWAL_EXCEEDS_PRE_EXECUTION_CASH');self.assertEqual(F(r['final_cash']),100);self.assertEqual(r['consumed_cash_event_ids'],['withdraw1']);self.assertEqual(len(r['daily_rows']),1)
        duplicate=fixture();duplicate['metadata']['B']=dict(ticker='A',issuer_id='I2',risk_chain='C2')
        with self.assertRaisesRegex(ValueError,'ticker'):s.simulate_paper_book(**duplicate)
        for amount in (True,float('nan'),float('inf')):
            bad=fixture();bad['cash_events'][0]['amount']=amount
            with self.assertRaises(ValueError):s.simulate_paper_book(**bad)

    def test_full_cash_withdrawal_returns_blocked_prefix_before_ids_or_zero_equity_commit(self):
        f=fixture();f['cash_events']=[dict(id='all',session=f['calendar'][1],amount=-120)]
        r=s.simulate_paper_book(**f)
        self.assertEqual(r['status'],'BLOCKED');self.assertEqual(F(r['final_cash']),120);self.assertEqual(r['consumed_cash_event_ids'],[]);self.assertEqual(len(r['daily_rows']),1)


if __name__=='__main__':unittest.main()
