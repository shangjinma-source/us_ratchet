from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import review_continuous_guided_metrics as reviewer


class IndependentMetricTests(unittest.TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        previous=sys.get_int_max_str_digits();self.addCleanup(sys.set_int_max_str_digits,previous)
        self.root=Path(self.temporary.name);self.directory=self.root/'comparison';self.directory.mkdir()
        rows=[dict(date='2024-01-02',equity='200'),dict(date='2024-12-31',equity='150'),
              dict(date='2025-01-02',equity='120'),dict(date='2025-01-03',equity='180')]
        pins={}
        for folder in ('daily_exclusion_B0_20261016_v1','continuous_guided_monthly_book_20261016_v1'):
            name=f'tmp/{folder}/outcome.json';path=self.root/name;path.parent.mkdir(parents=True)
            raw=json.dumps(dict(daily_ledger=rows)).encode();path.write_bytes(raw);pins[name]=sha256(raw).hexdigest()
        days=(date(2025,1,3)-date(2023,12,29)).days
        arm=dict(final_equity='180',maximum_close_drawdown='2/5',cagr=1.8**(365/days)-1,
            years=[dict(year=2024,return_fraction='1/2',maximum_close_drawdown='1/4'),
                   dict(year=2025,return_fraction='1/5',maximum_close_drawdown='1/5')])
        self.report=dict(opening_date='2023-12-29',through='2025-01-03',initial_cash='100',source_hashes=pins,
                         arms={'B0':deepcopy(arm),'continuous32':deepcopy(arm)})

    def verify(self):
        (self.directory/'comparison.json').write_text(json.dumps(self.report),encoding='utf-8')
        with patch.object(reviewer,'ROOT',self.root),patch.object(reviewer,'DIRECTORY',self.directory):return reviewer.verify()

    def test_cross_year_carry_and_whole_period_drawdown(self):
        previous_limit=sys.get_int_max_str_digits()
        result=self.verify()
        self.assertEqual(sys.get_int_max_str_digits(),previous_limit)
        self.assertEqual(result['status'],'PASS_INDEPENDENT_NAV_METRICS')
        self.assertEqual(result['arms']['B0']['maximum_close_drawdown'],'2/5')
        self.assertEqual(result['arms']['B0']['sessions'],4)
        self.assertFalse((self.directory/'root_metrics_review.json').exists())

    def test_reset_capital_or_within_year_drawdown_as_full_period_rejected(self):
        original=deepcopy(self.report)
        self.report['arms']['B0']['years'][1]['return_fraction']='4/5'
        with self.assertRaisesRegex(ValueError,'YEAR_METRIC_MISMATCH'):self.verify()
        self.report=deepcopy(original);self.report['arms']['B0']['maximum_close_drawdown']='1/4'
        with self.assertRaisesRegex(ValueError,'WHOLE_PERIOD_METRIC_MISMATCH'):self.verify()

    def test_source_hash_cagr_and_year_tamper_rejected(self):
        original=deepcopy(self.report)
        self.report['source_hashes']['tmp/daily_exclusion_B0_20261016_v1/outcome.json']='0'*64
        with self.assertRaisesRegex(ValueError,'OUTCOME_HASH_MISMATCH'):self.verify()
        self.report=deepcopy(original);self.report['arms']['continuous32']['cagr']=999
        with self.assertRaisesRegex(ValueError,'CAGR_MISMATCH'):self.verify()
        self.report=deepcopy(original);self.report['arms']['B0']['years'].pop()
        with self.assertRaisesRegex(ValueError,'YEAR_COVERAGE_MISMATCH'):self.verify()
        self.report=deepcopy(original);self.report['arms']['B0']['years'].append(deepcopy(self.report['arms']['B0']['years'][0]))
        previous_limit=sys.get_int_max_str_digits()
        with self.assertRaisesRegex(ValueError,'YEAR_COVERAGE_MISMATCH'):self.verify()
        self.assertEqual(sys.get_int_max_str_digits(),previous_limit)


if __name__=='__main__':unittest.main()
