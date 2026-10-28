"""Real base-decision authentication, ledger replay and difference core.

Only market/action assembly is a deterministic transport fixture. No live quotes.
"""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from unittest.mock import patch
import unittest
import json
from core.strategy_account_ledger import create_account, apply_event, canonical
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView

path = Path(os.environ.get('NEWS_HOLD_BRIDGE_CANDIDATE', 'data/news_risk_execution_bridge_v1.py'))
spec = importlib.util.spec_from_file_location('news_hold_candidate', path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
NOW = '2026-10-28T14:00:00+00:00'
END = '2026-10-28T14:01:00+00:00'


class HoldBridgeTests(unittest.TestCase):
    def fixture(self, directory):
        state = create_account('synthetic')
        for event in [dict(event_id='fill',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=10,price='100',fees='0',executed_at=NOW),dict(event_id='cash',kind='CASH_CONFIRM',amount='500',cash_basis='TOTAL_UNINVESTED')]:
            state,_ = apply_event(state,event,expected_revision=state['revision'])
        provider = StrategyAccountEvidenceProvider.__new__(StrategyAccountEvidenceProvider)
        provider.output=Path(directory);provider.manifest_path='manifest';raw=canonical(dict(decision_date='2026-09-30'))
        provider.manifest_hash=sha256(raw).hexdigest();provider.closed='2026-09-30T20:00:00+00:00'
        provider._read=lambda p,h:raw
        binding=dict(account_id=state['account_id'],documents={'training_manifest':'manifest'},source_hashes={'manifest':provider.manifest_hash},historical_search_arguments=dict(decision_date='2026-09-30',metadata={'A':{}}),training_cutoff_date='2026-09-30')
        payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={'A':10})
        decision=dict(status='TARGET_READY',payload=payload,decision_id=sha256(canonical(payload)).hexdigest())
        target=dict(target_id='target',payload=dict(account_id=state['account_id'],target_month='2026-10',decision=decision,target_quantities={'A':10}))
        monthly_proposal=dict(proposal_id='monthly',payload=dict(fee_bps='0',proposed_target_quantities={'A':10}))
        signal=dict(account_id=state['account_id'],account_revision=state['revision'],target_id='target',policy_id='policy',proposal_id='monthly',observed_at=NOW,available_at=NOW,valid_from=NOW,valid_until=END,evidence_id='evidence',evidence_archive='archive',effective_target_quantities={'A':10})
        server=dict(state=state,target=target,monthly=monthly_proposal,clock=datetime.fromisoformat(NOW),guard=True)
        composition=SimpleNamespace(enabled=True,policy_id='policy',fees='0',clock=lambda:server['clock'],provider=provider.execution,
            monthly=SimpleNamespace(accounts=SimpleNamespace(read=lambda:server['state']),current=lambda:server['target'],validate_current_target_pins=lambda:None),
            monthly_view=SimpleNamespace(require_proposal=lambda **kwargs:server['monthly']),
            reader=lambda *a,**k:dict(status='DAILY_SIGNAL_READY',signal=deepcopy(signal),evidence_archive='archive'))
        composition.monthly_view.current=lambda:SavedFrontierMonthlyView._view(composition.monthly_view,server['target'],server['monthly'])
        original=dict(status='HOLD',new_orders=[],account_revision=state['revision'],target_id='target',proposal_id='monthly',policy_id='policy',risk_valid_from=NOW,risk_valid_until=END,effective_target_quantities={'A':10})
        proposal=dict(schema='NEWS_INVESTMENT_REVIEW_PROPOSAL_V1',status='REVIEW_PROPOSAL_ONLY',review_id='review',original_binding={k:original[k] for k in ('account_revision','target_id','proposal_id')},review_created_at=NOW,review_valid_until=END,executable=False,orders_created=False,
            rows=[dict(security_id='A',action='REDUCE_HOLDING',held_quantity=10,original_target_quantity=10,proposed_target_quantity=5,reviewed=True)])
        callback=module.make_hold_risk_plan_adapter(composition=composition,validate=lambda:None,review_guard=lambda:server['guard'])
        args=dict(original=original,proposal=proposal,account=deepcopy(state),target=composition.monthly_view.current(),now=NOW)
        calls=[]
        def assemble(view,state,package,historical,*,target_quantities,execution_only):
            calls.append(deepcopy(target_quantities))
            self.assertTrue(execution_only);self.assertIn('news_execution_binding',package['documents'])
            mark=dict(security_id='A',currency='USD',price_basis='TEST',price='100',observed_at=NOW,source_hashes={'synthetic':'a'*64})
            quote=dict(security_id='A',price_basis='TEST',buy='100',sell='100',observed_at=NOW,buy_evaluated=False,evaluated_account_revision=state['revision'],evaluated_net_gap=target_quantities.get('A',0)-10,reference_valid_until=END,sell_reason='verified synthetic quote',source_hashes={'synthetic':'a'*64})
            return dict(marks={'A':mark},limits={'A':quote})
        return callback,args,server,signal,calls,assemble

    def test_real_authentication_and_sell_only_no_mutation(self):
        with TemporaryDirectory() as d:
            callback,args,server,signal,calls,assemble=self.fixture(d);before=deepcopy((args,server,signal))
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',assemble): result=callback(**args)
            self.assertEqual(result['status'],'READY',result)
            self.assertEqual([(o['side'],o['quantity']) for o in result['candidate_orders']],[('SELL',5)])
            self.assertEqual(result['cash']['new_buy_cash_required'],'0');self.assertFalse(result['cash']['sell_proceeds_assumed'])
            self.assertEqual((args,server,signal),before);self.assertEqual(calls,[{'A':5}])
            self.assertEqual(result['binding']['lineage']['original_signal'],signal)
            self.assertFalse(result['executable'])

    def test_frozen_base_tamper_fails_before_quote_transport(self):
        with TemporaryDirectory() as d:
            callback,args,server,signal,calls,assemble=self.fixture(d)
            server['target']['payload']['decision']['decision_id']='bad';args['target']['payload']['decision']['decision_id']='bad'
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',assemble): result=callback(**args)
            self.assertEqual(result['reason'],'FROZEN_TARGET_CHANGED');self.assertEqual(calls,[])

    def test_pending_cash_binding_and_no_admitted_reduction_do_not_quote(self):
        for mode in ('pending','cash','binding','abstain','keep','raise','risk_exit'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                callback,args,server,signal,calls,assemble=self.fixture(d)
                if mode=='pending':server['state']['orders']['open']={'status':'OPEN'};args['account']=deepcopy(server['state'])
                elif mode=='cash':server['state']['cash_confirmation_valid']=False;args['account']=deepcopy(server['state'])
                elif mode=='binding':args['proposal']['original_binding']['target_id']='other'
                elif mode=='abstain':args['proposal']['rows'][0].update(action='ABSTAIN',reviewed=False)
                elif mode=='keep':args['proposal']['rows'][0]['action']='KEEP'
                elif mode=='raise':args['proposal']['rows'][0]['proposed_target_quantity']=11
                else:signal['effective_target_quantities']['A']=0
                with patch.object(StrategyAccountEvidenceProvider,'_assemble',assemble): result=callback(**args)
                self.assertEqual(result['status'],'WAIT',result);self.assertEqual(calls,[]);self.assertEqual(result['candidate_orders'],[])

    def test_capture_races_and_missing_quotes_fail_closed(self):
        for mode in ('account','target','proposal','guard','expiry','quote_expiry','missing'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                callback,args,server,signal,calls,assemble=self.fixture(d)
                def transport(*a,**k):
                    value=assemble(*a,**k)
                    if mode=='account':server['state']['revision']='changed'
                    elif mode=='target':server['target']['target_id']='changed'
                    elif mode=='proposal':server['monthly']['payload']['fee_bps']='1'
                    elif mode=='guard':server['guard']=False
                    elif mode=='expiry':server['clock']=datetime.fromisoformat(END)
                    elif mode=='quote_expiry':value['limits']['A']['reference_valid_until']=NOW
                    else:value['marks']={}
                    return value
                with patch.object(StrategyAccountEvidenceProvider,'_assemble',transport):result=callback(**args)
                self.assertEqual(result['status'],'WAIT',result);self.assertEqual(result['candidate_orders'],[])
                self.assertIsNone(result['cash']);self.assertIsNone(result['valid_until'])

    def test_fresh_reader_time_advances_with_decorated_view_and_datetime_clock(self):
        with TemporaryDirectory() as d:
            callback,args,server,signal,calls,assemble=self.fixture(d)
            server['clock']=datetime.fromisoformat('2026-10-28T14:00:10+00:00')
            signal.update(observed_at='2026-10-28T14:00:10+00:00',available_at='2026-10-28T14:00:10+00:00',valid_from='2026-10-28T14:00:10+00:00',valid_until='2026-10-28T14:02:00+00:00')
            self.assertIn('frontier_proposal',args['target'])
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',assemble):result=callback(**args)
            self.assertEqual(result['status'],'READY',result)
            self.assertEqual(result['valid_until'],END)
            self.assertNotEqual(result['original_risk_interval']['valid_from'],result['binding']['lineage']['original_signal']['valid_from'])

    def test_preview_hash_matches_service_format_and_lineage_bytes(self):
        with TemporaryDirectory() as d:
            callback,args,server,signal,calls,assemble=self.fixture(d)
            with patch.object(StrategyAccountEvidenceProvider,'_assemble',assemble):result=callback(**args)
            expected=sha256(json.dumps(args['original'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(result['original_preview_sha256'],expected)
            self.assertEqual(result['binding']['sha256'],sha256(Path(result['binding']['path']).read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
