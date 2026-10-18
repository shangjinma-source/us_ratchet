from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_store import StrategyAccountStore
from data import strategy_account_target_service as module
from test_strategy_account_target_decision import fixture, ROOT


class ServiceTests(unittest.TestCase):
    def fixture(self,folder):
        args,limits=fixture(folder);runtime=Path(folder)/'runtime';pins={}
        for path in module.MINIMUM_RUNTIME_PATHS:
            raw=(ROOT/path).read_bytes();destination=runtime/path
            destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
            pins[path]=sha256(raw).hexdigest()
        time=[datetime.fromisoformat(args['now'])]
        store=StrategyAccountStore(Path(folder)/'strategy.db',clock=lambda:time[0])
        state=store.initialize('strategy',operation_id='init')
        for event in args['state']['events']:
            state,_=store.append(event['payload'],expected_revision=state['revision'])
        self.assertEqual(state,args['state'])
        evidence={k:deepcopy(args[k]) for k in ('source_package','manifest_path','marks_path','unit_review_path')}
        evidence['limits']=limits
        service=module.StrategyAccountTargetService(store=store,evidence_provider=lambda state:deepcopy(evidence),
            runtime_root=runtime,runtime_pins=pins,maximum_mark_age_seconds=120,execution_fee_bps='0',clock=lambda:time[0])
        return service,time,runtime,store

    def test_real_tiny_search_readonly_and_no_client_clock(self):
        with TemporaryDirectory() as folder:
            service,time,_,store=self.fixture(folder);before=store.path.read_bytes()
            result=service.generate();self.assertEqual(result['status'],'READY')
            self.assertEqual(result['difference']['new_orders'],[])
            self.assertEqual(store.path.read_bytes(),before)
            self.assertFalse(result['runtime_transitive_closure_certified'])
            with self.assertRaises(TypeError):service.preview(now=time[0])
            time[0]+=timedelta(seconds=121)
            self.assertEqual(service.preview()['status'],'REQUOTE_REQUIRED')
            self.assertEqual(service.preview()['reason'],'NO_CURRENT_TARGET')

    def test_select_real_v2_without_limits_or_preview(self):
        with TemporaryDirectory() as folder:
            service,_,_,store=self.fixture(folder);before=store.path.read_bytes()
            original=service.provider
            service.provider=lambda state:{k:v for k,v in original(state).items() if k!='limits'}
            with patch.object(service,'_preview',side_effect=AssertionError('no execution preview')), patch.object(module,'decide_target',wraps=module.decide_target) as search:
                result=service.select()
            self.assertEqual(result['status'],'READY');self.assertFalse(result['execution_previewed'])
            self.assertEqual(search.call_count,1);self.assertIsNone(service.current[1])
            self.assertEqual(service.current[2]['revision'],store.read()['revision'])
            self.assertEqual(store.path.read_bytes(),before)
            self.assertEqual(service.preview()['reason'],'EXECUTION_LIMITS_REQUIRED')

    def test_search_account_source_and_time_changes_fail_closed(self):
        for kind,reason in [('account','ACCOUNT_CHANGED_DURING_TARGET'),('source','RUNTIME_SOURCE_CHANGED'),('time','REQUOTE_REQUIRED')]:
            with self.subTest(kind=kind),TemporaryDirectory() as folder:
                service,time,runtime,store=self.fixture(folder)
                real=module.decide_target
                def during(**kwargs):
                    result=real(**kwargs)
                    if kind=='time':time[0]+=timedelta(seconds=121)
                    elif kind=='source':
                        path=runtime/'data/strategy_account_preview.py';path.write_bytes(path.read_bytes()+b'\n')
                    else:
                        state=store.read();store.append(dict(event_id='changed',kind='CASH_CONFIRM',amount='501',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
                    return result
                with patch.object(module,'decide_target',side_effect=during):result=service.generate()
                self.assertEqual(result['reason'],reason);self.assertNotIn('difference',result)
                self.assertIsNone(service.current)

    def test_missing_account_and_provider_cannot_supply_now_or_decision(self):
        with TemporaryDirectory() as folder:
            service,time,_,_=self.fixture(folder)
            original=service.provider
            service.provider=lambda state:dict(original(state),now=time[0].isoformat())
            self.assertEqual(service.generate()['reason'],'TARGET_PROVIDER_FIELDS')
            service.store=StrategyAccountStore(Path(folder)/'missing'/'a.db')
            self.assertEqual(service.generate()['reason'],'ACCOUNT_NOT_INITIALIZED')
            self.assertFalse(service.store.path.parent.exists())


if __name__=='__main__':unittest.main()
