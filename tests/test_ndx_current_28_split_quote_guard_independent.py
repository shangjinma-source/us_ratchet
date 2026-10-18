"""Independent bounded source/event-denominator adversarial checks; no HTTP."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_current_28_split_quote_guard_research as module


class IndependentTests(unittest.TestCase):
    def test_original_twenty_five_exact_and_new_sources_strict(self):
        old=module.previous.gap.load_registry()
        registry=module.load_registry()
        self.assertEqual(json.dumps(registry['events'][:25],sort_keys=True),json.dumps(old['events'],sort_keys=True))
        for path,sha in ((module.SOURCE,module.LOADED),(module.FACT,module.FACT_SHA),(module.FACT_SOURCE,module.FACT_LOADED)):
            self.assertEqual(registry['verified_source_hashes'][str(path)],sha)
        self.assertEqual({r['ticker'] for r in registry['events'][25:]},{'MSTR','SHOP','WMT'})
        self.assertFalse(registry['historical_full_source_closure_verified'])

    def test_resigned_fact_content_cannot_replace_hard_anchor(self):
        read_bytes=Path.read_bytes
        bad=json.loads(module.FACT.read_bytes())
        bad['events'][0]['ticker']='UNKNOWN'
        forged=json.dumps(bad,sort_keys=True).encode()
        def read(path):
            return forged if path==module.FACT else read_bytes(path)
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(ValueError,'Hard three event facts differ'):
                module.load_registry()

    def test_known_event_cannot_be_deleted_and_complex_zero_event_blocked(self):
        registry=module.load_registry()
        events=[r for r in registry['events'] if r['simple_split_guard_eligible']]
        folder=module.previous.BASE/'current_22_price_capture_20260919_v1'
        receipt=json.loads((folder/'MSTR.receipt.json').read_bytes())
        raw,_,request,_=module.previous.load_capture(ticker='MSTR',raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],sources={})
        body=json.loads(raw);body['chart']['result'][0]['events']['splits']={}
        matching=module.previous.gap.addressed.previous.first_guard.match_returned_events(decoded=json.dumps(body).encode(),ticker='MSTR',specific_events=events,blocked_tickers=set())
        with self.assertRaises(ValueError):
            module.previous.gap.addressed.previous.validate_known_event_denominator(ticker='MSTR',matches=matching,events=events,request=request)
        for ticker in ('TRI','WDC','AZN','SIRI','ILMN','LCID','LRCX'):
            with self.subTest(ticker=ticker),patch.object(module,'load_registry',side_effect=AssertionError('Must block before reading event evidence')):
                with self.assertRaisesRegex(ValueError,'blocked'):
                    module.reconstruct_current_receipt_quote(ticker=ticker,raw_path='unused',raw_sha256='unused',calendar=['2026-09-17'],quote_field_basis=module.previous.nominal.BASIS)


if __name__=='__main__':unittest.main()
