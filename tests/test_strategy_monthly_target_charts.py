import copy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts


class ChartsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.days = ['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']
        self.raw = {'chart': {'error': None, 'result': [{
            'meta': dict(symbol='AAA', currency='USD', instrumentType='EQUITY',
                         exchangeTimezoneName='America/New_York', dataGranularity='1d'),
            'timestamp': [int(datetime.fromisoformat(day+'T20:00:00+00:00').timestamp()) for day in self.days],
            'indicators': {'quote': [dict(open=[10, 11, 12, 13, 99], high=[12, 13, 14, 15, 101],
                low=[9, 10, 11, 12, 98], close=[11, 12, 13, 14, 100], volume=[1, 2, 3, 4, 5])]},
        }]}}
        self.publish()
        self.reads = 0
        class Store:
            def current(inner):
                self.reads += 1
                return copy.deepcopy(self.target)
        self.store = Store()
        self.charts = StrategyMonthlyTargetCharts(root=self.root, target_service=self.store)

    def publish(self, *, quantity=4, source='AAA.json'):
        raw = canonical(self.raw)
        (self.root/'AAA.json').write_bytes(raw)
        digest = sha256(raw).hexdigest()
        manifest = dict(decision_date='2026-10-05', source_hashes={source: digest}, candidates=[
            dict(security_id='sid:AAA', ticker='AAA', status='READY_CONDITIONAL', training_source=source)])
        manifest_raw = canonical(manifest)
        (self.root/'manifest.json').write_bytes(manifest_raw)
        binding = dict(training_cutoff_date='2026-10-05', documents={'training_manifest':'manifest.json'},
            source_hashes={'manifest.json':sha256(manifest_raw).hexdigest(), source:digest},
            search_arguments={'metadata':{'sid:AAA':{'ticker':'AAA'}}})
        decision_payload = dict(input_binding=binding, input_id=sha256(canonical(binding)).hexdigest(),
                                target_quantities={'sid:AAA':quantity})
        payload = dict(decision={'payload':decision_payload, 'decision_id':sha256(canonical(decision_payload)).hexdigest()},
                       target_quantities={'sid:AAA':quantity})
        self.target = dict(payload=payload, target_id=sha256(canonical(payload)).hexdigest())

    def bars(self, **kwargs):
        return self.charts.bars(target_id=self.target['target_id'], security_id='sid:AAA', **kwargs)

    def test_actual_daily_weekly_monthly_and_cutoff(self):
        daily = self.bars()
        self.assertEqual([r['date'] for r in daily['bars']], self.days[:4])
        weekly = self.bars(interval='week')['bars']
        self.assertEqual([(r['open'],r['high'],r['low'],r['close'],r['volume']) for r in weekly],
                         [(10,14,9,13,6),(13,15,12,14,4)])
        monthly = self.bars(interval='month')['bars']
        self.assertEqual([(r['open'],r['high'],r['low'],r['close'],r['volume']) for r in monthly],
                         [(10,12,9,11,1),(11,15,10,14,9)])
        self.assertFalse(daily['limit_line_coordinate_confirmed'])
        self.assertEqual(len(self.bars(bars=1)['bars']),1)

    def test_stale_nonmember_zero_and_arguments(self):
        with self.assertRaisesRegex(ValueError,'STALE_TARGET'):
            self.charts.bars(target_id='0'*64,security_id='sid:AAA')
        with self.assertRaisesRegex(ValueError,'CHART_NOT_SELECTED'):
            self.charts.bars(target_id=self.target['target_id'],security_id='sid:BBB')
        self.publish(quantity=0)
        with self.assertRaisesRegex(ValueError,'CHART_NOT_SELECTED'):self.bars()
        for kwargs in ({'interval':'minute'},{'bars':True},{'bars':261}):
            with self.assertRaisesRegex(ValueError,'CHART_ARGUMENTS_INVALID'):self.bars(**kwargs)

    def test_tampered_raw_and_manifest(self):
        for name in ('AAA.json','manifest.json'):
            self.publish()
            with (self.root/name).open('ab') as stream:stream.write(b' ')
            with self.assertRaisesRegex(ValueError,'CHART_SOURCE_CHANGED'):self.bars()

    def test_tampered_target_and_unsafe_bound_path(self):
        self.target['payload']['target_quantities']['sid:AAA']=5
        with self.assertRaisesRegex(ValueError,'CHART_TARGET_CHANGED'):self.bars()
        self.publish(source='../AAA.json')
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_PATH_INVALID'):self.bars()

    def test_missing_ohlc_not_filled_and_cutoff_required(self):
        quote=self.raw['chart']['result'][0]['indicators']['quote'][0]
        quote['open'][1]=None
        self.publish()
        result=self.bars()
        self.assertEqual(result['missing_sessions'],['2026-10-01'])
        self.assertEqual(len(result['bars']),3)
        quote['close'][3]=None
        self.publish()
        with self.assertRaisesRegex(ValueError,'CHART_CUTOFF_OHLC_MISSING'):self.bars()

    def test_target_changes_during_read(self):
        original=self.charts._read
        def read(name,digest):
            raw=original(name,digest)
            if name=='AAA.json':self.target['target_id']='0'*64
            return raw
        self.charts._read=read
        with self.assertRaisesRegex(ValueError,'STALE_TARGET'):self.bars()


if __name__=='__main__':unittest.main()
