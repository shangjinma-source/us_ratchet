import copy
import json
from hashlib import sha256
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_strategy_monthly_target_charts import ChartsTests
from data.strategy_account_holding_charts import StrategyAccountHoldingCharts
from api.strategy_account_charts import create_router


class HoldingTests(unittest.TestCase):
    def setUp(self):
        self.fixture=ChartsTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.state=dict(account_id='real',revision='a'*64,shares={'sid:AAA':14},events=[
            {'payload':{'identity_evidence':{'security_id':'sid:AAA','ticker':'AAA'}}}])
        owner=self
        class Store:
            def read(self):return copy.deepcopy(owner.state)
        self.store=Store();self.configure()

    def configure(self, display_sources=None):
        self.charts=StrategyAccountHoldingCharts(root=self.fixture.root,account_store=self.store,account_id='real',
            training_manifest='manifest.json',training_sha256=sha256((self.fixture.root/'manifest.json').read_bytes()).hexdigest(),
            display_sources=display_sources)

    def display(self, mutate=None):
        raw=copy.deepcopy(self.fixture.raw)
        raw['chart']['result'][0]['meta'].update(exchangeName='NMS',fullExchangeName='NasdaqGS')
        # Distinct complete source proves we never splice historical training prices.
        raw['chart']['result'][0]['indicators']['quote'][0]['close'][0]=10
        if mutate:mutate(raw)
        body=json.dumps(raw).encode();(self.fixture.root/'display.json').write_bytes(body)
        return {'sid:AAA':dict(ticker='AAA',path='display.json',sha256=sha256(body).hexdigest(),
            as_of='2026-10-06',captured_at='2026-10-07T00:00:00+00:00')}

    def test_display_complete_source_and_no_mutation(self):
        source=self.display();self.configure(source);source['sid:AAA']['ticker']='BAD'
        before=copy.deepcopy(self.state);manifest=(self.fixture.root/'manifest.json').read_bytes()
        result=self.bars()
        self.assertEqual(result['bars'][0]['close'],10)
        self.assertEqual(result['as_of'],'2026-10-06');self.assertEqual(len(result['bars']),5)
        self.assertTrue(result['display_source_independent'])
        self.assertFalse(result['limit_line_coordinate_confirmed'])
        self.assertFalse(result['corporate_actions_completeness_verified'])
        self.assertEqual(self.state,before);self.assertEqual((self.fixture.root/'manifest.json').read_bytes(),manifest)
        self.assertEqual(self.bars(interval='week')['bars'][-1]['close'],100)

    def test_display_binding_errors_do_not_fallback(self):
        for field,value,error in [('ticker','BBB','CHART_IDENTITY_MISMATCH'),
                ('sha256','0'*64,'CHART_SOURCE_CHANGED'),('path','../display.json','CHART_SOURCE_PATH_INVALID'),
                ('as_of','2026-10-05','CHART_DISPLAY_AS_OF_MISMATCH'),
                ('captured_at','2026-10-07T00:00:00','CHART_CAPTURE_TIME_INVALID')]:
            source=self.display();source['sid:AAA'][field]=value;self.configure(source)
            with self.assertRaisesRegex(ValueError,error):self.bars()
        for field,value,error in [('exchangeName','NYQ','CHART_DISPLAY_EXCHANGE_INVALID'),
                                 ('currency','CAD','provider symbol/USD')]:
            source=self.display(lambda raw:raw['chart']['result'][0]['meta'].update({field:value}))
            self.configure(source)
            with self.assertRaisesRegex(ValueError,error):self.bars()

    def bars(self,**kwargs):
        return self.charts.bars(account_revision='a'*64,security_id='sid:AAA',**kwargs)

    def test_history_has_account_scope_no_target(self):
        for interval,count in [('day',4),('week',2),('month',2)]:
            result=self.bars(interval=interval)
            self.assertEqual(result['scope'],'RECORDED_HOLDING_HISTORY')
            self.assertEqual(result['account_revision'],'a'*64)
            self.assertNotIn('target_id',result);self.assertEqual(len(result['bars']),count)

    def test_account_revision_scope_identity_and_positive_holding(self):
        for field,value,error in [('revision','b'*64,'STALE_REVISION'),('account_id','other','ACCOUNT_SCOPE_MISMATCH'),('shares',{'sid:AAA':0},'CHART_NOT_HELD'),('events',[],'CHART_RECORDED_IDENTITY_REQUIRED')]:
            saved=copy.deepcopy(self.state);self.state[field]=value
            with self.assertRaisesRegex(ValueError,error):self.bars()
            self.state=saved
        self.state['events'][0]['payload']['identity_evidence']['ticker']='BBB'
        with self.assertRaisesRegex(ValueError,'CHART_IDENTITY_MISMATCH'):self.bars()

    def test_source_hash_path_and_concurrent_account_change(self):
        with (self.fixture.root/'AAA.json').open('ab') as stream:stream.write(b' ')
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_CHANGED'):self.bars()
        self.fixture.publish(source='../AAA.json');self.configure()
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_PATH_INVALID'):self.bars()
        self.fixture.publish();self.configure();read=self.charts.reader._read
        def changed(name,digest):
            raw=read(name,digest)
            if name=='AAA.json':self.state['revision']='b'*64
            return raw
        self.charts.reader._read=changed
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):self.bars()

    def test_readonly_api_query_binding(self):
        calls=[]
        app=FastAPI();app.include_router(create_router(charts=self.charts,validate_runtime=lambda:calls.append('pin')));client=TestClient(app)
        query='/api/strategy-account/holding-bars?account_revision='+('a'*64)+'&security_id=sid:AAA'
        response=client.get(query);self.assertEqual(response.status_code,200)
        self.assertEqual(calls,['pin','pin'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        for suffix in ('&target_id=x','&security_id=sid:BBB','&bars=261','&interval=minute'):
            self.assertEqual(client.get(query+suffix).status_code,422)
        self.state['revision']='b'*64;self.assertEqual(client.get(query).status_code,409)

    def test_runtime_recheck_blocks_changed_sources(self):
        calls=[]
        def verify():
            calls.append(1)
            if len(calls)>1:raise ValueError('RUNTIME_CHANGED')
        app=FastAPI();app.include_router(create_router(charts=self.charts,validate_runtime=verify))
        response=TestClient(app).get('/api/strategy-account/holding-bars',params={'account_revision':'a'*64,'security_id':'sid:AAA'})
        self.assertEqual(response.status_code,422);self.assertEqual(response.json()['reason'],'RUNTIME_CHANGED')


if __name__=='__main__':unittest.main()
