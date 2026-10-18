"""Targeted source-table attacks; compact copies are deliberately updated too."""
import copy,unittest
from test_ndx_persisted_candidate_calendar_research import fixture,m
from scripts import ndx_persisted_candidate_calendar_independent_readback_20261003 as reader

def attack(a,role):
 o=a['observation'];p=o['payload'];key='synthetic-non-snapshot-code.py';value='b'*64
 for obj in (p,o['receipt'],o['audit']):obj['source_hashes'][key]=value
 for obj in (a['history']['document'],a['history']['publication'],a['history']['readback']):obj['source_hashes'][key]=value
 del o[role]['source_hashes'][key]
 entry=a['history']['document']['observations'][-1]
 entry['original_source_hash_claims']={k:copy.deepcopy(o[k]['source_hashes'])for k in ('payload','receipt','audit')}

def reader_args(a):
 evidence=m.prepare_persisted_candidate_evidence(**a);docs={k:a[k]for k in ('history','observation','capture')};refs={k:{role:a[k][role]for role in (reader.OBS_ROLES if k=='observation'else reader.ROLES)}for k in docs};base=dict(evidence['source_hash_claims']);base[str(reader.PRODUCER)]=reader.PRODUCER_SHA;base[str(reader.CORE)]=reader.CORE_SHA
 core_ref=reader.reference(str(reader.CORE),reader.CORE_SHA);started_ref=reader.reference('synthetic-started','c'*64);result_ref=reader.reference('synthetic-result','d'*64)
 started=dict(schema='PERSISTED_CANDIDATE_CALENDAR_STARTED_V2',input_references=refs,core_reference=core_ref,source_hashes=base,started_at_utc=a['seal_evaluation_at_utc'],retry_allowed=False,**dict.fromkeys(reader.FALSE,False))
 result=dict(schema='SOURCE_BOUND_PERSISTED_CANDIDATE_CALENDAR_V2',evidence=evidence,input_references=refs,core_reference=core_ref,source_hashes=base,started_reference=started_ref,evaluation_at_utc=a['seal_evaluation_at_utc'],evaluation_clock_read_by_runner=True,external_clock_attestation_verified=False,evaluation_time_role='BEFORE_CONDITIONAL_EVALUATION_NOT_ACTUAL_SEAL_OR_FINAL_DURABLE_COMPLETION',**dict.fromkeys(reader.FALSE,False))
 pub=dict(schema='PERSISTED_CANDIDATE_CALENDAR_PUBLICATION_V2',status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=result_ref,source_hashes=base,**dict.fromkeys(reader.FALSE,False))
 return dict(docs=docs,tz=a['tzif_bytes'],result=result,pub=pub,started=started,refs=refs,result_ref=result_ref,started_ref=started_ref,base=base)

class Tests(unittest.TestCase):
 def test_pure_rejects_receipt_difference_and_audit_omission(self):
  for role in ('receipt','audit'):
   a=fixture();attack(a,role)
   with self.subTest(role=role),self.assertRaises(ValueError):m.prepare_persisted_candidate_evidence(**a)
 def test_independent_reader_rejects_synchronized_compact_attack(self):
  for role in ('receipt','audit'):
   a=fixture();args=reader_args(a);attack(a,role)
   # Keep every existing copied-evidence gate satisfied and preserve identity.
   args['result']['evidence']['selected_compact_entry']=copy.deepcopy(a['history']['document']['observations'][-1]);args['result']['evidence']['source_hash_claims']['synthetic-non-snapshot-code.py']='b'*64;args['base']['synthetic-non-snapshot-code.py']='b'*64
   with self.subTest(role=role),self.assertRaises(ValueError):reader.inspect(**args)
if __name__=='__main__':unittest.main()
