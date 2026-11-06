"""ROA monthly active-pointer adoption, default dry-run. Never restarts services.

The adjacent lock serializes cooperating adopters; unrelated/manual writers must
honor it too. Filesystem replace is atomic but is not an OS-wide compare-and-swap.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4
from scripts.research.prepare_roa_monthly_publication import prepare_publication
from data.strategy_unified_server_preparation_v34 import build_unified_server_preparation_v34


def adopt(*,root,active,registration,output_directory,execute=False):
 root=Path(root).resolve()
 def bounded(name):
  p=Path(name)
  if p.is_absolute() or '..' in p.parts or ':' in str(name):raise ValueError('PATH_OUTSIDE_ROOT')
  p=(root/p).resolve()
  if not p.is_relative_to(root):raise ValueError('PATH_OUTSIDE_ROOT')
  return p
 pointer=bounded(active['path']);out=bounded(output_directory)
 if out==root or out==pointer or out in pointer.parents:raise ValueError('OUTPUT_SCOPE')
 def verify_pointer():
  if sha256(pointer.read_bytes()).hexdigest()!=active['sha256']:raise ValueError('STALE_ACTIVE')
 verify_pointer()
 if out.exists():raise ValueError('OUTPUT_ALREADY_EXISTS_RECONCILE_PRIOR_ATTEMPT')
 lock=pointer.with_name(pointer.name+'.roa-monthly.lock')
 lock_bytes=json.dumps({'token':uuid4().hex,'pid':os.getpid(),'expected_active':active},sort_keys=True).encode()
 try:
  with lock.open('xb') as stream:stream.write(lock_bytes);stream.flush();os.fsync(stream.fileno())
 except FileExistsError:raise ValueError('ACTIVE_ADOPTION_BUSY_OR_NEEDS_RECONCILIATION')
 temporary=None
 try:
  verify_pointer()
  verified=prepare_publication(root=root,active=active,registration=registration,output_directory=output_directory)
  before=pointer.read_bytes();verify_pointer()
  next_path=bounded(verified['next_active']['path']);next_raw=next_path.read_bytes()
  if sha256(next_raw).hexdigest()!=verified['next_active']['sha256']:raise ValueError('NEXT_ACTIVE_CHANGED')
  if (out/'rollback_active.json').read_bytes()!=before:raise ValueError('ROLLBACK_MISMATCH')
  def save(name,obj):
   with (out/name).open('xb') as stream:stream.write(json.dumps(obj,indent=2).encode());stream.flush();os.fsync(stream.fileno())
  status=dict(status='DRY_RUN_VALIDATED_NOT_SWITCHED',expected_active=active,next_active_sha256=sha256(next_raw).hexdigest(),rollback=verified['rollback'],registration=registration,account_events_written=False,service_restarted=False,runtime_verified=False,requires_exclusive_cooperating_writers=True)
  if not execute:
   verify_pointer();save('adoption.json',status);return status
  save('switch-intent.json',status)
  temporary=pointer.with_name(pointer.name+'.'+uuid4().hex+'.staged')
  with temporary.open('xb') as stream:stream.write(next_raw);stream.flush();os.fsync(stream.fileno())
  next_reference=json.loads(next_raw)
  prepared=build_unified_server_preparation_v34(root=root,configuration_path=next_reference['configuration_path'],configuration_sha256=next_reference['configuration_sha256'])
  prepared['validate_code']()
  # Recheck the complete declared closure immediately before the atomic replace.
  for name,digest in verified['source_hashes'].items():
   if sha256(bounded(name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED_BEFORE_SWITCH:'+name)
  verify_pointer()
  if lock.read_bytes()!=lock_bytes:raise ValueError('ADOPTION_LOCK_OWNERSHIP_CHANGED')
  if temporary.read_bytes()!=next_raw:raise ValueError('STAGED_ACTIVE_CHANGED')
  os.replace(temporary,pointer);temporary=None
  if pointer.read_bytes()!=next_raw:raise ValueError('ACTIVE_POST_SWITCH_CONFLICT_RECONCILE')
  status.update(status='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED',active_sha256=sha256(next_raw).hexdigest(),
   next_step='Controlled service restart then verify loaded strategy, month, account invariant and workers. Disk switch alone is not deployment success.',
   rollback_requirement='Before restoring exact rollback bytes verify active still equals this next_active_sha256; never overwrite a later release.')
  save('adoption.json',status);return status
 except Exception as error:
  # Replacement may already be durable; failure must never claim unchanged.
  if out.exists() and not (out/'adoption-failure.json').exists():
   current=sha256(pointer.read_bytes()).hexdigest() if pointer.is_file() else None
   with (out/'adoption-failure.json').open('xb') as stream:stream.write(json.dumps({'status':'FAILED_RECONCILE_ACTIVE_BEFORE_RETRY','reason':str(error),'observed_active_sha256':current,'expected_active_sha256':active['sha256'],'service_restarted':False}).encode())
  raise
 finally:
  if temporary is not None and temporary.exists():temporary.unlink()
  if lock.exists() and lock.read_bytes()==lock_bytes:lock.unlink()


if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('active-path','active-sha256','registration-path','registration-sha256','output-directory'):parser.add_argument('--'+name,required=True)
 parser.add_argument('--execute',action='store_true')
 args=parser.parse_args()
 print(json.dumps(adopt(root=Path(__file__).resolve().parents[2],active=dict(path=args.active_path,sha256=args.active_sha256),registration=dict(path=args.registration_path,sha256=args.registration_sha256),output_directory=args.output_directory,execute=args.execute)))
