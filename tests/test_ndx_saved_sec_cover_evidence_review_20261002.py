from copy import deepcopy
import hashlib
import unittest
from backtest import ndx_saved_sec_cover_evidence_research as m

def extract(raw,queries=None):
    raw=raw.encode() if isinstance(raw,str) else raw
    digest=hashlib.sha256(raw).hexdigest()
    return m.extract_saved_sec_evidence(raw,{'path':'synthetic/issuer.html','sha256':digest},{'expected_raw_sha256':digest,'phrase_queries':queries or [],'reporter_cik':'0000999999','current_review_date':'2026-07-13','saved_risk':'UNREVIEWED_FOR_HISTORICAL_WINDOW'})

class SecEvidenceIndependentReview(unittest.TestCase):
    def test_reporter_cik_and_same_ticker_class_contexts_never_merge(self):
        raw='''<xbrli:context id="issuer"><xbrli:entity><xbrli:identifier scheme="SEC">0000000001</xbrli:identifier></xbrli:entity></xbrli:context>
        <xbrli:context id="classA"><xbrli:entity><xbrli:identifier scheme="SEC">0000000001</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="security">A</xbrldi:explicitMember></xbrli:segment></xbrli:entity></xbrli:context>
        <xbrli:context id="reporter"><xbrli:entity><xbrli:identifier scheme="SEC">0000999999</xbrli:identifier></xbrli:entity></xbrli:context>
        <ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="issuer">0000000001</ix:nonNumeric>
        <ix:nonNumeric name="dei:TradingSymbol" contextRef="classA">SAME</ix:nonNumeric><ix:nonNumeric name="dei:Security12bTitle" contextRef="classA">Class A</ix:nonNumeric>
        <ix:nonNumeric name="dei:TradingSymbol" contextRef="reporter">SAME</ix:nonNumeric><ix:nonNumeric name="dei:Security12bTitle" contextRef="reporter">Fund units</ix:nonNumeric>'''
        r=extract(raw)
        self.assertEqual(len(r['same_context_security_groups']),2)
        self.assertEqual([g['distinct_titles'] for g in r['same_context_security_groups']],[['Class A'],['Fund units']])
        self.assertEqual(r['dei_facts'][r['cik_fact_indexes'][0]]['resolved_text'],'0000000001')
        self.assertEqual(r['review_decision_preserved']['reporter_cik'],'0000999999')
        for key in ('same_context_cik_title_joint_proof_created','cross_context_facts_merged','cover_cusip_identity_verified','provider_identity_verified','point_in_time_verified','promotion_allowed'):self.assertIs(r[key],False)

    def test_hidden_continuations_exclude_and_duplicate_context_not_single(self):
        raw='''<xbrli:context id="c"><xbrli:identifier>1</xbrli:identifier></xbrli:context><xbrli:context id="c"><xbrli:identifier>2</xbrli:identifier></xbrli:context>
        <ix:nonNumeric name="dei:Security12bTitle" contextRef="c" continuedAt="tail">Class <span>A</span><ix:exclude>not part of fact</ix:exclude></ix:nonNumeric>
        <div style="display:none"><ix:continuation id="tail">common shares</ix:continuation></div>
        <script>business phrase</script><style>business phrase</style><div hidden>business phrase</div><p>business phrase</p><p>business phrase</p>'''
        r=extract(raw,['business phrase']);f=r['dei_facts'][0]
        self.assertEqual(f['resolved_text'],'Class A common shares');self.assertTrue(f['continuations'][0]['hidden'])
        self.assertEqual(f['context_match_count'],2)
        self.assertIn('MISSING_OR_AMBIGUOUS_CONTEXT',{x['kind'] for x in r['issues']})
        evidence=r['phrase_evidence'][0];self.assertEqual(len(evidence['matches']),2)
        for hit in evidence['matches']:
            self.assertEqual(r['normalized_visible_text'][hit['offset']:hit['end_offset']],'business phrase')
            self.assertEqual(hashlib.sha256(hit['snippet'].encode()).hexdigest(),hit['snippet_sha256'])
        self.assertNotIn('common shares',r['normalized_visible_text'])

    def test_ambiguous_continuation_and_hash_raw_bom(self):
        raw=b'\xef\xbb\xbf<p>\xe4\xb8\xad\xe6\x96\x87</p><ix:nonNumeric name="dei:TradingSymbol" contextRef="none" continuedAt="d">X</ix:nonNumeric><ix:continuation id="d">Y</ix:continuation><ix:continuation id="d">Z</ix:continuation>'
        r=extract(raw,['中文']);self.assertEqual(r['raw_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(r['dei_facts'][0]['continuation_complete']);self.assertEqual(r['dei_facts'][0]['resolved_text'],'X')
        self.assertEqual(r['phrase_evidence'][0]['matches'][0]['offset'],0)
        digest=hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):m.extract_saved_sec_evidence(raw,{'path':'x','sha256':'0'*64},{'expected_raw_sha256':digest})

if __name__=='__main__':unittest.main()
