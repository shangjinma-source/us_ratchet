"""Synthetic execution and exact production-prompt checks; no network/model."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from scripts.research import run_news_five_case_v1 as runner
from data import news_investment_model_v1 as model


class BatchTests(unittest.TestCase):
    def fixture(self):
        sid='research:security:dltr';days=['2022-08-24','2022-08-25','2022-08-26','2022-08-29']
        risk=runner.MonthlyExitCoreResearchAdapter()
        risk.apply(day='2022-07-29',month='2022-07-29',target={sid:4},closes={sid:'100'})
        _,diag=risk.apply(day='2022-08-23',month='2022-07-29',target={sid:4},closes={sid:'100'})
        inputs={'assembled':{'close_prices':{sid:{day:'100' for day in days}}},'ohlc':{sid:{day:dict(open='100',high='100',low='100',close='100') for day in days}}}
        spec=dict(days=days,security_id=sid,held=4,target=4,initial=dict(cash='500',shares={sid:4},equity='900'),risk_state=diag['state'],monthly_ceiling={sid:4},epoch='2022-07-29')
        return inputs,spec

    def test_fixed_caps_and_fraction_validation(self):
        self.assertEqual(runner.action_cap(dict(action='REDUCE_HOLDING',buy_fraction='0',holding_fraction='1/2'),5,5),2)
        self.assertEqual(runner.action_cap(dict(action='REDUCE_BUY',buy_fraction='1/2',holding_fraction='1'),5,10),7)
        with self.assertRaises(ValueError):runner.action_cap(dict(action='KEEP',buy_fraction='0',holding_fraction='1'),5,5)

    def test_open_orders_do_not_use_same_day_close_and_expiry_respects_exit(self):
        inputs,spec=self.fixture();row=dict(action='EXIT',buy_fraction='0',holding_fraction='0');signal=dict(direction='NEUTRAL',materiality='MODERATE')
        original=runner.replay(inputs,spec,'A',row,signal,'5')
        altered=deepcopy(inputs);sid=spec['security_id']
        for day in spec['days'][1:]:
            altered['assembled']['close_prices'][sid][day]='70';altered['ohlc'][sid][day].update(close='70',low='70')
        changed=runner.replay(altered,spec,'A',row,signal,'5')
        self.assertEqual(original['trace'][0],changed['trace'][0])
        self.assertEqual(original['book']['daily_ledger'][0],changed['book']['daily_ledger'][0])
        self.assertEqual(original['book']['daily_ledger'][-1]['shares'][sid],4)
        self.assertEqual(changed['book']['daily_ledger'][-1]['shares'][sid],0)
        self.assertFalse(changed['trace'][-1]['news_active'])
        self.assertEqual(changed['trace'][-1]['original_target'][sid],0)

    def test_neutral_b_and_keep_match_baseline(self):
        inputs,spec=self.fixture();row=dict(action='KEEP',buy_fraction='1',holding_fraction='1');signal=dict(direction='NEGATIVE',materiality='MODERATE')
        base=runner.replay(inputs,spec,'BASELINE',row,signal,'5')['book']
        for arm in ('A','B'):self.assertEqual(base,runner.replay(inputs,spec,arm,row,signal,'5')['book'])

    def test_real_adapter_prompt_exact_bytes_without_model(self):
        folder=Path('tmp/news_five_case_execution_20261029/DLTR_20220825_v2')
        if not folder.exists():self.skipTest('Optional frozen development package unavailable')
        public=runner.read(folder/'public_input.json');captured=[]
        class Coordinator:
            def __init__(self,*args):pass
            def reserve(self,*args):return nullcontext()
        def invoke(prompt,*args):
            captured.append(prompt.encode('utf-8'))
            return {'rows':[dict(security_id=public['positions'][0]['security_id'],ticker=public['positions'][0]['ticker'],action='ABSTAIN',buy_fraction='1',holding_fraction='1',reason='证据不足',counterevidence=['未证'],uncertainty=['未证'],evidence=[])]},{}
        with TemporaryDirectory() as directory,patch.object(model,'ModelCoordinator',Coordinator),patch.object(model,'_invoke',invoke),patch.object(model,'PROMPT',model.PROMPT+(folder/'temporal_protocol.txt').read_text(encoding='utf-8')):
            result=model.analyze_review(public['sources'],public['positions'],Path(directory)/'investment')
        self.assertEqual(result['status'],'SUCCEEDED')
        self.assertEqual(captured,[(folder/'A_prompt.txt').read_bytes()])

if __name__=='__main__':unittest.main()
