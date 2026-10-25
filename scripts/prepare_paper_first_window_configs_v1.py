"""Offline missing-parent configuration preparation; never captures or registers."""
import argparse,json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from core.strategy_account_ledger import canonical,require
from data.strategy_daily_session_capture import reject_links
from data.strategy_prospective_paper_first_window_v1 import CODE_PATHS
from scripts.preflight_prospective_paper_sources_v1 import Inventory,preflight

MISSING='AUTO_CAPTURE_AND_FIRST_WINDOW_REVIEW_REQUIRED'
REUSABLE='SAVED_PARENT_REUSABLE_AFTER_CONTINUITY_REVIEW'

def configuration_rows(template,report,candidates):
 require(template['schema']=='PAPER_FIRST_WINDOW_SOURCE_PREPARATION_V1' and template.get('release_sha256') is None,'PREP_NO_RELEASE')
 require(report['candidate_count_matches'] and report['candidate_count']==len(candidates),'PREP_COUNT')
 for name in ('source_errors','calendar_errors','parent_errors','baseline_errors'):
  require(report[name]==[],'PREP_SOURCE_ERRORS')
 domain={r['security_id']:r['ticker'] for r in candidates}
 require(len(domain)==len(candidates) and len(set(domain.values()))==len(domain),'PREP_DUPLICATE_CANDIDATE')
 rows=report['securities']
 require(len(rows)==len(domain) and {r['security_id'] for r in rows}==set(domain),'PREP_REPORT_DOMAIN')
 output=[];reusable=[]
 for row in rows:
  sid=row['security_id'];require(row['identity_ok'] and domain[sid]==row['ticker'],'PREP_IDENTITY')
  require(row['preparation_class'] in {MISSING,REUSABLE},'PREP_UNSUPPORTED_CLASS')
  require(row['saved_unit_baseline']['byte_closure_verified'] is True,'PREP_UNIT_CLOSURE')
  if row['preparation_class']==REUSABLE:
   reusable.append(dict(security_id=sid,ticker=row['ticker'],status=REUSABLE));continue
  config=deepcopy(template);config['security_id']=sid
  raw=canonical(config)
  output.append(dict(ticker=row['ticker'],security_id=sid,raw=raw,sha256=sha256(raw).hexdigest()))
 return output,reusable

def prepare(*,root,template_reference,request_reference,output):
 root=Path(root).absolute();inventory=Inventory(root)
 template=inventory.document(template_reference);request=inventory.document(request_reference)
 for key in ('training','identity','calendar'):require(template[key]==request[key],'PREP_REQUEST_BINDING')
 require(template['baseline_review']==request['unit_baseline']['review_reference'],'PREP_BASELINE_BINDING')
 require(CODE_PATHS<={r['path'] for r in template['source_pins']},'PREP_CODE_SCOPE')
 for ref in template['source_pins']:
  raw=inventory.read(ref)
  if ref['path'] in CODE_PATHS:require(raw==(Path(__file__).resolve().parents[1]/ref['path']).read_bytes(),'PREP_EXECUTING_CODE')
 training=inventory.document(template['training'])
 review=inventory.document(template['baseline_review']);marks_raw=inventory.read(template['baseline_marks'])
 complete=inventory.document(template['baseline_complete'])
 require(complete['status']=='EVIDENCE_ASSEMBLED_NOT_EXECUTED','PREP_BASELINE_COMPLETE')
 for key in ('unit_review','marks'):
  ref=template['baseline_review' if key=='unit_review' else 'baseline_marks']
  require(complete['source_hashes'][complete['documents'][key]]==ref['sha256'],'PREP_BASELINE_HASH')
 require(review['training_manifest_sha256']==template['training']['sha256'] and review['marks_sha256']==sha256(marks_raw).hexdigest(),'PREP_BASELINE_TRAINING')
 for unit in review['securities'].values():
  for name in unit['source_references']:
   digest=complete['source_hashes'][name]
   inventory.read(dict(path=template['unit_source_paths'][name],sha256=digest))
 report=preflight(root=root,request=request)
 rows,reusable=configuration_rows(template,report,training['candidates'])
 # Re-read through a fresh inventory; cached bytes are not a race check.
 fresh=Inventory(root)
 for (name,digest),raw in inventory.cache.items():require(fresh.read(dict(path=name,sha256=digest))==raw,'PREP_SOURCE_CHANGED')
 destination=Path(output).absolute();reject_links(destination)
 require(destination.resolve().is_relative_to(root.resolve()) and destination.resolve()!=root.resolve(),'PREP_OUTPUT_SCOPE')
 destination.mkdir(parents=True,exist_ok=False)
 refs=[]
 for index,row in enumerate(rows):
  name=f'{index:03d}-{row["sha256"]}.json'
  with (destination/name).open('xb') as stream:stream.write(row['raw'])
  refs.append(dict(ticker=row['ticker'],security_id=row['security_id'],path=name,sha256=row['sha256'],status='CONFIG_ONLY_NOT_CAPTURED'))
 manifest=dict(status='CONFIGURATIONS_PREPARED_NOT_ACTIVATED',template_reference=template_reference,request_reference=request_reference,
  generated_count=len(refs),reuse_requires_review=reusable,configurations=refs,
  network_calls=0,account_mutated=False,orders_created=False,registration_created=False,
  next_step='Single-security real capture must succeed before batch capture; each result requires independent source review.')
 (destination/'preflight.json').write_bytes(canonical(report))
 (destination/'manifest.json').write_bytes(canonical(manifest))
 return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--template',required=True);parser.add_argument('--template-sha256',required=True);parser.add_argument('--request',required=True);parser.add_argument('--request-sha256',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
 result=prepare(root=args.root,template_reference=dict(path=args.template,sha256=args.template_sha256),request_reference=dict(path=args.request,sha256=args.request_sha256),output=args.output)
 print(json.dumps(dict(status=result['status'],generated_count=result['generated_count'],reusable_count=len(result['reuse_requires_review']),network_calls=0)))
