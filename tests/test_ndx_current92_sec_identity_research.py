from copy import deepcopy
import json
from pathlib import Path
import unittest
from backtest import ndx_current92_sec_identity_research as module


class Tests(unittest.TestCase):
    def fixture(self):
        root=Path(__file__).resolve().parents[1]
        value=json.loads((root/'data/cache/research/current101_conditional_issuer_map_20260919_v1/issuer_map.json').read_bytes())
        expected=module.expected_refresh(value);by_cik={}
        for ticker,cik in expected.items():by_cik.setdefault(cik,[]).append(ticker)
        decoded={cik:json.dumps(dict(cik=cik,name='synthetic issuer',tickers=tickers,exchanges=['Nasdaq']*len(tickers))).encode() for cik,tickers in by_cik.items()}
        return value,decoded

    def test_complete_92_and_dual_class_one_issuer(self):
        value,decoded=self.fixture();result=module.refresh_identity_rows(value,decoded)
        self.assertEqual((len(result['rows']),len(result['candidate_facts'])),(92,91))
        goog=[r for r in result['rows'] if r['ticker'] in ('GOOG','GOOGL')]
        self.assertEqual(len(goog),2);self.assertEqual(len({r['current_reported_cik'] for r in goog}),1)
        self.assertEqual({r['reported_ticker_exchange_position'] for r in goog},{0,1})
        self.assertFalse(result['input_artifact_binding_verified'])

    def test_missing_extra_or_wrong_cik_response_reject(self):
        value,decoded=self.fixture();first=next(iter(decoded))
        variants=[dict(decoded),dict(decoded),dict(decoded)]
        variants[0].pop(first);variants[1]['0000000001']=b'{}'
        body=json.loads(variants[2][first]);body['cik']='0000000001';variants[2][first]=json.dumps(body).encode()
        for bad in variants:
            with self.assertRaises(ValueError):module.refresh_identity_rows(value,bad)

    def test_wrong_exchange_position_or_name_only_not_accepted(self):
        value,decoded=self.fixture();cik=next(iter(decoded));body=json.loads(decoded[cik])
        for changes in ({'exchanges':['NYSE']*len(body['tickers'])},{'tickers':['OTHER']*len(body['tickers'])}):
            bad=dict(decoded);bad[cik]=json.dumps(dict(body,**changes)).encode()
            with self.assertRaises(ValueError):module.refresh_identity_rows(value,bad)

    def test_refresh_old_nine_or_type_upgrade_reject(self):
        value,decoded=self.fixture();bad=deepcopy(value)
        bad['rows'][0]['september_current_issuer_observation_available']=1
        with self.assertRaises(ValueError):module.expected_refresh(bad)
        bad=deepcopy(value);bad['latest_sec_refresh_candidate_tickers'].append('SPCX')
        with self.assertRaises(ValueError):module.expected_refresh(bad)


if __name__=='__main__':unittest.main()
