"""Synthetic declaration contracts; never actual build/publish."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_orly_conditional_identity_risk_20260925 as m


def fixture():
    docs={}
    for role,(p,h) in m.BOUND.items():
        if role in ('config','snapshot','taxonomy'):docs[role]=m.yaml.safe_load(p.read_bytes())
        elif role in ('registry','manifest','index','capture_started','form_started','form_receipt','occ_started','occ_receipt'):docs[role]=json.loads(p.read_bytes())
    blobs={k:b'synthetic' for k in m.BOUND}
    context=f'<xbrli:context id="{m.CONTEXT}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000898173</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startdate>2025-01-01</xbrli:startdate><xbrli:enddate>2025-12-31</xbrli:enddate></xbrli:period></xbrli:context>'
    fields=''.join(f'<ix:nonnumeric name="{k}" contextref="{m.CONTEXT}">{v}</ix:nonnumeric>' for k,v in [('dei:EntityCentralIndexKey','0000898173'),('dei:Security12bTitle','Common Stock'),('dei:TradingSymbol','ORLY')])
    blobs['annual']=(context+fields+'specialty retailers of automotive aftermarket parts').encode()
    blobs['form_pdf']=b'%PDF-synthetic';blobs['occ_failed_body']=b'<!DOCTYPE html>synthetic403'
    for k in ('page1','page2'):blobs[k]=b'\x89PNG\r\n\x1a\nsynthetic'
    bound={k:(p,m.sha(blobs[k])) for k,(p,h) in m.BOUND.items()}
    docs['snapshot']['source_seed_sha256']=bound['config'][1]
    review=m.one(docs['snapshot']['decisions'],'decision_id','current:ORLY');review['raw_sha256']=bound['annual'][1]
    docs['manifest']['content_sha256']=bound['annual'][1];docs['registry']['events'][20]['raw_sha256']=bound['faq'][1]
    for role,body in [('form','form_pdf'),('occ','occ_failed_body')]:
        docs[role+'_receipt']['raw_reference']=dict(path=str(bound[body][0]),sha256=bound[body][1],byte_count=len(blobs[body]))
    docs['index']['receipts']=[deepcopy(docs['occ_receipt']),deepcopy(docs['form_receipt'])]
    return docs,blobs,bound


class Tests(unittest.TestCase):
    def assemble(self,docs,blobs,bound,pages=None):
        with patch.object(m,'BOUND',bound):return m.assemble(docs,blobs,['',''] if pages is None else pages)

    def test_visual_facts_not_parser_publication_or_cik(self):
        docs,blobs,bound=fixture();r=self.assemble(docs,blobs,bound)
        self.assertEqual(r['coordinate']['cusip'],'67103H107')
        visual=r['complete_visual_transcription'];self.assertEqual(visual['cusip_original_text'],'67103H 107')
        self.assertIsNone(r['publication_date']);self.assertEqual(r['action_date'],r['signature_date'])
        self.assertTrue(visual['visual_transcription_is_not_text_parser_output'])
        self.assertFalse(visual['ein_used_as_cik']);self.assertFalse(r['direct_single_document_cusip_cik_proof'])
        self.assertIsNone(r['original_faq_registry_event']['cusip']);self.assertIsNone(r['original_faq_registry_event']['publication_date'])
        self.assertFalse(r['complete_capture_evidence']['occ_local_pdf_available'])
        self.assertEqual(r['complete_capture_evidence']['occ_receipt']['http_status'],403)
        self.assertTrue(all(r[k] is False for k in m.FALSE))

    def test_pdf_text_layer_or_page_replacement_rejected(self):
        docs,blobs,bound=fixture()
        with self.assertRaises(ValueError):self.assemble(docs,blobs,bound,['CUSIP 67103H107',''])
        blobs['page1']+=b'changed'
        with self.assertRaises(ValueError):self.assemble(docs,blobs,bound)

    def test_cannot_upgrade_occ_failure_old_faq_or_current_ticker(self):
        for attack in ('occ','faq','ticker','publication'):
            docs,blobs,bound=fixture()
            if attack=='occ':docs['occ_receipt']['http_status']=200;docs['index']['receipts'][0]=deepcopy(docs['occ_receipt'])
            elif attack=='faq':docs['registry']['events'][20]['cusip']='67103H107'
            elif attack=='publication':docs['registry']['events'][20]['publication_date']='2025-06-09'
            else:m.one(docs['snapshot']['decisions'],'decision_id','current:ORLY')['security_ids']=['security:0000898173:67103H107']
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.assemble(docs,blobs,bound)

    def test_early_clock_and_review_backdating_rejected(self):
        for attack in ('review','clock','attempt'):
            docs,blobs,bound=fixture()
            if attack=='review':m.one(docs['snapshot']['decisions'],'decision_id','current:ORLY')['selection_date']='2026-02-27'
            elif attack=='clock':docs['form_receipt']['received_at_utc']='2026-09-24T17:37:33.511356'
            else:docs['form_receipt']['attempt']=True
            docs['index']['receipts'][1]=deepcopy(docs['form_receipt'])
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.assemble(docs,blobs,bound)

    def test_cover_context_or_class_conflict(self):
        docs,blobs,bound=fixture()
        for a,b in [(b'Common Stock',b'Preferred Stock'),(b'>0000898173</xbrli:identifier>',b'>9999999999</xbrli:identifier>')]:
            with self.subTest(a=a),self.assertRaises(ValueError):m.cover_facts(blobs['annual'].replace(a,b))

    def test_actual_pins_and_cover_parser_only(self):
        for p,h in m.BOUND.values():self.assertEqual(m.sha(p.read_bytes()),h)
        result=m.cover_facts(m.BOUND['annual'][0].read_bytes())
        self.assertEqual(result['business_phrase_offsets'],[24044])

    def test_existing_namespace_and_loaded_source_conflict(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)/'declaration.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        path=next(iter(m.LOADED))
        with self.assertRaises(ValueError):m.guard({path:'f'*64})

if __name__=='__main__':unittest.main()
