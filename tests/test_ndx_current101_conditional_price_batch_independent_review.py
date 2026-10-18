from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from scripts import ndx_current101_conditional_price_batch_20260919 as batch


class IndependentResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Expand an already saved two-session fixture in memory from its hard
        # raw receipt; no guard reconstruction or new batch artifact is run.
        result = json.loads((batch.BASE / 'current_receipt_quote_guard_20260919_v1/aapl_two_session_probe.json').read_bytes())
        result['schema'] = 'CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1'
        result.update(registry_event_count=28, registry_guard_eligible_event_count=26)
        result['additional_complex_tickers_blocked'] = sorted(batch.guard.ADDITIONAL_BLOCKED)
        sources = result['historical_expected_source_hashes']
        batch.GAP.merge(sources, {str(batch.guard.SOURCE): batch.guard.LOADED, str(batch.guard.FACT): batch.guard.FACT_SHA})
        batch.GAP.attach_partition(result, sources, batch.GAP.partition(sources, batch.GAP.drift.load_contract(), require_all=True))
        raw_ref = result['raw_decoding_evidence']
        raw = Path(raw_ref['raw_path']).read_bytes()
        data = batch.decode(raw)
        if data.get('events', {}).get('splits'):
            raise ValueError('This independent counterexample requires the actual no-split AAPL receipt')
        task = dict(ticker='AAPL', mode='NEW_CONDITIONAL_RECONSTRUCTION', raw_path=raw_ref['raw_path'],
                    raw_sha256=raw_ref['raw_sha256'], received_at_utc=result['original_received_at_utc'],
                    exclude_on_or_after=result['receipt_day_excluded'])
        q = data['indicators']['quote'][0]
        template = result['reconstruction']['rows'][0]
        rows = []
        for i, timestamp in enumerate(data['timestamp']):
            day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(batch.guard.previous.nominal.NEW_YORK).date().isoformat()
            if day >= task['exclude_on_or_after']:
                continue
            row = dict(template, session=day, provider_timestamp=timestamp, quote_open=q['open'][i], quote_close=q['close'][i],
                       nominal_open=q['open'][i], nominal_close=q['close'][i])
            rows.append(row)
        result['reconstruction'].update(rows=rows, row_count=len(rows))
        cls.task = task
        cls.plan = dict(historical_expected_source_hashes=sources)
        cls.document = dict(task, status='CONDITIONAL_PRICE_NOT_IDENTITY', result=result, plan_sha256='fixture',
                            decimal_audit=batch.decimal_audit(raw, rows), **{k: False for k in batch.FALSE_FIELDS})
        batch.validate_saved(cls.document, cls.task, cls.plan, 'fixture')

    def test_nested_identity_upgrade_rejected(self):
        value = deepcopy(self.document)
        value['result']['reconstruction']['provider_price_identity_verified'] = True
        with self.assertRaises(ValueError):
            batch.validate_saved(value, self.task, self.plan, 'fixture')

    def test_nested_unknown_basis_rejected(self):
        value = deepcopy(self.document)
        value['result']['reconstruction']['quote_field_basis'] = 'TOTAL_RETURN_ADJCLOSE'
        with self.assertRaises(ValueError):
            batch.validate_saved(value, self.task, self.plan, 'fixture')

    def test_reported_factor_corruption_rejected_even_when_prices_are_correct(self):
        value = deepcopy(self.document)
        value['result']['reconstruction']['rows'][0]['split_factor'] = 999
        value['result']['reconstruction']['rows'][0]['split_factor_numerator'] = '999'
        with self.assertRaises(ValueError):
            batch.validate_saved(value, self.task, self.plan, 'fixture')

    def test_saved_official_event_match_cannot_be_invented(self):
        value = deepcopy(self.document)
        value['result']['matched_specific_events'] = [{'forged_official_fact': True}]
        value['result']['known_in_request_event_dates'] = ['1999-01-01']
        with self.assertRaises(ValueError):
            batch.validate_saved(value, self.task, self.plan, 'fixture')


if __name__ == '__main__':
    unittest.main()
