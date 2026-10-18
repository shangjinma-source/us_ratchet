import copy
import unittest
from unittest.mock import patch
from test_ndx_pcar_cprt_conditional_identity_20260923 import fixture
from scripts import ndx_pcar_cprt_conditional_identity_20260923 as m


class IdentityIndependentReview(unittest.TestCase):
    def test_cusip_and_effective_year_cannot_be_truncated(self):
        cover,texts=fixture('PCAR')
        for old,new in [('CUSIP:693718108','CUSIP:6937181089'),('CUSIP:693718108','CUSIP:693718108X'),('Effective Date:February 8, 2023','Effective Date:February 8, 20230')]:
            bad={k:v.replace(old,new) for k,v in texts.items()}
            with self.subTest(new=new),self.assertRaises(ValueError):m.relation('PCAR',cover,bad)

    def test_same_context_duplicate_field_and_option_label_confusion_refused(self):
        cover,texts=fixture('PCAR');context=m.CASES['PCAR']['context']
        cases=[cover.replace(b'>PCAR<',b'>PCAR1<'),cover.replace(b'Common Stock, $1 par value',b'Class B Common Stock, $1 par value'),cover.replace(b'</html>',f'<ix:nonNumeric name="dei:TradingSymbol" contextRef="{context}">PCAR</ix:nonNumeric></html>'.encode())]
        for bad in cases:
            with self.assertRaises(ValueError):m.relation('PCAR',bad,texts)
        valid=m.relation('PCAR',cover,texts)
        self.assertTrue(valid['dated_memo_facts'][0]['option_symbols_are_not_equity_rename_evidence'])
        self.assertFalse(valid['memo_contains_subject_cik']);self.assertFalse(valid['direct_single_document_cusip_cik_proof'])
        self.assertFalse(valid['latest_security_interval_verified']);self.assertIsNone(valid['risk_chain'])

    def test_publisher_cannot_accept_resigned_risk_pit_or_deleted_raw_sources(self):
        expected=dict(source_hashes={'required_raw':'a'*64},rows=[m.relation('CPRT',*fixture('CPRT'))],point_in_time_verified=False)
        for defect in ('risk','pit','sources'):
            bad=copy.deepcopy(expected)
            if defect=='risk':bad['rows'][0]['risk_chain']='guessed';bad['rows'][0]['risk_chain_assigned']=True
            elif defect=='pit':bad['rows'][0]['annual_report_receipt_time']='2022-01-01';bad['point_in_time_verified']=True
            else:bad['source_hashes'].clear()
            with self.subTest(defect=defect),patch.object(m,'build',return_value=expected),patch.object(m,'publish') as publish:
                with self.assertRaises(ValueError):m.publish_verified('unused.json',bad)
                publish.assert_not_called()


if __name__=='__main__':unittest.main()
