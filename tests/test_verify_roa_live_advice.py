from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.verify_roa_live_advice import review, capture

class LiveAdviceTests(unittest.TestCase):
    def fixture(self):
        account={'revision':2,'cash_confirmation_valid':True,'execution_ready':True,'available_cash':'100','holdings':[{'security_id':'old','quantity':14}],'orders':[]}
        order={'security_id':'new','side':'BUY','quantity':5,'limit_price':'20'}
        rows=[dict(order,held=0,target_quantity=5),dict(security_id='old',held=14,target_quantity=14,side='HOLD',quantity=None,limit_price=None)]
        snapshot=dict(account=account,account_revision=2,strategy_epoch='epoch',status='READY',phase='OPEN',signal_date='2026-11-05',execution_session='2026-11-06',executable=True,advice_ready=True,orders_created=False,target_id='a'*64,proposal_id='b'*64,valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T14:35:00Z',quote_valid_until='2026-11-06T14:33:00Z',target_quantities={'old':14,'new':5},rows=rows,difference=dict(schema='STRATEGY_MANUAL_CASH_DIFFERENCE_V1',account_id='account',account_revision=2,binding=dict(account_id='account',account_revision=2,fee_bps='0',marks={'new':dict(security_id='new',currency='USD',price_basis='current',price='20',observed_at='2026-11-06T14:31:30Z')},limits={'new':dict(buy='20',sell='20',security_id='new',price_basis='current',observed_at='2026-11-06T14:31:30Z')}),new_orders=[order],new_buy_cash_required='100',spendable_cash='100'))
        return dict(before={'account':deepcopy(account)},after={'account':deepcopy(account)},config=dict(active=True,strategy_kind='ROA_DEFENSIVE_V1',strategy_epoch='epoch',account_id='account'),snapshot=snapshot,now=datetime(2026,11,6,14,32,tzinfo=timezone.utc))
    def test_ready(self):self.assertTrue(review(**self.fixture())['api_advice_passed'])
    def test_wait_not_pass(self):
        for status in ('PENDING','HOLD','WAIT_FRESH_QUOTE'):
            args=self.fixture();args['snapshot'].update(status=status,executable=False)
            result=review(**args);self.assertEqual(result['status'],'WAIT_EVENT');self.assertFalse(result['api_advice_passed'])
    def test_capture_service_failure_is_not_normal_wait(self):
        for snapshot_code in (200,503):
            with self.subTest(snapshot_code=snapshot_code),TemporaryDirectory() as folder:
                fixture=self.fixture();fixture['snapshot'].update(status='WAIT_FRESH_QUOTE',executable=False)
                class Response:
                    def __init__(self,name):
                        self.code=snapshot_code if name=='snapshot' else 200
                        self.body=json.dumps(fixture[name]).encode()
                    def read(self):return self.body
                responses=[Response(name) for name in ('before','config','snapshot','after')]
                with patch('scripts.verify_roa_live_advice.urlopen',side_effect=responses):
                    result=capture('http://isolated.test',Path(folder)/'evidence')
                self.assertEqual(result['status'],'WAIT_EVENT' if snapshot_code==200 else 'FAILED')
                self.assertFalse(result['api_advice_passed'])
                self.assertEqual('HTTP_STATUS_INVALID' in result['errors'],snapshot_code!=200)
    def test_negative_cases(self):
        for case in ('changed','budget','expiry','fractional','cent','hash','oversell','stale','target','cash_invalid','bound_limit','phase','session'):
            with self.subTest(case=case):
                args=self.fixture();s=args['snapshot'];o=s['difference']['new_orders'][0]
                if case=='changed':args['after']['account']['revision']=3
                elif case=='budget':s['account']['available_cash']='99'
                elif case=='expiry':s['quote_valid_until']='2026-11-06T14:31:59Z'
                elif case=='fractional':o['quantity']=1.5
                elif case=='cent':o['limit_price']='20.001'
                elif case=='hash':s['target_id']='bad'
                elif case=='bound_limit':s['difference']['binding']['limits']['new']['buy']='19'
                elif case=='phase':s['phase']='UNKNOWN'
                elif case=='session':s['execution_session']='2026-11-09'
                elif case=='target':s['target_quantities']['new']=1;s['rows'][0]['target_quantity']=1
                elif case=='cash_invalid':
                    for response in (args['before'],args['after'],s):response['account']['cash_confirmation_valid']=False
                elif case=='stale':s['difference']['binding']['marks']['new']['observed_at']='2026-11-06T14:29:00Z'
                else:o.update(security_id='old',side='SELL',quantity=15)
                self.assertFalse(review(**args)['api_advice_passed'])

if __name__=='__main__':unittest.main()
