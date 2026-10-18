import copy
import unittest
from unittest.mock import patch
from backtest import ndx_saved_sec_cover_evidence_research as module


def fixture(extra=''):
    raw=('''<html><body><xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="SEC">0000000001</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2020-12-31</xbrli:instant></xbrli:period></xbrli:context>
    <xbrli:context id="c2"><xbrli:entity><xbrli:identifier scheme="SEC">0000000001</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="class">ClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity></xbrli:context>
    <ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c1">0000000001</ix:nonNumeric>
    <ix:nonNumeric name="dei:EntityRegistrantName" contextRef="c1">A &amp; B</ix:nonNumeric>
    <ix:nonNumeric name="dei:TradingSymbol" contextRef="c2">ABC</ix:nonNumeric>
    <ix:nonNumeric name="dei:Security12bTitle" contextRef="c2" continuedAt="tail">Class A</ix:nonNumeric>
    <ix:continuation id="tail">ordinary shares</ix:continuation>
    <p>品牌 &amp; Unicode</p><p>品牌 &amp; Unicode</p>'''+extra+'</body></html>').encode()
    return raw,{'path':'saved.html','sha256':module.sha(raw)}, {'expected_raw_sha256':module.sha(raw),
        'phrase_queries':['品牌 & Unicode'],'risk_chain':'saved_late_decision','claimed_section_hash':'not_reverified'}


class CoverTests(unittest.TestCase):
    def test_contexts_continuation_and_all_phrase_positions(self):
        args=fixture(); before=copy.deepcopy(args); result=module.extract_saved_sec_evidence(*args)
        self.assertEqual(args,before)
        self.assertEqual(result['dei_facts'][-1]['resolved_text'],'Class A ordinary shares')
        self.assertEqual(result['dei_facts'][0]['context_ref'],'c1')
        self.assertEqual(result['same_context_security_groups'][0]['context_ref'],'c2')
        self.assertEqual(result['contexts'][1]['dimensions'][0]['value'],'ClassAMember')
        self.assertEqual(len(result['phrase_evidence'][0]['matches']),2)
        self.assertFalse(result['cross_context_facts_merged'])
        self.assertEqual(result['review_decision_preserved'],args[2])

    def test_hidden_duplicate_multiclass_not_merged(self):
        args=fixture('<ix:hidden><ix:nonNumeric name="dei:TradingSymbol" contextRef="c2">ABC</ix:nonNumeric></ix:hidden><ix:nonNumeric name="dei:Security12bTitle" contextRef="c2">Class B</ix:nonNumeric>')
        result=module.extract_saved_sec_evidence(*args)
        self.assertEqual(len(result['same_context_security_groups'][0]['ticker_fact_indexes']),2)
        self.assertTrue(result['same_context_security_groups'][0]['multiple_tickers_or_classes_unresolved'])
        self.assertTrue(result['dei_facts'][-2]['hidden'])
        self.assertEqual(result['normalized_visible_text'].count('ABC'),1)

    def test_broken_cycle_context_and_missing(self):
        result=module.extract_saved_sec_evidence(*fixture('<ix:nonNumeric name="dei:Security12bTitle" contextRef="missing" continuedAt="cycle">X</ix:nonNumeric><ix:continuation id="cycle" continuedAt="cycle">Y</ix:continuation>'))
        self.assertFalse(result['dei_facts'][-1]['continuation_complete'])
        self.assertEqual(result['dei_facts'][-1]['context_match_count'],0)
        self.assertEqual({issue['kind'] for issue in result['issues']},{'BROKEN_OR_AMBIGUOUS_CONTINUATION','MISSING_OR_AMBIGUOUS_CONTEXT'})
        raw=b'<p>No cover data</p>'; digest=module.sha(raw)
        result=module.extract_saved_sec_evidence(raw,{'path':'x','sha256':digest},{'expected_raw_sha256':digest})
        self.assertTrue(result['missing_cik_fact']); self.assertTrue(result['missing_security_title_fact'])

    def test_hash_decode_and_resource_contract(self):
        self.assertEqual(module.MAX_RAW_BYTES,32_000_000)
        args=fixture()
        with patch.object(module,'MAX_RAW_BYTES',len(args[0])-1):
            with self.assertRaises(ValueError): module.extract_saved_sec_evidence(*args)
        args=list(fixture()); args[2]['expected_raw_sha256']='0'*64
        with self.assertRaises(ValueError): module.extract_saved_sec_evidence(*args)
        args=list(fixture()); args[2]['phrase_queries']=[False]
        with self.assertRaises(ValueError): module.extract_saved_sec_evidence(*args)
        raw=b'\xff'; digest=module.sha(raw)
        with self.assertRaises(UnicodeDecodeError): module.extract_saved_sec_evidence(raw,{'path':'x','sha256':digest},{'expected_raw_sha256':digest})


if __name__=='__main__': unittest.main()
