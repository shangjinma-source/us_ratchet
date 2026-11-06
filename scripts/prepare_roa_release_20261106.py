"""Stage V34 references and rollback materials. Never changes the active manifest/server."""
import argparse,json,subprocess
from pathlib import Path
from hashlib import sha256
from data.strategy_unified_server_preparation_v34 import SOURCES,build_unified_server_preparation_v34
from data.roa_current_signal import CONTRACT_PATHS
from data.roa_execution_lifecycle import digest
ROOT=Path(__file__).resolve().parents[1]
def encode(value):return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()
def prepare(directory,account_id):
 out=(ROOT/directory).resolve()
 if not out.is_relative_to(ROOT/'research_contracts'):raise ValueError('RELEASE_DIRECTORY_SCOPE')
 out.mkdir(parents=True,exist_ok=False)
 active_raw=(ROOT/'config/strategy_server_active.json').read_bytes();active=json.loads(active_raw)
 server=(ROOT/'api/server.py').read_bytes();replacement=server.replace(b'from api.strategy_server_mount_v8 import mount_strategy_routes',b'from api.strategy_server_mount_v9 import mount_strategy_routes')
 if replacement==server:raise ValueError('SERVER_IMPORT_NOT_FOUND')
 (out/'previous_active.json').write_bytes(active_raw);(out/'previous_server.py').write_bytes(server);(out/'next_server.py').write_bytes(replacement)
 old_index=subprocess.check_output(['git','show','203de553c0a68e3a4526d6c6a62f9885cd430eb7:web/index.html'],cwd=ROOT).replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
 if sha256(old_index).hexdigest()!='fbe96ea7d82f182a4e9f8016162ba780b292226358b8ed10429f6fafcfaf66fa':raise ValueError('ROLLBACK_INDEX_HASH')
 (out/'previous_index.html').write_bytes(old_index)
 (out/'rollback.json').write_bytes(encode(dict(restore={'api/server.py':'previous_server.py','web/index.html':'previous_index.html','config/strategy_server_active.json':'previous_active.json'},new_account_ledger_migration=False,retain_roa_state=True)))
 refs={};changes=[]
 def clone(reference,mode):
  key=(reference['path'],mode)
  if key in refs:return refs[key]
  raw=(ROOT/reference['path']).read_bytes()
  if sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('OLD_REFERENCE_HASH_CHANGED:'+reference['path'])
  value=json.loads(raw)
  for k,v in list(value.items()):
   if k.startswith('base_') and isinstance(v,dict) and set(v)=={'path','sha256'}:value[k]=clone(v,mode)
  pins=value.get('source_pins',{})
  for name in ('web/index.html','api/server.py'):
   if name in pins:
    fresh=sha256(replacement if name=='api/server.py' and mode=='deploy' else (ROOT/name).read_bytes()).hexdigest()
    if fresh!=pins[name]:changes.append(dict(mode=mode,source=name,previous=pins[name],next=fresh));pins[name]=fresh
  if value==json.loads(raw):
   refs[key]=dict(reference);return refs[key]
  target=out/(mode+'-base-'+str(len(refs))+'.json');data=encode(value);target.write_bytes(data)
  result=dict(path=target.relative_to(ROOT).as_posix(),sha256=sha256(data).hexdigest());refs[key]=result;return result
 contracts={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CONTRACT_PATHS}
 roa=dict(account_id=account_id,strategy_epoch='ROA_20261106',contract_sha256=digest(contracts),contract_hashes=contracts,
  daily_signal_path='data/strategy_account/roa_20261106/daily_signal.json',lifecycle_path='data/strategy_account/roa_20261106/lifecycle.json',
  close_evidence_path='data/strategy_account/roa_20261106/close_evidence',close_recovery_path='data/strategy_account/roa_20261106/close_recovery',monthly_selections={},execution_admission=None)
 outputs={}
 for mode in ('preflight','deploy'):
  base=clone(dict(path=active['configuration_path'],sha256=active['configuration_sha256']),mode)
  value=dict(schema='ROA_UNIFIED_PREPARATION_V34',base_v33=base,source_pins={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(SOURCES)},roa=roa)
  target=out/(mode+'-v34.json');data=encode(value);target.write_bytes(data);outputs[mode]=dict(path=target.relative_to(ROOT).as_posix(),sha256=sha256(data).hexdigest())
 reference=outputs['preflight'];prepared=build_unified_server_preparation_v34(root=ROOT,configuration_path=reference['path'],configuration_sha256=reference['sha256'])
 prepared['validate_code']()
 next_active=dict(schema=active['schema'],configuration_path=outputs['deploy']['path'],configuration_sha256=outputs['deploy']['sha256'])
 (out/'next_active.json').write_bytes(encode(next_active))
 (out/'preflight.json').write_bytes(encode(dict(status='PREPARED_NOT_ACTIVATED',preflight='PASS',deploy_requires_staged_server=True,execution_admission=None,source_pin_changes=changes,outputs=outputs)))
 print(json.dumps(dict(status='PREPARED_NOT_ACTIVATED',directory=directory,preflight='PASS')))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);parser.add_argument('--account-id',required=True);ARGS=parser.parse_args();prepare(ARGS.directory,ARGS.account_id)
