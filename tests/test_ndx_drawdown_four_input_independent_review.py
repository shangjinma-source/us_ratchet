from copy import deepcopy
import hashlib
import json
import unittest
from scripts import ndx_drawdown_four_input_assembly_20260923 as m
import test_ndx_drawdown_four_input_assembly_20260923 as fixtures


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.AssemblyTests.setUpClass();cls.docs=fixtures.AssemblyTests.documents;cls.raw=fixtures.AssemblyTests.raw

    def changed(self,edit):
        doc=json.loads(self.raw);edit(doc['chart']['result'][0]);raw=json.dumps(doc).encode()
        metadata=deepcopy(self.docs['metadata']);metadata.update(response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw))
        return raw,metadata

    def test_short_calendar_cannot_claim_214_cells(self):
        calendar=self.docs['benchmark']['calendar'][:21]
        with self.assertRaises(ValueError):m.decode_enph(self.raw,self.docs['metadata'],calendar)

    def test_missing_events_is_explicit_uncertainty_not_completeness(self):
        raw,metadata=self.changed(lambda d:d.pop('events',None))
        result=m.decode_enph(raw,metadata,self.docs['benchmark']['calendar'])
        self.assertFalse(result['raw_events_field_present'])
        self.assertEqual(result['event_scope'],'ABSENT_OR_EMPTY_RETURNED_EVENTS_NOT_COMPLETE_ACTION_HISTORY')
        self.assertEqual(len(result['rows'])*2,214)
        for event in ({'dividends':{'1':{'amount':1}}},{'splits':{}}):
            raw,metadata=self.changed(lambda d:d.update(events=event))
            with self.assertRaises(ValueError):m.decode_enph(raw,metadata,self.docs['benchmark']['calendar'])

    def test_wrong_instrument_or_frequency_rejected(self):
        for key,value in [('instrumentType','ETF'),('dataGranularity','1wk')]:
            raw,metadata=self.changed(lambda d:d['meta'].update({key:value}))
            with self.assertRaises(ValueError):m.decode_enph(raw,metadata,self.docs['benchmark']['calendar'])

    def test_bool_price_and_duplicate_raw_key_rejected(self):
        def change(doc):
            from datetime import datetime,timezone
            i=next(i for i,t in enumerate(doc['timestamp']) if datetime.fromtimestamp(t,timezone.utc).date().isoformat()=='2023-03-31')
            doc['indicators']['quote'][0]['open'][i]=True
        raw,metadata=self.changed(change)
        with self.assertRaises(ValueError):m.decode_enph(raw,metadata,self.docs['benchmark']['calendar'])
        with self.assertRaises(ValueError):json.loads('{"a":1,"a":2}',object_pairs_hook=m.unique)

    def test_shared_energy_and_identity_interval_never_upgraded(self):
        result=m.assemble(self.docs,self.raw)
        for mapping in result['selected_risk_chains_by_decision'].values():
            self.assertEqual(mapping['security:0001701605:05722G100'],mapping['security:0001463101:29355A107'])
        self.assertEqual(result['identity_projection']['enph_original_conditional_window']['end'],'2023-05-01')
        self.assertFalse(result['identity_projection']['enph_original_interval_certification_extended'])
        self.assertTrue(all(result[key] is False for key in m.FALSE))


if __name__=='__main__':unittest.main()
