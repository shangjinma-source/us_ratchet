"""Bounded CTAS parser/metadata tests; no build, publish or HTTP."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from scripts import ndx_ctas_conditional_identity_risk_20260925 as m


def html():
    context='<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000723254</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-06-01</xbrli:startDate><xbrli:endDate>2025-05-31</xbrli:endDate></xbrli:period></xbrli:context>'
    fields=''.join(f'<ix:nonNumeric name="dei:{k}" contextRef="c-1">{v}</ix:nonNumeric>' for k,v in [('EntityCentralIndexKey','0000723254'),('EntityRegistrantName','Cintas Corporation'),('TradingSymbol','CTAS'),('Security12bTitle',m.TITLE)])
    return (context+fields+' uniforms, mats, mops, shop towels').encode()


def pages():return ['#55082 August 21, 2024 100 Cintas Corporation (CTAS) Common Shares CUSIP:172908105 09/12/2024 4 for 1 stock split','','unofficial summary','continued disclaimer']


def documents():
    result={}
    for k in ('config','snapshot','taxonomy','manifest','registry','capture_started','capture_receipt','extraction'):
        b=m.BOUND[k][0].read_bytes();result[k]=yaml.safe_load(b) if k in ('config','snapshot','taxonomy') else json.loads(b)
    return result


class Tests(unittest.TestCase):
    def test_hard_inputs_byte_pins(self):
        for k,(p,h) in m.BOUND.items():self.assertEqual(m.sha(p.read_bytes()),h,k)
    def test_cover_same_cik_context_not_ticker_inference(self):
        value=m.cover_facts(html());self.assertEqual(value['entity_cik'],'0000723254')
        for b in (html().replace(b'0000723254',b'0000000000',1),html().replace(b'name="dei:TradingSymbol" contextRef="c-1"',b'name="dei:TradingSymbol" contextRef="other"'),html().replace(b'Common stock, no par value',b'Preferred stock')):
            with self.assertRaises(ValueError):m.cover_facts(b)
    def test_memo_same_page_and_third_page_disclaimer(self):
        self.assertEqual(m.memo_facts(pages())['publication_date'],'2024-08-21')
        for attack in ('cusip','class','disclaimer','count'):
            p=pages()
            if attack=='cusip':p[0]=p[0].replace('CUSIP:172908105','');p[1]='CUSIP:172908105'
            elif attack=='class':p[0]=p[0].replace('Common Shares','Options')
            elif attack=='disclaimer':p[2]='official certification'
            else:p.pop()
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.memo_facts(p)
    def test_saved_multipart_exact_and_metadata_tampering(self):
        d=documents();raw=m.BOUND['memo_raw'][0].read_bytes();pdf=m.BOUND['memo'][0].read_bytes()
        self.assertTrue(m.multipart_evidence(raw,pdf,d)['strict_single_part_payload_exact'])
        for attack in ('offset','status','source','retry'):
            bad=deepcopy(d)
            if attack=='offset':bad['extraction']['payload_start_offset']=194
            elif attack=='status':bad['capture_receipt']['http_status']=True
            elif attack=='source':bad['capture_receipt']['body_reference']['sha256']='0'*64
            else:bad['capture_started']['retry_allowed']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.multipart_evidence(raw,pdf,bad)
        with self.assertRaises(ValueError):m.multipart_evidence(raw,pdf+b'!',d)
    def test_assembly_preserves_old_null_and_late_availability(self):
        d=documents();annual=m.BOUND['annual'][0].read_bytes();capture=dict(strict_single_part_payload_exact=True,original_receipt=d['capture_receipt'])
        with patch.object(m,'cover_facts',return_value={'synthetic':'covered'}),patch.object(m,'memo_facts',return_value={'synthetic':'memo'}):
            value=m.assemble(d,annual,[],capture)
            self.assertIsNone(value['registry_event']['cusip']);self.assertIsNone(value['registry_event']['publication_date'])
            self.assertEqual(value['coordinate']['cusip'],'172908105');self.assertEqual(value['risk_chain'],'industrial')
            self.assertTrue(value['saved_review_selection_postdates_window_start'])
            self.assertTrue(all(value[k] is False for k in m.FALSE))
            bad=deepcopy(d);bad['snapshot']['decisions']=[dict(x,selection_date='2025-07-28') if x['decision_id']=='current:CTAS' else x for x in bad['snapshot']['decisions']]
            with self.assertRaises(ValueError):m.assemble(bad,annual,[],capture)
    def test_namespace_guard_prevents_any_build(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'OUTPUT',Path(d)/'declaration.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with self.assertRaises(ValueError):m.guard({str(m.SOURCE):'0'*64})

if __name__=='__main__':unittest.main()
