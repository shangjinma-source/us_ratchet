"""Small source-parser counterexamples; no publication or HTTP."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bkng_conditional_identity_risk_20260925 as m


def html():
 contexts=''
 for name in ('c-1','c-2'):
  member='<xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonStockMember</xbrldi:explicitMember>' if name=='c-2' else ''
  contexts+=f'<xbrli:context id="{name}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001075531</xbrli:identifier>{member}</xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>'
 fields=''
 for name,context,value in [('EntityCentralIndexKey','c-1','0001075531'),('DocumentPeriodEndDate','c-1','December 31 , 2025'),('Security12bTitle','c-2',m.TITLE),('TradingSymbol','c-2','BKNG')]:
  fields+=f'<ix:nonNumeric name="dei:{name}" contextRef="{context}">{value}</ix:nonNumeric>'
 return (contexts+fields+' travel service provider partners Booking.com Priceline Agoda KAYAK OpenTable travel service provider partners').encode()


def pages():return ['March 02, 2026 #58460 100 Booking Holdings Inc. (BKNG) Common Shares CUSIP:09857L108 Ex-Date:04/06/2026']+['']*12+['unofficial summary']


class Tests(unittest.TestCase):
 def test_common_stock_context_and_separate_document_context(self):
  result=m.cover_facts(html());self.assertEqual(result['fields'][2]['context'],'c-2');self.assertEqual(result['fields'][1]['context'],'c-1')
  self.assertEqual(len(result['business_phrase_offsets']),2)
 def test_other_cik_bond_member_and_mixed_ticker_context_rejected(self):
  attacks=[html().replace(b'0001075531',b'0000000000',1),html().replace(b'CommonStockMember',b'NotesMember'),
   html().replace(b'name="dei:TradingSymbol" contextRef="c-2"',b'name="dei:TradingSymbol" contextRef="c-1"')]
  for value in attacks:
   with self.assertRaises(ValueError):m.cover_facts(value)
 def test_memo_same_page_required_without_option_multiplier_inference(self):
  result=m.memo_facts(pages());self.assertTrue(result['option_deliverable_is_not_equity_identity_proof'])
  value=pages();value[0]=value[0].replace('CUSIP:09857L108','Contract Multiplier:25.00');value[1]='CUSIP:09857L108'
  with self.assertRaises(ValueError):m.memo_facts(value)
  value=pages();value[0]=value[0].replace('Common Shares','Options')
  with self.assertRaises(ValueError):m.memo_facts(value)
 def test_memo_disclaimer_and_page_count_required(self):
  value=pages();value[-1]='official certification'
  with self.assertRaises(ValueError):m.memo_facts(value)
  with self.assertRaises(ValueError):m.memo_facts(pages()[:-1])
 def test_immutable_namespace_and_loaded_source_lock(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'declaration.json'),patch.object(m,'build') as build:
   with self.assertRaises(ValueError):m.publish()
   build.assert_not_called()
  with patch.object(m.Path,'read_bytes',return_value=b'drift'):
   with self.assertRaises(ValueError):m.guard({})
 def test_no_early_window_or_equity_certification_flags(self):
  self.assertTrue({'early_window_review_availability_verified','early_window_local_evidence_available','direct_single_document_cusip_cik_proof','option_contract_terms_used_as_equity_identity','classification_uniquely_proven'}<=set(m.FALSE))


if __name__=='__main__':unittest.main()
