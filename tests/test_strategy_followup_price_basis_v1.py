from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from unittest import TestCase
from data.strategy_followup_price_basis_v1 import review_price_basis


class PriceBasisTests(TestCase):
    def fixture(self):
        days=[datetime(2026,9,1,14,tzinfo=timezone.utc)+timedelta(days=i) for i in range(20)]
        closes=[100+i for i in range(20)]
        source=dict(meta=dict(symbol='TEST',currency='USD',exchangeName='NMS',instrumentType='EQUITY'),
            timestamp=[int(d.timestamp()) for d in days],events={},
            indicators=dict(quote=[dict(close=closes)],adjclose=[dict(adjclose=closes.copy())]))
        history=dict(source_reference='raw', units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
            currency='USD',unit_asof='2026-09-20',review_reference='units',basis_id='conditional'),
            closes=[dict(date=d.date().isoformat(),close=str(c)) for d,c in zip(days,closes)])
        return dict(signal_date='2026-09-20',histories={'sid':history}),source

    def review(self,inputs,source):
        return review_price_basis(inputs,{'raw':json.dumps(dict(chart=dict(error=None,result=[source]))).encode(),'units':b'{}'})

    def test_exact_prices_remain_conditional(self):
        inputs,source=self.fixture(); before=deepcopy(inputs)
        result=self.review(inputs,source)
        self.assertEqual(result['securities']['sid']['checked_sessions'],20)
        self.assertFalse(result['capture_admitted']); self.assertFalse(result['performance_computed'])
        self.assertEqual(inputs,before)

    def test_adjustment_or_action_rejected(self):
        inputs,source=self.fixture();source['indicators']['adjclose'][0]['adjclose'][0]=50
        with self.assertRaisesRegex(ValueError,'ADJUSTMENT_DIFFERENCE'): self.review(inputs,source)
        inputs,source=self.fixture();source['events']={'splits':{'date':{'ratio':'2:1'}}}
        with self.assertRaisesRegex(ValueError,'VISIBLE_CORPORATE_ACTION'): self.review(inputs,source)

    def test_wrong_normalization_or_missing_day_rejected(self):
        inputs,source=self.fixture();inputs['histories']['sid']['closes'][0]['close']='99'
        with self.assertRaisesRegex(ValueError,'NORMALIZATION_DIFFERENCE'): self.review(inputs,source)
        inputs,source=self.fixture();source['timestamp'][0]-=86400
        with self.assertRaisesRegex(ValueError,'WINDOW_INCOMPLETE'): self.review(inputs,source)

    def test_wrong_currency_and_duplicate_rejected(self):
        inputs,source=self.fixture();source['meta']['currency']='CAD'
        with self.assertRaisesRegex(ValueError,'PRICE_IDENTITY'): self.review(inputs,source)
        inputs,source=self.fixture();source['timestamp'][1]=source['timestamp'][0]
        with self.assertRaisesRegex(ValueError,'DUPLICATE_PRICE_DATE'): self.review(inputs,source)
