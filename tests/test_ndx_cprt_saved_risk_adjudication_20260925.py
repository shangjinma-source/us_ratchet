from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_cprt_saved_risk_adjudication_20260925 as m

def fixture():
 expected={'dei:entitycentralindexkey':'0000900075','dei:tradingsymbol':'CPRT','dei:security12btitle':'Common Stock, par value $0.0001','dei:documentperiodenddate':'July 31, 2025'}
 raw=(''.join('<ix:nonnumeric name="'+k+'" contextref="same">'+v+'</ix:nonnumeric>' for k,v in expected.items())+' '.join(m.PHRASES)).encode()
 seed=dict(decision_id='current:CPRT',tickers=['CPRT'],risk_chain='automotive',confidence='high',status='accepted',evidence_phrase='online auctions and vehicle remarketing services')
 saved=dict(seed,source_phrase=seed['evidence_phrase'],issuer_id='issuer:0000900075',security_ids=['security:0000900075:current_ticker:CPRT'],form='10-K',accession_number='0001628280-25-042946',document_url=m.URL,raw_sha256=m.sha(raw),effective_from='2025-09-26',evidence_available_date='2025-09-26',selection_date='2026-07-13',effective_to='',allow_fallback=False)
 old=dict(ticker='CPRT',conditional_research_security_id='security:0000900075:217204106',issuer_id='issuer:0000900075',cusip='217204106',security_class='Common Stock, par value $0.0001',risk_chain=None,risk_chain_assigned=False,issuer_link_is_cross_document_research_assumption=True,direct_single_document_cusip_cik_proof=False)
 business=dict(ticker='CPRT',issuer_id=old['issuer_id'],assigned_risk_chain=None,risk_chain_assigned=False,boundary_status='UNRESOLVED_EXISTING_ALTERNATIVES',candidate_risk_chains=['internet_ecommerce','automotive','industrial'])
 definition={'label':'automotive','description':'synthetic unchanged taxonomy'}
 docs=dict(config=dict(research_only=True,taxonomy_id='us_growth_risk_chain_taxonomy_v2',decisions=[seed]),snapshot=dict(research_only=True,taxonomy_id='us_growth_risk_chain_taxonomy_v2',source_seed_sha256=m.BOUND['config'][1],decisions=[saved]),identity={'rows':[old]},business={'rows':[business],'taxonomy_definitions':{'automotive':definition},'source_hashes':{str(m.BOUND['taxonomy'][0]):m.BOUND['taxonomy'][1]}},taxonomy={'risk_chains':{'automotive':definition}})
 return docs,raw

def run(docs,raw):
 bound=dict(m.BOUND);bound['annual']=(bound['annual'][0],m.sha(raw))
 with patch.object(m,'BOUND',bound):return m.assemble(docs,raw)

class Tests(unittest.TestCase):
 def test_preserves_old_null_and_new_conditional_declaration(self):
  docs,raw=fixture();r=run(docs,raw)
  self.assertEqual(r['risk_chain'],'automotive');self.assertIsNone(r['original_identity_fact']['risk_chain']);self.assertEqual(r['original_business_fact'],docs['business']['rows'][0]);self.assertTrue(all(r[k] is False for k in m.FALSE));self.assertTrue(r['saved_current_ticker_id_is_not_dated_cusip_proof']);self.assertTrue(r['saved_review_selection_postdates_window_start']);self.assertFalse(r['early_window_review_availability_verified'])
 def test_review_classification_link_and_scope_tampering(self):
  for attack in ('risk','raw','seed','date','scope','class','old'):
   d,b=fixture();s=d['snapshot']['decisions'][0]
   if attack=='risk':s['risk_chain']='internet_ecommerce'
   elif attack=='raw':s['raw_sha256']='0'*64
   elif attack=='seed':d['snapshot']['source_seed_sha256']='0'*64
   elif attack=='date':s['effective_from']='2026-03-20'
   elif attack=='scope':d['config']['research_only']=False
   elif attack=='class':d['identity']['rows'][0]['security_class']='Class A'
   else:d['business']['rows'][0]['assigned_risk_chain']='automotive'
   with self.subTest(attack=attack),self.assertRaises(ValueError):run(d,b)
 def test_original_text_missing_duplicate_or_context_conflict(self):
  for attack in ('missing','context'):
   d,b=fixture()
   if attack=='missing':b=b.replace(m.PHRASES[0].encode(),b'not present')
   else:b=b.replace(b'contextref="same"',b'contextref="other"',1)
   d['snapshot']['decisions'][0]['raw_sha256']=m.sha(b)
   with self.subTest(attack=attack),self.assertRaises(ValueError):run(d,b)
 def test_repeated_body_clauses_preserve_all_offsets(self):
  docs,raw=fixture();raw+=(' MD&A Overview '+' '.join(m.PHRASES)+' Notes '+m.PHRASES[2]).encode();docs['snapshot']['decisions'][0]['raw_sha256']=m.sha(raw)
  result=run(docs,raw);self.assertEqual([c['occurrence_count'] for c in result['business_clauses']],[2,2,3])
  parser=m.Text();parser.feed(raw.decode());text=' '.join(' '.join(parser.parts).split())
  for clause in result['business_clauses']:
   self.assertEqual(clause['normalized_text_offset'],clause['all_normalized_text_offsets'][0])
   self.assertEqual(clause['reference_occurrence_index'],0)
   for offset in clause['all_normalized_text_offsets']:self.assertEqual(text[offset:offset+len(clause['text'])],clause['text'])
 def test_actual_sealed_annual_clause_positions_without_assembly(self):
  raw=m.BOUND['annual'][0].read_bytes();self.assertEqual(m.sha(raw),m.BOUND['annual'][1]);parser=m.Text();parser.feed(raw.decode('utf-8'));text=' '.join(' '.join(parser.parts).split())
  expected=[[26702,165332],[29601,168211],[29827,168437,243740]]
  for phrase,positions in zip(m.PHRASES,expected):
   observed=[];start=0
   while True:
    offset=text.find(phrase,start)
    if offset<0:break
    observed.append(offset);start=offset+len(phrase)
   self.assertEqual(observed,positions)
 def test_saved_taxonomy_projection_mismatch_is_preserved(self):
  docs,raw=fixture();docs['business']['taxonomy_definitions']={'automotive':{'label':'historical mojibake','description':'unchanged old projection'}}
  result=run(docs,raw);self.assertFalse(result['saved_and_current_taxonomy_text_exact']);self.assertEqual(result['original_business_taxonomy_definitions'],docs['business']['taxonomy_definitions']);self.assertEqual(result['taxonomy_definition'],docs['taxonomy']['risk_chains']['automotive'])
  docs['business']['source_hashes'][str(m.BOUND['taxonomy'][0])]='0'*64
  with self.assertRaises(ValueError):run(docs,raw)
 def test_existing_namespace_does_not_build(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'adjudication.json'),patch.object(m,'build') as build:
   with self.assertRaises(ValueError):m.build_and_publish()
   build.assert_not_called()
 def test_consumed_blob_must_match_hard_source(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'source';p.write_bytes(b'changed')
   with patch.object(m,'BOUND',{'config':(p,'0'*64)}),patch.object(m,'guard'),patch.object(m,'assemble') as assemble:
    with self.assertRaises(ValueError):m.build()
    assemble.assert_not_called()
 def test_loaded_hash_conflict(self):
  with self.assertRaises(ValueError):m.guard({str(m.SOURCE):'0'*64})

if __name__=='__main__':unittest.main()
