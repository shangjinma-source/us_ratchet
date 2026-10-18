"""Synthetic published-history boundary and temporary versioned recovery only."""
from copy import deepcopy
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_first_persisted_candidate_calendar_research as old
from backtest import ndx_first_persisted_candidate_calendar_v2_research as core
from scripts import ndx_prospective_observation_parent_history_20261003 as history_publisher
from scripts import ndx_first_persisted_candidate_calendar_v2_20261003 as producer
from scripts import ndx_first_persisted_candidate_calendar_v2_independent_readback_20261003 as reader
from test_ndx_first_persisted_candidate_calendar_research import fixture
from test_ndx_first_persisted_candidate_calendar_20261003 import file_fixture


def expanded_fixture():
 a=fixture();h=a['history'];g=a['genesis'];o=a['observation']
 # Run the actual history publisher in a synthetic source seam, not a hand-made
 # replacement of its publication fields. No actual source or observation IO.
 gb={k:(g[k]['path'],g[k]['sha256'])for k in history_publisher.GENESIS_BOUND}
 ob={k:(o[k]['path'],o[k]['sha256'])for k in history_publisher.OBSERVATION_BOUND}
 bb={k:(v['path'],v['sha256'])for k,v in g['baseline_references'].items()}
 code=Path(history_publisher.CORE[0]).read_bytes()
 raw={o[r]['path']:history_publisher.enc(o[k])for r,k in [('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit')]}
 def consume(r,s):
  history_publisher.merge(s,r)
  return code if r['path']==history_publisher.CORE[0]else raw.get(r['path'],b'synthetic source')
 with tempfile.TemporaryDirectory()as td,patch.multiple(history_publisher,OUTPUT=Path(td)/'history',GENESIS_BOUND=gb,OBSERVATION_BOUND=ob,BASELINE_BOUND=bb),patch.object(history_publisher,'load_envelope',return_value=g),patch.object(history_publisher,'consume',side_effect=consume),patch.object(history_publisher,'observation_namespace'),patch.object(history_publisher,'guard'):
  saved=history_publisher.run(execute=True);d=json.loads(Path(saved['history_reference']['path']).read_bytes())
 h['document']=d;h['publication']['source_hashes']=deepcopy(d['source_hashes']);h['readback']['source_hashes'].update(d['source_hashes']);a['history_publication_sources']=deepcopy(producer.HISTORY_PUBLICATION_SOURCES)
 return a


def write(path,obj):
 raw=producer.enc(obj);path.write_bytes(raw);return (str(path),sha256(raw).hexdigest())


def physical(root):
 b=file_fixture(root);hb=b['HISTORY_BOUND'];hpath=Path(hb['reference'][0]);h=json.loads(hpath.read_bytes());h['source_reference_claims_preserved_from_pure']=deepcopy(h['source_hashes']);h['input_references']={'core':deepcopy(producer.HISTORY_PUBLICATION_SOURCES['core'])}
 for r in producer.HISTORY_PUBLICATION_SOURCES.values():h['source_hashes'][r['path']]=r['sha256']
 hb['reference']=write(hpath,h)
 ppath=Path(hb['publication_reference'][0]);p=json.loads(ppath.read_bytes());p['history_reference']=dict(zip(('path','sha256'),hb['reference']));p['source_hashes']=deepcopy(h['source_hashes']);hb['publication_reference']=write(ppath,p)
 apath=Path(hb['readback_reference'][0]);audit=json.loads(apath.read_bytes());audit['history_reference']=p['history_reference'];audit['publication_reference']=dict(zip(('path','sha256'),hb['publication_reference']));audit['source_hashes'].update(h['source_hashes'])
 for r in (audit['history_reference'],audit['publication_reference']):audit['source_hashes'][r['path']]=r['sha256']
 hb['readback_reference']=write(apath,audit)
 refs={name:{k:dict(zip(('path','sha256'),v))for k,v in b[key].items()}for name,key in [('genesis','GENESIS_BOUND'),('history','HISTORY_BOUND'),('capture','CAPTURE_BOUND'),('observation','OBSERVATION_BOUND')]}
 failed=root/'failed_v1';failed.mkdir();recovery=deepcopy(producer.RECOVERY_BOUND)
 started=dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_STARTED_V1',input_references=refs,core_reference=recovery['core'],source_hashes={recovery[k]['path']:recovery[k]['sha256']for k in ('producer','core')},**dict.fromkeys(producer.FALSE,False))
 failure=dict(status='FAILED_DO_NOT_CONSUME',error_type='ValueError',error='Compact source declarations agree',retry_allowed=False,**dict.fromkeys(producer.FALSE,False))
 for role,value in [('started',started),('failure',failure)]:recovery[role]=dict(zip(('path','sha256'),write(failed/(role+'.json'),value)))
 b.update(FAILED_PARENT=failed,RECOVERY_BOUND=recovery)
 return b


class Tests(unittest.TestCase):
 def test_old_red_new_green_and_claims_not_authentication(self):
  a=expanded_fixture();old_args={k:v for k,v in a.items()if k!='history_publication_sources'}
  with self.assertRaisesRegex(ValueError,'Compact source declarations agree'):old.prepare_first_persisted_candidate_evidence(**old_args)
  before=deepcopy(a);result=core.prepare_first_persisted_candidate_evidence(**a)
  self.assertEqual(a,before);self.assertTrue(result['monthly_coordinate']);self.assertFalse(result['candidate_seal_allowed']);self.assertFalse(result['history_source_boundary']['source_authenticity_verified'])
  self.assertEqual(len(result['history_source_boundary']['published_sources']),len(result['history_source_boundary']['original_claims'])+2)
 def test_preserved_expansion_role_and_audit_attacks(self):
  for attack in ('preserved','extra','codehash','corelink','audit'):
   with self.subTest(attack=attack):
    a=expanded_fixture();h=a['history'];d=h['document'];r=a['history_publication_sources']['producer']
    if attack=='preserved':d['source_reference_claims_preserved_from_pure']['evil']='a'*64
    elif attack=='extra':
     d['source_hashes']['evil']='a'*64;h['publication']['source_hashes']['evil']='a'*64;h['readback']['source_hashes']['evil']='a'*64
    elif attack=='codehash':a['history_publication_sources']['producer']['sha256']='b'*64
    elif attack=='corelink':d['input_references']['core']=deepcopy(r)
    else:del h['readback']['source_hashes'][r['path']]
    with self.assertRaises(ValueError):core.prepare_first_persisted_candidate_evidence(**a)
 def test_physical_publisher_and_independent_reader_without_live_cache(self):
  with tempfile.TemporaryDirectory()as td:
   bindings=physical(Path(td))
   with ExitStack()as stack:
    for k,v in bindings.items():stack.enter_context(patch.object(producer,k,v))
    stack.enter_context(patch.object(producer,'now',return_value='2026-10-02T20:02:00+00:00'))
    saved=producer.run(execute=True)
   refs=dict(RESULT_SHA=saved['result_reference']['sha256'],PUBLICATION_SHA=saved['publication_reference']['sha256'],PARENT=bindings['OUTPUT'],OUTPUT=Path(td)/'readback',ROOT=Path(td),FAILED_PARENT=bindings['FAILED_PARENT'],RECOVERY_BOUND=bindings['RECOVERY_BOUND'])
   refs.update({k:bindings[k]for k in ('GENESIS_BOUND','HISTORY_BOUND','CAPTURE_BOUND','OBSERVATION_BOUND')})
   with ExitStack()as stack:
    for k,v in refs.items():stack.enter_context(patch.object(reader,k,v))
    stack.enter_context(patch.object(core,'prepare_first_persisted_candidate_evidence',side_effect=AssertionError('No production oracle')))
    out=reader.readback(execute=True);report=json.loads(Path(out['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertFalse(report['candidate_seal_allowed'])
   self.assertEqual(sorted(x.name for x in bindings['FAILED_PARENT'].iterdir()),['failure.json','started.json'])

 def test_reader_post_report_old_failed_parent_intrusion(self):
  with tempfile.TemporaryDirectory()as td:
   bindings=physical(Path(td))
   with ExitStack()as stack:
    for k,v in bindings.items():stack.enter_context(patch.object(producer,k,v))
    stack.enter_context(patch.object(producer,'now',return_value='2026-10-02T20:02:00+00:00'))
    saved=producer.run(execute=True)
   outdir=Path(td)/'independent';report=outdir/'independent_readback.json'
   refs=dict(RESULT_SHA=saved['result_reference']['sha256'],PUBLICATION_SHA=saved['publication_reference']['sha256'],PARENT=bindings['OUTPUT'],OUTPUT=outdir,ROOT=Path(td),FAILED_PARENT=bindings['FAILED_PARENT'],RECOVERY_BOUND=bindings['RECOVERY_BOUND'])
   refs.update({k:bindings[k]for k in ('GENESIS_BOUND','HISTORY_BOUND','CAPTURE_BOUND','OBSERVATION_BOUND')})
   original_open=Path.open
   @contextmanager
   def opening(path,*args,**kwargs):
    with original_open(path,*args,**kwargs)as f:yield f
    if path==report and args and args[0]=='xb':
     with original_open(bindings['FAILED_PARENT']/'extra.bin','xb')as f:f.write(b'late alien file')
   with ExitStack()as stack:
    for k,v in refs.items():stack.enter_context(patch.object(reader,k,v))
    stack.enter_context(patch.object(Path,'open',opening))
    with self.assertRaisesRegex(ValueError,'Retained failed parent inventory'):reader.readback(execute=True)
    self.assertEqual(sorted(x.name for x in outdir.iterdir()),['failure.json','independent_readback.json'])
    failure=json.loads((outdir/'failure.json').read_bytes());self.assertIs(failure['retry_allowed'],False)
    with self.assertRaises(ValueError):reader.readback(execute=True)

if __name__=='__main__':unittest.main()
