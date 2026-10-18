"""New synthetic OHLC alignment and exact four-day ledger; no actual source reads."""
from pathlib import Path
from datetime import date,timedelta
from fractions import Fraction as F
from copy import deepcopy
import hashlib,importlib.util,sys,unittest,types
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BOOK=ROOT/'tmp/return_priority_paper_continuous_book_prepared_20261013_v2/return_priority_paper_continuous_book_research.py.before';raw=BOOK.read_bytes();assert hashlib.sha256(raw).hexdigest()=='5a2e90a159cf40c5738516ab37a3cd17bc1c1f2b7f3251cb88546ce02f796cd2'
book=types.ModuleType('independent_oldbook');exec(compile(raw,str(BOOK),'exec'),book.__dict__)
PATH=ROOT/'data/current_research_ohlc_panel.py';assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='c9eed4d223c33a8edbdd1f425eff80079ded57cc55f69386d58f696d45b8e1f0'
spec=importlib.util.spec_from_file_location('independent_ohlc',PATH);ohlc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ohlc)


def ledger_fixture():
    days=['2026-01-05','2026-01-06','2026-01-07','2026-01-08']
    return dict(calendar=days,open_prices={days[0]:{'A':100},days[1]:{'A':110,'B':50},days[2]:{'B':70},days[3]:{'A':120,'B':60}},close_prices={days[0]:{'A':105},days[1]:{'B':60},days[2]:{'B':65},days[3]:{'A':125,'B':55}},metadata={sid:dict(ticker=sid,issuer_id='ISS'+sid,risk_chain='CHAIN'+sid)for sid in ('A','B')},initial_shares={'A':2},initial_cash=100,fee_bps=100,minimum_cash_buffer=10,decisions=[dict(id='p1',decision_date=days[0],target_shares={'B':3}),dict(id='p2',decision_date=days[2],target_shares={'A':1,'B':1})],cash_events=[dict(id='deposit',session=days[1],amount=50)],risk_parameters=dict(max_single_weight=.45,min_single_weight=.05,top_three_cap=.8,min_neff_ratio=.7,chain_cap=.55),enforce_initial_target_risk=False,declared_price_basis='CONDITIONAL_SYNTHETIC')


class IndependentComponents(unittest.TestCase):
    def test_ohlc_default_partial_boundaries_full1198_alignment_control_separation(self):
        with patch.object(ohlc.close,'_read_fixed',side_effect=AssertionError('Actual raw read forbidden')):self.assertEqual(ohlc.load_current_ohlc_panel()['source_files_read'],0)
        calendar=[(date(2026,10,12)-timedelta(days=1197-i)).isoformat()for i in range(1198)];tickers=[f'FAKE{i}'for i in range(101)]+list(ohlc.close.CONTROLS)
        sealed=dict(calendar=calendar,target=calendar[-1],stocks=[dict(ticker=t,raw_close=[100.]*1198)for t in tickers[:101]],controls=[dict(ticker=t,raw_close=[100.]*1198)for t in tickers[101:]],**ohlc.close.FALSE_FLAGS)
        channels={t:dict(ticker=t,dates=list(calendar),values=[[100.,110.,90.,100.,1000]for _ in calendar],raw_sha256='a'*64,decoded_sha256='b'*64,events_sha256='c'*64)for t in tickers}
        channels['FAKE0']['dates'].pop(500);channels['FAKE0']['values'].pop(500);sealed['stocks'][0]['raw_close'][500]=None
        channels['FAKE1']['values'][700][0]=None
        panel=ohlc.bind_ohlc_panel(sealed_close=sealed,channels=channels)
        self.assertEqual(len(panel['calendar']),1198);self.assertEqual(len(panel['stocks']),101);self.assertEqual(len(panel['controls']),3)
        self.assertEqual(panel['stocks'][0]['values'][500],[None]*5);self.assertEqual(panel['stocks'][1]['missing_open_indices'],[700]);self.assertTrue(panel['no_date_compression']);self.assertFalse(panel['open_execution_authorized'])
        self.assertTrue(all(r['role']=='REFERENCE_ONLY_NEVER_TRAIN'for r in panel['controls']))
        with self.assertRaises(ValueError):ohlc._validate_ohlcv_row([120.,110.,None,None,100])
        with self.assertRaises(ValueError):ohlc._validate_ohlcv_row([None,None,90.,80.,100])
        broken=deepcopy(channels);broken['FAKE1']['values'][4][3]=101.
        with self.assertRaisesRegex(ValueError,'CLOSE'):ohlc.bind_ohlc_panel(sealed_close=sealed,channels=broken)

    def test_nextopen_two_sides_flow_twr_atomic_and_future_dicts(self):
        inputs=ledger_fixture();r=book.simulate_paper_book(**inputs);rows=r['daily_rows'];self.assertEqual(len(rows),4)
        expected_cash=[F(100),F(2163,10),F(2163,10),F(2139,10)];expected_equity=[F(310),F(3963,10),F(4113,10),F(3939,10)]
        growth=[F(310,300),F(320,300)*F(3963,3700),F(320,300)*F(4113,3700),F(320,300)*F(3939,3700)]
        for row,cash,equity,g in zip(rows,expected_cash,expected_equity,growth):self.assertEqual(F(row['cash']),cash);self.assertEqual(F(row['close_equity']),equity);self.assertEqual(F(row['cumulative_time_weighted_return']),g-1)
        first,second=r['executions'];self.assertEqual(first['decision_date'],'2026-01-05');self.assertEqual(first['execution_date'],'2026-01-06');self.assertEqual(F(first['sell_fee']),F(22,10));self.assertEqual(F(first['buy_fee']),F(15,10));self.assertEqual(F(first['cash_after_sells']),F(3678,10));self.assertEqual(F(second['sell_fee'])+F(second['buy_fee']),F(24,10))
        future=deepcopy(inputs);future['open_prices']['2099-01-01']={'A':True,'B':float('nan')};future['close_prices']['2099-01-01']={'A':-1};self.assertEqual(book.simulate_paper_book(**future),r)
        fail=ledger_fixture();fail['decisions'][0]['target_shares']={'B':1000};blocked=book.simulate_paper_book(**fail);self.assertEqual(blocked['status'],'BLOCKED');self.assertEqual(blocked['final_shares'],{'A':2});self.assertEqual(F(blocked['final_cash']),150);self.assertEqual(blocked['executions'][0]['status'],'BLOCKED_ATOMIC_NO_TRADES_COMMITTED');self.assertEqual(len(blocked['daily_rows']),1)

    def test_registered_withdrawal_must_be_supported_with_sufficient_cash(self):
        inputs=ledger_fixture();inputs['cash_events'][0]['amount']=-20
        # Method explicitly permits withdrawals; sufficient100 cash should allow it.
        r=book.simulate_paper_book(**inputs)
        self.assertIn('deposit',r['consumed_cash_event_ids'])


if __name__=='__main__':unittest.main()
