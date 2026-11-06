import copy
import json
from hashlib import sha256
from test_strategy_account_holding_charts import HoldingTests

class SourcePriorityTests(HoldingTests):
    def older_source(self, conflict=False):
        raw=copy.deepcopy(self.fixture.raw);result=raw['chart']['result'][0]
        result['meta'].update(exchangeName='NMS',fullExchangeName='NasdaqGS')
        result['timestamp']=result['timestamp'][:3]
        quote=result['indicators']['quote'][0]
        for key in quote:quote[key]=quote[key][:3]
        if conflict:quote['close'][0]=10
        blob=json.dumps(raw).encode();(self.fixture.root/'older.json').write_bytes(blob)
        return {'sid:AAA':dict(ticker='AAA',path='older.json',sha256=sha256(blob).hexdigest(),as_of='2026-10-02',captured_at='2026-10-03T00:00:00Z')}

    def test_old_display_cannot_regress_approved_training(self):
        self.configure(self.older_source());result=self.bars()
        self.assertEqual(result['as_of'],'2026-10-05');self.assertFalse(result['display_source_independent'])
        self.assertEqual([row['close'] for row in result['bars']],[11,12,13,14])

    def test_old_display_coordinate_or_hash_conflict_rejects(self):
        self.configure(self.older_source(True))
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_COORDINATE_CONFLICT'):self.bars()
        source=self.older_source();source['sid:AAA']['sha256']='0'*64;self.configure(source)
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_CHANGED'):self.bars()
