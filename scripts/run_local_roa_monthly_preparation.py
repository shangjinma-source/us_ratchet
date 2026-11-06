"""Pinned local ROA preparation scheduler. No automatic adoption or task changes."""
import ast
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

ENTRY='scripts/run_local_roa_monthly_preparation.py'
INSTALLER='scripts/install_local_roa_monthly_preparation.ps1'


def source_closure(root):
 """Enumerate local static imports and literal local Python source references.
 Runtime configuration/data dependencies remain checked by the formal pipeline.
 """
 root=Path(root).resolve();todo=[ENTRY,'scripts/research/run_roa_monthly_pipeline.py'];seen=set()
 def add_module(name):
  parts=name.split('.')
  for n in range(1,len(parts)+1):
   init=Path(*parts[:n])/'__init__.py'
   if (root/init).is_file():todo.append(init.as_posix())
  for p in (Path(*parts).with_suffix('.py'),Path(*parts)/'__init__.py'):
   if (root/p).is_file():todo.append(p.as_posix())
 while todo:
  name=todo.pop()
  if name in seen:continue
  seen.add(name);tree=ast.parse((root/name).read_text(encoding='utf-8-sig'))
  package=Path(name).parent.parts
  for node in ast.walk(tree):
   if isinstance(node,ast.Import):
    for alias in node.names:add_module(alias.name)
   elif isinstance(node,ast.ImportFrom):
    prefix=list(package[:len(package)-node.level+1]) if node.level else []
    module='.'.join(prefix+([node.module] if node.module else []))
    if module:add_module(module)
    for alias in node.names:
     if alias.name!='*':add_module('.'.join(filter(None,[module,alias.name])))
   elif isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.endswith('.py'):
    p=Path(node.value)
    if not p.is_absolute() and '..' not in p.parts and (root/p).is_file():todo.append(p.as_posix())
 seen.add(INSTALLER)
 return sorted(seen)


def make_descriptor(*,root,python_path,request,log_directory):
 """Return a descriptor for explicit review/save, without running the pipeline."""
 root=Path(root).resolve();request_path=(root/request['path']).resolve()
 if not request_path.is_relative_to(root) or sha256(request_path.read_bytes()).hexdigest()!=request['sha256']:raise ValueError('REQUEST_HASH_OR_SCOPE')
 python=Path(python_path)
 if not python.is_absolute() or not python.is_file():raise ValueError('ABSOLUTE_PYTHON_REQUIRED')
 return dict(schema='ROA_MONTHLY_PREPARATION_LAUNCHER_V1',root=str(root),python_path=str(python),request=request,log_directory=log_directory,
  source_pins={name:sha256((root/name).read_bytes()).hexdigest() for name in source_closure(root)})


def run(*,root,descriptor_path,descriptor_sha256,execute=False,clock=lambda:datetime.now(timezone.utc)):
 root=Path(root).resolve()
 def path(name):
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or ':' in str(name):raise ValueError('PATH_OUTSIDE_ROOT')
  p=(root/p).resolve()
  if not p.is_relative_to(root):raise ValueError('PATH_OUTSIDE_ROOT')
  return p
 def read(ref):
  raw=path(ref['path']).read_bytes()
  if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('SOURCE_CHANGED:'+ref['path'])
  return json.loads(raw)
 descriptor=read(dict(path=descriptor_path,sha256=descriptor_sha256))
 if set(descriptor)!={'schema','root','python_path','request','source_pins','log_directory'} or descriptor['schema']!='ROA_MONTHLY_PREPARATION_LAUNCHER_V1':raise ValueError('DESCRIPTOR_FIELDS')
 if Path(descriptor['root']).resolve()!=root:raise ValueError('ROOT_MISMATCH')
 if set(descriptor['source_pins'])!=set(source_closure(root)):raise ValueError('SOURCE_CLOSURE_INCOMPLETE')
 def gate():
  read(dict(path=descriptor_path,sha256=descriptor_sha256))
  for name,digest in descriptor['source_pins'].items():
   if sha256(path(name).read_bytes()).hexdigest()!=digest:raise ValueError('CODE_SOURCE_CHANGED:'+name)
 gate();request=read(descriptor['request'])
 def current_active():
  try:read(request['active'])
  except ValueError:raise ValueError('ACTIVE_CHANGED_REBUILD_REVIEWED_REQUEST')
 current_active()
 logs=path(descriptor['log_directory'])
 if logs==root or any(logs==path(x) or logs in path(x).parents for x in (descriptor_path,descriptor['request']['path'],request['active']['path'])):raise ValueError('LOG_SCOPE')
 if not execute:return dict(status='PREVIEW_VALIDATED_NO_CAPTURE',source_count=len(descriptor['source_pins']),request_sha256=descriptor['request']['sha256'],exit_code=0,activated=False)
 logs.mkdir(parents=True,exist_ok=True);lock=logs/'running.lock';token=uuid4().hex;lock_bytes=token.encode()
 try:
  with lock.open('xb') as f:f.write(lock_bytes)
 except FileExistsError:return dict(status='BUSY_OR_NEEDS_LOCK_RECONCILIATION',exit_code=2,activated=False)
 try:
  complete=logs/'prepared.json';failure=logs/'blocked.json'
  if complete.exists():
   saved=json.loads(complete.read_bytes())
   if saved['descriptor_sha256']!=descriptor_sha256:raise ValueError('PREPARED_DESCRIPTOR_CHANGED')
   current_active()
   return dict(status='PREPARED_AWAITING_CONTROLLED_ADOPTION',publication_directory=saved['result']['publication_directory'],formal_gate_calls=0,exit_code=0,activated=False,artifact_revalidation_required_before_adoption=True)
  if failure.exists():return dict(status='BLOCKED_REVIEW_REQUIRED_NO_AUTOMATIC_RETRY',exit_code=2,activated=False)
  from scripts.research.run_roa_monthly_pipeline import run as pipeline,exit_code
  gate();result=pipeline(root=root,request=request,execute=True,clock=clock);gate();current_active()
  record=dict(descriptor_sha256=descriptor_sha256,at=clock().isoformat(),result=result,exit_code=exit_code(result))
  with (logs/(token+'.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
  if result['status']=='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED':
   with complete.open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
  elif record['exit_code']!=0:
   with failure.open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
  return dict(result,exit_code=record['exit_code'])
 except Exception as error:
  failure=logs/'blocked.json'
  if not failure.exists():
   with failure.open('x',encoding='utf-8') as f:json.dump(dict(descriptor_sha256=descriptor_sha256,status='BLOCKED_REVIEW_REQUIRED',error=str(error),at=clock().isoformat(),exit_code=2),f)
  raise
 finally:
  if lock.exists() and lock.read_bytes()==lock_bytes:lock.unlink()


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser()
 for name in ('descriptor-path','descriptor-sha256'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 try:result=run(root=Path(__file__).resolve().parents[1],descriptor_path=args.descriptor_path,descriptor_sha256=args.descriptor_sha256,execute=args.execute)
 except Exception as error:result=dict(status='BLOCKED_REVIEW_REQUIRED',error=str(error),exit_code=2,activated=False)
 print(json.dumps(result,ensure_ascii=False));raise SystemExit(result['exit_code'])
