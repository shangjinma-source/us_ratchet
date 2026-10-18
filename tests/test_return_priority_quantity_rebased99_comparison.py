import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import scripts.return_priority_quantity_rebased99_comparison as runner


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class RunnerTests(unittest.TestCase):
    def fixture(self,root,fail=False):
        root=Path(root)
        for name in runner.PROTECTED:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic')
        path=root/runner.RUNNER;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(Path(runner.RUNNER).read_bytes())
        for name in runner.METHODS:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('')
        core=root/runner.METHODS[-1]
        core.write_text('def search_fresh_cash_quantities(**args):\n '+('raise RuntimeError("synthetic failure")' if fail else 'return dict(decision_date=args["decision_date"],entered_cash=args["entered_cash"],objective_evaluations=1,selected=dict(quantities={"s0":1},actual_k=1,notional="1",fees="0",residual_cash="19999",actual_weights={"s0":"1/20000"}))'))
        dates=[(date(2026,10,13)-timedelta(days=i)).isoformat() for i in reversed(range(253))]
        args=dict(prices={f's{i}':'1' for i in range(99)},metadata={f's{i}':dict(ticker=f'T{i}',issuer_id=str(i%98)) for i in range(99)},entered_cash='20000',fee_bps='0',minimum_cash_buffer='0',decision_date='2026-10-13',fixed_seed=runner.SEED,max_objective_evaluations=8192,scenario_dates=dates[21::21],training_scenarios=[{f's{i}':'1' for i in range(99)} for _ in range(12)])
        write(root/'input.json',args);write(root/'prepared.json',dict(status='READY_CONDITIONAL',coverage_denominator=101,search_arguments=args,window=dict(training_dates=dates,member_count=101)))
        write(root/'top/registration.json',dict(input_path='prepared.json',input_sha256=sha(root/'prepared.json')))
        selected=dict(quantities={'s0':1},actual_k=1,notional='1',fees='0',residual_cash='19999',actual_weights={'s0':'1/20000'})
        result=dict(registration_sha256=sha(root/'top/registration.json'),metadata=args['metadata'],selector_result=dict(decision_date=args['decision_date'],entered_cash='20000',candidate_count=99,status='SELECTOR_COMPLETE',selected=selected,training_gross_product='1'))
        write(root/'top/result.json',result);write(root/'top/independent_readback.json',dict(status='PASS_INDEPENDENT_EXACT_TOP1_READBACK',registration_sha256=sha(root/'top/registration.json'),result_sha256=sha(root/'top/result.json')))
        methods={p:sha(root/p) for p in runner.METHODS};pins={p:sha(root/p) for p in ['input.json','prepared.json','top/result.json','top/registration.json','top/independent_readback.json']}
        draft=dict(source_pins=pins,method_hashes=methods,input_path='input.json',input_sha256=pins['input.json'],prepared_path='prepared.json',prepared_sha256=pins['prepared.json'],baseline_result_path='top/result.json',baseline_result_sha256=pins['top/result.json'],maximum_new_search_calls=1,maximum_objective_evaluations=8192,baseline_selector_calls=0,baseline_search_calls=0,book_calls=0,automatic_retry=False)
        write(root/'draft.json',draft);reviewed=dict(methods,**{'input.json':pins['input.json'],'prepared.json':pins['prepared.json'],'draft.json':sha(root/'draft.json')})
        write(root/'review.json',dict(status='PASS',independent_review=True,eligible_for_rebased99_single_conditional_research=True,reviewed_source_hashes=reviewed))
        write(root/'runner_review.json',dict(status='PASS',root_checked=True,reviewed_source_hashes={runner.RUNNER:runner.LOADED_RUNNER_SHA}))
        return root

    def register(self):
        return runner.register(draft_path='draft.json',review_path='review.json',runner_review_path='runner_review.json',output='out')

    def test_single_stub_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'ROOT',self.fixture(td)):
            h=self.register()
            with self.assertRaises(FileExistsError):self.register()
            runner.run(output='out',registration_sha256=h)
            d=json.loads((Path(td)/'out/comparison.json').read_text())
            self.assertEqual(d['v2_to_top1_portfolio_product_ratio'],'1')
            self.assertTrue(json.loads((Path(td)/'out/protected_after.json').read_text())['unchanged'])
            with self.assertRaisesRegex(ValueError,'ALREADY_STARTED'):runner.run(output='out',registration_sha256=h)
            self.assertTrue(all(p[:-3].replace('/','.') not in sys.modules for p in runner.METHODS))

    def test_race_and_cached_method_fail_before_start(self):
        for mode in ('race','cache'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td,patch.object(runner,'ROOT',self.fixture(td)):
                h=self.register();real=runner.verify
                def race(pins):
                    real(pins);p=Path(td)/'input.json';d=json.loads(p.read_text());d['max_objective_evaluations']=99999;write(p,d)
                if mode=='race':
                    with patch.object(runner,'verify',race),self.assertRaisesRegex(ValueError,'LOADED_PIN_CHANGED'):runner.run(output='out',registration_sha256=h)
                else:
                    name=runner.METHODS[0][:-3].replace('/','.')
                    with patch.dict(sys.modules,{name:ModuleType(name)}),self.assertRaisesRegex(ValueError,'FRESH_PROCESS_REQUIRED'):runner.run(output='out',registration_sha256=h)
                self.assertFalse((Path(td)/'out/started.json').exists())

    def test_failure_protection_and_cleanup(self):
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'ROOT',self.fixture(td,True)):
            h=self.register()
            with self.assertRaisesRegex(RuntimeError,'synthetic failure'):runner.run(output='out',registration_sha256=h)
            self.assertTrue((Path(td)/'out/failure.json').exists())
            self.assertTrue(json.loads((Path(td)/'out/protected_after.json').read_text())['unchanged'])
            self.assertTrue(all(p[:-3].replace('/','.') not in sys.modules for p in runner.METHODS))

    def test_review_and_wrapper_mismatch(self):
        for mode in ('review','input'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td,patch.object(runner,'ROOT',self.fixture(td)):
                if mode=='review':
                    p=Path(td)/'review.json';d=json.loads(p.read_text());d['eligible_for_rebased99_single_conditional_research']=False;write(p,d)
                else:
                    p=Path(td)/'input.json';d=json.loads(p.read_text());d['prices']['s0']='2';write(p,d)
                with self.assertRaises(ValueError):self.register()
                self.assertFalse((Path(td)/'out').exists())


if __name__=='__main__':unittest.main()
