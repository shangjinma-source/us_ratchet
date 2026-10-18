from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from data.current_quantity_portfolio_research_v2 import CurrentQuantityPortfolioResearchV2, RESEARCH_VERSION, WORKER_DEPENDENCIES, WORKER
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account, REQUIRED_PINS, VERSION
from data.current_cash_portfolio_research import ResearchExpiredError

ROOT=Path(__file__).resolve().parents[1]

def fixture(root, budget=128):
    pins={}
    def save(name,raw):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        pins[name]=sha256(raw).hexdigest()
    for name in (*WORKER_DEPENDENCIES,WORKER):
        save(name,(ROOT/name).read_bytes())
    args=dict(decision_date='2026-10-13',quote_as_of='2026-10-13',price_basis='SYNTHETIC_USD',
        prices={'A':'60','B':'40'},metadata={'A':dict(ticker='AAA',issuer_id='IA'),'B':dict(ticker='BBB',issuer_id='IB')},
        entered_cash='100',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}],
        scenario_dates=['2026-09-30','2026-10-13'],max_objective_evaluations=budget,fixed_seed='synthetic')
    quotes=[];sources={}
    for sid,price in args['prices'].items():
        ticker=args['metadata'][sid]['ticker'];name=sid+'.json'
        raw={'chart':{'error':None,'result':[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=[int(datetime(2026,10,d,20,tzinfo=timezone.utc).timestamp()) for d in (12,13,14)],
            indicators={'quote':[{**{k:[int(price)]*3 for k in ('open','high','low','close')},'volume':[1,1,1]}]})]}}
        save(name,json.dumps(raw).encode());sources[sid]=dict(path=name,price_basis='SYNTHETIC_USD')
        quotes.append(dict(security_id=sid,as_of='2026-10-13',price=price,price_basis='SYNTHETIC_USD',source_references=[name]))
    save('input.json',json.dumps(dict(search_arguments=args,valuation_quotes=quotes,bar_sources=sources)).encode())
    save('admission.json',json.dumps(dict(status='ADMITTED_CASH_RESEARCH_V2',method=VERSION,input_path='input.json',input_sha256=pins['input.json'])).encode())
    descriptor=dict(input_path='input.json',admission_path='admission.json',source_hashes=pins)
    search=Mock(side_effect=decide_quantity_v2_for_account)
    service=CurrentQuantityPortfolioResearchV2(root=root,source_loader=lambda:deepcopy(descriptor),search=search,test_mode=True)
    return service,search,descriptor

class SnapshotTests(unittest.TestCase):
    def test_default_unavailable_and_unknown_does_not_search(self):
        with tempfile.TemporaryDirectory() as d:
            service=CurrentQuantityPortfolioResearchV2(root=d)
            with self.assertRaisesRegex(ValueError,'ADMISSION_UNAVAILABLE'):service.calculate('100')
            with self.assertRaises(ResearchExpiredError):service.snapshot('a'*24)

    def test_real_tiny_v2_cache_cash_composition_and_immutable_bars(self):
        with tempfile.TemporaryDirectory() as d:
            service,search,_=fixture(Path(d))
            first=service.calculate('60');self.assertEqual(first['target_quantities'],{'B':1})
            again=service.calculate('60.00');self.assertTrue(again['cache_hit']);self.assertEqual(search.call_count,1)
            second=service.calculate('100');self.assertEqual(second['target_quantities'],{'A':1,'B':1})
            self.assertNotEqual(first['research_id'],second['research_id']);self.assertEqual(search.call_count,2)
            self.assertEqual(second['research_version'],RESEARCH_VERSION);self.assertIsNone(second['executable_buy_quantities'])
            second['stocks'].clear();self.assertEqual(len(service.snapshot(second['research_id'])['stocks']),2)
            with self.assertRaisesRegex(ValueError,'NOT_SELECTED'):service.bars(first['research_id'],'AAA')
            for interval in ('day','week','month'):
                bars=service.bars(second['research_id'],'AAA',interval)
                self.assertEqual(bars['security_id'],'A');self.assertEqual(bars['research_id'],second['research_id'])
                self.assertTrue(all(row['date']<='2026-10-13' for row in bars['bars']))
                self.assertFalse(bars['limit_line_coordinate_confirmed'])
            with self.assertRaises(ResearchExpiredError):service.bars('f'*24,'AAA')

    def test_concurrent_same_cash_exactly_one_search(self):
        with tempfile.TemporaryDirectory() as d:
            service,search,_=fixture(Path(d))
            with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(service.calculate,['100']*4))
            self.assertEqual(search.call_count,1);self.assertEqual(len({r['research_id'] for r in results}),1)

    def test_drift_and_outside_path_reject_before_search_or_cached_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);service,search,descriptor=fixture(root);view=service.calculate('60')
            (root/'B.json').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):service.snapshot(view['research_id'])
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):service.calculate('100')
            self.assertEqual(search.call_count,1)
            descriptor['source_hashes']={'../outside':'a'*64}
            with self.assertRaisesRegex(ValueError,'PATH_INVALID'):service.calculate('100')

    def test_rehashed_coordinate_counterexamples_reject_before_search(self):
        for case in ('wrong_raw_close','missing_open','bad_ordering','wrong_bar_basis','wrong_quote_basis','wrong_quote_price','precise_raw_decimal'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as d:
                root=Path(d);service,search,descriptor=fixture(root)
                data=json.loads((root/'input.json').read_bytes())
                raw=json.loads((root/'A.json').read_bytes())
                row=raw['chart']['result'][0]['indicators']['quote'][0]
                if case=='wrong_raw_close':
                    for key in ('open','high','low','close'):row[key][1]=6000
                elif case=='missing_open':row['open'][1]=None
                elif case=='bad_ordering':row['low'][1]=61
                elif case=='wrong_bar_basis':data['bar_sources']['A']['price_basis']='OTHER'
                elif case=='wrong_quote_basis':data['valuation_quotes'][0]['price_basis']='OTHER'
                elif case=='wrong_quote_price':data['valuation_quotes'][0]['price']='6000'
                elif case=='precise_raw_decimal':
                    # The float parser rounds this to 60; original decimal must still differ.
                    row['close'][1]='EXACT_DECIMAL'
                def rewrite(name,value):
                    encoded=json.dumps(value).replace('"EXACT_DECIMAL"','60.000000000000000001').encode()
                    (root/name).write_bytes(encoded);descriptor['source_hashes'][name]=sha256(encoded).hexdigest()
                rewrite('A.json',raw);rewrite('input.json',data)
                admission=json.loads((root/'admission.json').read_bytes())
                admission['input_sha256']=descriptor['source_hashes']['input.json'];rewrite('admission.json',admission)
                with self.assertRaises(ValueError):service.calculate('100')
                search.assert_not_called()
                self.assertEqual(service.snapshots,{})

    def test_isolated_default_ignores_cached_algorithm_and_projection_objects(self):
        import data.current_research_capital_decision_v2 as old_adapter
        import data.current_quantity_projection_v2 as old_projection
        import backtest.return_priority_fresh_cash_quantity_search_v2 as old_core
        with tempfile.TemporaryDirectory() as d:
            _,_,descriptor=fixture(Path(d))
            service=CurrentQuantityPortfolioResearchV2(root=d,source_loader=lambda:deepcopy(descriptor))
            with patch.object(old_adapter,'decide_quantity_v2_for_account',side_effect=AssertionError('CACHED_OLD_ADAPTER')), \
                 patch.object(old_core,'search_fresh_cash_quantities',side_effect=AssertionError('CACHED_OLD_CORE')), \
                 patch.object(old_projection,'project_capital_decision_v2',side_effect=AssertionError('CACHED_OLD_PROJECTOR')), \
                 patch('data.current_quantity_portfolio_research_v2.project_capital_decision_v2',side_effect=AssertionError('HOST_PROJECTOR')):
                result=service.calculate('100')
            self.assertEqual(result['target_quantities'],{'A':1,'B':1})
            self.assertEqual(result['implementation_mode'],'ISOLATED_PINNED_SOURCE_BYTES')
            self.assertEqual(set(result['implementation_source_hashes']),set(WORKER_DEPENDENCIES)|{WORKER})
            self.assertTrue(service.calculate('100')['cache_hit'])

    def test_missing_closure_and_changed_bootstrap_fail_before_worker(self):
        for missing in ('data/current_quantity_projection_v2.py','scripts/return_priority_latest_saved_snapshot_research.py'):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as d:
                _,_,descriptor=fixture(Path(d));descriptor['source_hashes'].pop(missing)
                service=CurrentQuantityPortfolioResearchV2(root=d,source_loader=lambda:deepcopy(descriptor))
                with patch('data.current_quantity_portfolio_research_v2.subprocess.run') as run:
                    with self.assertRaisesRegex(ValueError,'CLOSURE_MISSING'):service.calculate('100')
                    run.assert_not_called()
        with tempfile.TemporaryDirectory() as d:
            _,_,descriptor=fixture(Path(d));raw=b'print("fake")'
            (Path(d)/WORKER).write_bytes(raw);descriptor['source_hashes'][WORKER]=sha256(raw).hexdigest()
            service=CurrentQuantityPortfolioResearchV2(root=d,source_loader=lambda:deepcopy(descriptor))
            with self.assertRaisesRegex(ValueError,'BOOTSTRAP_VERSION'):service.calculate('100')
            with self.assertRaisesRegex(ValueError,'TEST_MODE_REQUIRED'):
                CurrentQuantityPortfolioResearchV2(root=d,search=Mock())

    def test_incomplete_no_target_and_failed_attempt_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            service,search,_=fixture(Path(d),budget=1)
            view=service.calculate('100');self.assertEqual(view['status'],'INCOMPLETE');self.assertIsNone(view['target_quantities'])
            self.assertEqual(view['stocks'],[]);self.assertTrue(view['execution_blocked'])
            service.calculate('100');self.assertEqual(search.call_count,1)
        with tempfile.TemporaryDirectory() as d:
            service,search,_=fixture(Path(d));search.side_effect=ValueError('synthetic failure')
            with self.assertRaises(ValueError):service.calculate('100')
            with self.assertRaisesRegex(ValueError,'NO_AUTOMATIC_RETRY'):service.calculate('100')
            self.assertEqual(search.call_count,1)

if __name__=='__main__':unittest.main()
