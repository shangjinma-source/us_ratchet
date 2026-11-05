from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates.split_monthly_raw_history_20261105 import normalize_monthly_raw
import test_monthly_peak_exit_history as fixtures


class SplitRawHistoryTests(unittest.TestCase):
    def arguments(self,basis='AS_TRADED',last=10):
        inputs=fixtures.MonthlyHistoryTests().inputs();dates=inputs['session_dates']
        inputs['base_target']['price_units']['A']='post8'
        inputs['histories']['A']['units']['basis_id']='post8'
        times=[int(datetime.fromisoformat(day+'T13:30:00+00:00').timestamp()) for day in dates]
        closes=[100,12.5,last] if basis=='AS_TRADED' else [12.5,12.5,last]
        series=dict(meta=dict(symbol='TEST',currency='USD',exchangeName='NMS',instrumentType='EQUITY'),
            timestamp=times,indicators=dict(quote=[dict(close=closes)],adjclose=[dict(adjclose=[9,9,8])]),
            events=dict(splits={'s':dict(date=times[1],numerator=8.0,denominator=1.0,splitRatio='8:1')},
                        dividends={'d':dict(date=times[2],amount=.1)}))
        raw=json.dumps(dict(chart=dict(error=None,result=[series]))).encode();digest=sha256(raw).hexdigest()
        review=dict(security_id='A',raw_sha256=digest,review_reference='synthetic-caller-review',
            price_basis=basis,basis_asof=inputs['observed_at'],captured_at=inputs['observed_at'],current_unit_id='post8',
            split_schedule=[dict(action_id='synthetic-split',security_id='A',ratio=8,old_unit_id='pre8',new_unit_id='post8',
                                 quote_unit_effective_at=dates[1]+'T13:30:00+00:00')],
            reviewed_dividends=[dict(date=dates[2],provider_amount='0.1')])
        return dict(inputs=inputs,sources={'A':raw},expected_hashes={'A':digest},
                    identities={'A':dict(ticker='TEST',exchange='NMS')},reviews={'A':review})

    def test_both_coordinates_same_real_risk_no_double_adjust_and_true_exit(self):
        for last,exited in ((12.5,[]),(10,['A'])):
            outputs=[]
            for basis in ('AS_TRADED','SPLIT_ADJUSTED_TO_CURRENT_UNIT'):
                arguments=self.arguments(basis,last);before=deepcopy(arguments)
                normalized=normalize_monthly_raw(**arguments)
                self.assertEqual(arguments,before)
                self.assertFalse(normalized['source_authenticated'])
                self.assertFalse(normalized['dividends_in_price_risk'])
                self.assertEqual(normalized['observations'][0]['closes']['A'],'25/2')
                self.assertIn('dividends',normalized['original_events']['A'])
                with TemporaryDirectory() as directory:
                    store=MonthlyPeakExitStore(Path(directory)/'risk.sqlite3')
                    applied=store.advance(account_id='synthetic',expected_previous_session=None,
                        observations=normalized['observations'],baseline_targets={'A':10})
                    self.assertEqual(applied['state']['exited'],exited)
                    self.assertEqual(applied['state']['peaks']['A'],'25/2')
                    outputs.append(normalized['observations'])
            self.assertEqual(*outputs)

    def test_wrong_date_missing_basis_unknown_dividend_and_incomplete_reject(self):
        args=self.arguments()
        wrong=deepcopy(args);wrong['reviews']['A']['split_schedule'][0]['quote_unit_effective_at']='2026-10-01T20:00:00+00:00'
        missing=deepcopy(args);del missing['reviews']['A']['price_basis']
        dividend=deepcopy(args);dividend['reviews']['A']['reviewed_dividends']=[]
        short=deepcopy(args);doc=json.loads(short['sources']['A']);series=doc['chart']['result'][0]
        del series['timestamp'][-1];del series['indicators']['quote'][0]['close'][-1]
        raw=json.dumps(doc).encode();short['sources']['A']=raw
        short['expected_hashes']['A']=short['reviews']['A']['raw_sha256']=sha256(raw).hexdigest()
        for case,reason in [(wrong,'RAW_SPLIT_SCHEDULE_MISMATCH'),(missing,'EXPLICIT_RAW_PRICE_BASIS_REQUIRED'),
                            (dividend,'RAW_DIVIDEND_REVIEW_MISMATCH'),(short,'RAW_COMPLETE_WINDOW_REQUIRED')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                normalize_monthly_raw(**case)

    def test_unknown_action_and_conflicting_ratio_rejected(self):
        for action in ('unknown','ratio'):
            args=self.arguments();doc=json.loads(args['sources']['A']);events=doc['chart']['result'][0]['events']
            if action=='unknown':events['capitalGains']={'x':dict(date=1,amount=2)}
            else:events['splits']['s']['splitRatio']='4:1'
            raw=json.dumps(doc).encode();args['sources']['A']=raw
            args['expected_hashes']['A']=args['reviews']['A']['raw_sha256']=sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'UNKNOWN_RAW_ACTION|RAW_SPLIT_RATIO_CONFLICT'):
                normalize_monthly_raw(**args)


if __name__=='__main__':unittest.main()
