from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from data.strategy_halt_aware_pullback_sources_v1 import candidate_from_yahoo_bytes
from test_current_quantity_v2_pullback_sources import payload, epoch


def fixture():
    data=payload(); result=data['chart']['result'][0]
    result['timestamp']=[epoch('09:'+str(i)+':00') for i in range(30,36)]
    result['meta']['regularMarketTime']=epoch('09:36:14')
    result['indicators']['quote'][0]={key:[100]*6 for key in ('open','high','low','close','volume')}
    return data


def invoke(data, **changes):
    raw=json.dumps(data).encode()
    args=dict(raw=raw, expected_sha256=sha256(raw).hexdigest(),security_id='SNDK-ID',
        ticker='SNDK',session='2026-10-15',session_open='2026-10-15T09:30:00-04:00',
        session_close='2026-10-15T16:00:00-04:00',captured_at='2026-10-15T09:36:15-04:00',
        checked_at='2026-10-15T09:36:16-04:00',now='2026-10-15T09:36:17-04:00',
        rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120,previous_cap=None)
    args.update(changes)
    return candidate_from_yahoo_bytes(**args)


class HaltSourceTests(unittest.TestCase):
    def evidence(self):
        from data.strategy_halt_gap_diagnostic_v1 import SOURCE_URL, HEADER
        raw=('<html>All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+
             '</tr><tr>'+''.join('<td>'+x+'</td>' for x in ['SNDK','SANDISK CORP','NASDAQ',
             '10/15/2026 09:30:54','Volatility Pause','10/15/2026','','09:33:54'])+'</tr></table></html>').encode()
        return dict(halt_raw=raw, halt_receipt=dict(url=SOURCE_URL,http_status=200,bytes=len(raw),
            raw_sha256=sha256(raw).hexdigest(),started_at='2026-10-15T09:35:58-04:00',
            received_at='2026-10-15T09:35:59-04:00'))

    def null_data(self):
        data=fixture()
        for values in data['chart']['result'][0]['indicators']['quote'][0].values():
            values[1]=values[2]=None
        return data

    def test_no_halt_retains_normal_bars(self):
        result=invoke(fixture())
        self.assertEqual(len(result['reference']['bars']),6)
        self.assertEqual(result['reference']['halt_intervals'],[])
        self.assertEqual(result['candidate']['observed_session_low'],'100')

    def test_missing_evidence_cannot_explain_nulls(self):
        with self.assertRaisesRegex(ValueError,'UNEXPLAINED_NULL_MINUTE'):invoke(self.null_data())

    def test_pair_required(self):
        with self.assertRaisesRegex(ValueError,'HALT_EVIDENCE_PAIR_REQUIRED'):invoke(fixture(),halt_raw=b'x')

    def test_verified_nulls_are_not_candles(self):
        result=invoke(self.null_data(),**self.evidence())
        self.assertEqual(len(result['reference']['bars']),4)
        self.assertEqual(result['receipt']['excluded_rows']['verified_halt_null_minutes'],2)
        self.assertTrue(all(not b['synthetic'] for b in result['reference']['bars']))
        self.assertEqual(result['candidate']['observed_session_low'],'100')
        self.assertEqual(result['receipt']['halt_raw_sha256'],result['reference']['source_hashes']['halt_raw'])
        self.assertEqual(result['receipt']['halt_receipt_digest'],result['reference']['source_hashes']['halt_receipt'])

    def test_missing_timestamps_only_covered_by_halt(self):
        data=fixture(); r=data['chart']['result'][0]
        for arr in [r['timestamp'],*r['indicators']['quote'][0].values()]:del arr[1:3]
        self.assertEqual(len(invoke(data,**self.evidence())['reference']['bars']),4)
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS'):invoke(data)

    def test_partial_null_still_fails(self):
        data=self.null_data();data['chart']['result'][0]['indicators']['quote'][0]['volume'][1]=0
        with self.assertRaisesRegex(ValueError,'PARTIAL_NULL_MINUTE'):invoke(data,**self.evidence())

    def test_boundary_minute_not_covered(self):
        data=self.null_data()
        for values in data['chart']['result'][0]['indicators']['quote'][0].values():values[3]=None
        with self.assertRaisesRegex(ValueError,'UNEXPLAINED_NULL_MINUTE'):invoke(data,**self.evidence())

    def test_trade_during_wholly_halted_minute_conflicts(self):
        with self.assertRaisesRegex(ValueError,'HALT_BAR_OVERLAP'):invoke(fixture(),**self.evidence())

    def test_receipt_tamper_rejected(self):
        evidence=self.evidence();evidence['halt_receipt']['raw_sha256']='0'*64
        with self.assertRaises(ValueError):invoke(self.null_data(),**evidence)


if __name__=='__main__':unittest.main()
