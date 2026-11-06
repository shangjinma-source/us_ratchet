"""Draft the strictly next ROA month request/launcher; never capture or activate."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from scripts.build_monthly_successor_plan import build_next_plan
from scripts.run_local_roa_monthly_preparation import make_descriptor


def draft(*,root,request,output_directory,python_path,clock=lambda:datetime.now(timezone.utc)):
 root=Path(root).resolve();checked={}
 def path(name):
  p=(root/name).resolve()
  if Path(name).is_absolute() or not p.is_relative_to(root) or p==root:raise ValueError('PATH_OUTSIDE_ROOT')
  return p
 def read(ref):
  raw=path(ref['path']).read_bytes()
  if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('INPUT_CHANGED:'+ref['path'])
  checked[ref['path']]=ref['sha256'];return json.loads(raw)
 active=read(request['active']);success=read(request['runtime_success'])
 adoption=read(request['adoption']);publication=read(request['publication']);seal=read(request['capture_receipt'])
 month=publication['month'];digest=request['active']['sha256']
 if (success.get('status')!='MONTH_RUNTIME_VERIFIED' or success['scope']['month']!=month or success['scope']['active_sha256']!=digest
     or success['scope']['adoption_sha256']!=request['adoption']['sha256'] or not success.get('account_and_ledger_unchanged')
     or adoption.get('status')!='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED' or adoption['active_sha256']!=digest
     or publication.get('status')!='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED' or publication['next_active']['sha256']!=digest):
  raise ValueError('COMPLETED_ADOPTION_REQUIRED')
 manifest_ref=request['manifest'];completion_ref=request['completion']
 for ref in (manifest_ref,completion_ref):
  if seal['output_hashes'].get(ref['path'])!=ref['sha256'] or publication['source_hashes'].get(ref['path'])!=ref['sha256']:
   raise ValueError('CAPTURE_NOT_BOUND_TO_ADOPTED_PUBLICATION')
  read(ref)
 training=read(request['training_calendar']);read(request['session_calendar'])
 for name,h in request['calendar_source_hashes'].items():read(dict(path=name,sha256=h))
 out=path(output_directory)
 if out.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
 plan=build_next_plan(root=root,previous_manifest_path=manifest_ref['path'],previous_manifest_sha256=manifest_ref['sha256'],
  previous_completion_path=completion_ref['path'],previous_completion_sha256=completion_ref['sha256'],
  calendar_path=request['calendar_path'],calendar_source_hashes=request['calendar_source_hashes'],
  output_directory=output_directory,clock=clock,completed_target_month=month)
 boundary=json.loads(plan['artifacts'][output_directory+'/boundary.json'])
 dates={r['date'] for r in training['sessions']}
 if not set(boundary['training_dates']).issubset(dates):raise ValueError('TRUSTED_TRAINING_CALENDAR_INCOMPLETE')
 def recheck():
  for name,h in checked.items():
   if sha256(path(name).read_bytes()).hexdigest()!=h:raise ValueError('INPUT_CHANGED_DURING_DRAFT')
 recheck();out.mkdir(parents=True,exist_ok=False)
 for name,raw in plan['artifacts'].items():
  target=path(name)
  if not target.is_relative_to(out):raise ValueError('ARTIFACT_OUTSIDE_OUTPUT')
  with target.open('xb') as f:f.write(raw)
 def save(name,doc):
  target=out/name
  with target.open('x',encoding='utf-8') as f:json.dump(doc,f,indent=2)
  return dict(path=target.relative_to(root).as_posix(),sha256=sha256(target.read_bytes()).hexdigest())
 capture_path=output_directory+'/capture_plan.json'
 next_request=dict(capture=dict(plan=dict(path=capture_path,sha256=sha256(path(capture_path).read_bytes()).hexdigest()),training_calendar=request['training_calendar'],output_directory=output_directory+'/prepared'),
  active=request['active'],package=dict(session_calendar=request['session_calendar'],training_calendar=request['training_calendar'],expected_month=plan['target_month']),
  coordination_directory=output_directory+'/coordination',publication_directory=output_directory+'/publication')
 ref=save('request.json',next_request)
 descriptor=make_descriptor(root=root,python_path=python_path,request=ref,log_directory=output_directory+'/logs')
 launcher=save('launcher.json',descriptor);recheck()
 result=dict(status='DRAFT_NEXT_MONTH_NOT_INSTALLED',completed_month=month,target_month=plan['target_month'],request=ref,launcher=launcher,source_hashes=checked,capture_executed=False,task_changed=False,active_changed=False)
 save('draft.json',result);return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for field in ('request','output-directory','python-path'):p.add_argument('--'+field,required=True)
 a=p.parse_args();print(json.dumps(draft(root=Path(__file__).resolve().parents[2],request=json.loads(Path(a.request).read_bytes()),output_directory=a.output_directory,python_path=a.python_path)))
