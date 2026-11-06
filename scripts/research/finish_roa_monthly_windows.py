"""Windows monthly-adoption adapter, fail closed until loaded-release API exists.

Required GET /api/strategy-roa/runtime-binding fields must come from the running builder:
loaded_active_sha256, loaded_monthly_selections (month -> artifact hash), plus epoch.
Never synthesize these from disk. Existing production API lacks these fields.
"""
import argparse
import os
from datetime import datetime, timezone
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen
from hashlib import sha256
from core.strategy_account_store import StrategyAccountStore
from scripts.research.finish_roa_monthly_adoption import finish


class WindowsAdapter:
    def __init__(self, root, expected_process, month, artifact_sha256,
                 powershell=None, get_json=None, state_path=None):
        self.root=Path(root).resolve(); self.expected_process=expected_process
        self.state_path=Path(state_path) if state_path else None
        self.month=month; self.artifact_sha256=artifact_sha256
        self.powershell=powershell or self._powershell
        self.get_json=get_json or self._get_json
    def _powershell(self, command):
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                              cwd=self.root, capture_output=True, text=True, timeout=180)
        if result.returncode: raise RuntimeError('WINDOWS_OPERATION_FAILED:'+result.stderr[-1000:])
        return result.stdout.strip()
    def _get_json(self, path):
        with urlopen('http://127.0.0.1:8010'+path,timeout=120) as response:
            return json.load(response)
    def lookup_process(self, pid):
        raw=self.powershell(f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}'; if($p){{[ordered]@{{pid=[int]$p.ProcessId;creation_date=$p.CreationDate.ToUniversalTime().ToString('o');command_line=$p.CommandLine}}|ConvertTo-Json -Compress}}")
        return json.loads(raw) if raw else None
    def listener(self):
        raw=self.powershell("@(Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique) | ConvertTo-Json -Compress")
        ids=json.loads(raw) if raw else []
        if type(ids) is int: ids=[ids]
        if len(ids)>1: raise ValueError('MULTIPLE_LISTENER_OWNERS')
        return self.lookup_process(ids[0]) if ids else None
    def discover_started(self, record):
        candidates=[]
        for receipt in (self.root/'outputs/service_logs').glob('server_*.pid'):
            try:
                process=self.lookup_process(int(receipt.read_text().strip()))
                if not process: continue
                created=datetime.fromisoformat(process['creation_date'].replace('Z','+00:00')).timestamp()
                command=process['command_line']
                if (created < record['restart_started_at'] or abs(receipt.stat().st_mtime-created)>30
                    or command != self.expected_process['command_line']): continue
                candidates.append(process)
            except (ValueError, OSError): continue
        if len(candidates)>1: raise ValueError('MULTIPLE_STARTED_PROCESSES_RECONCILE')
        return candidates[0] if candidates else None
    def save_state(self, record):
        if self.state_path is None: raise ValueError('PERSISTENT_PROCESS_STATE_REQUIRED')
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.state_path.with_suffix('.staged')
        temporary.write_text(json.dumps(record));os.replace(temporary,self.state_path)
    def process(self):
        if self.state_path and self.state_path.exists():
            record=json.loads(self.state_path.read_bytes())
            if record['old_process']!=self.expected_process: raise ValueError('PROCESS_STATE_SCOPE_CONFLICT')
            expected=record.get('new_process')
            if expected:
                actual=self.lookup_process(expected['pid'])
                if actual and actual!=expected: raise ValueError('NEW_PROCESS_IDENTITY_CHANGED')
                return actual
            actual=self.discover_started(record)
            if actual:
                record['new_process']=actual;self.save_state(record)
            return actual
        actual=self.lookup_process(self.expected_process['pid'])
        if actual and actual!=self.expected_process: raise ValueError('OLD_PROCESS_IDENTITY_CHANGED')
        return actual
    def inspect(self):
        process=self.process()
        owner=self.listener()
        if owner is None:
            return dict(healthy=False, process_identity=process, state='LIVE_INITIALIZING' if process else 'UNAVAILABLE')
        if owner!=process: raise ValueError('LISTENER_PROCESS_IDENTITY_MISMATCH')
        try:
            config=self.get_json('/api/strategy-roa/config')
        except Exception:
            return dict(healthy=False, process_identity=process, state='LIVE_INITIALIZING' if process else 'UNAVAILABLE')
        try:
            binding=self.get_json('/api/strategy-roa/runtime-binding')
        except Exception as error:
            raise ValueError('LOADED_RELEASE_API_NOT_IMPLEMENTED_NO_RESTART') from error
        if not all(k in binding for k in ('loaded_active_sha256','loaded_monthly_selections')):
            raise ValueError('LOADED_RELEASE_API_NOT_IMPLEMENTED_NO_RESTART')
        if self.listener()!=owner or self.process()!=process:
            raise ValueError('HTTP_PROCESS_CHANGED')
        if not isinstance(binding.get('loaded_active_sha256'),str) or len(binding['loaded_active_sha256'])!=64:
            raise ValueError('LOADED_ACTIVE_POINTER_PROOF_REQUIRED')
        registry=binding['loaded_monthly_selections']
        if registry.get(self.month,{}).get('sha256')!=self.artifact_sha256:
            return dict(healthy=False, process_identity=process, state='MONTH_ARTIFACT_NOT_LOADED', active_sha256=binding['loaded_active_sha256'], epoch=config.get('strategy_epoch'), month=None)
        snapshot=self.get_json('/api/strategy-roa/snapshot')
        if self.listener()!=owner or self.process()!=process:
            raise ValueError('HTTP_PROCESS_CHANGED')
        session=snapshot.get('execution_session','')
        return dict(healthy=bool(config.get('active') and session[:7]==self.month and snapshot.get('strategy_epoch')==config.get('strategy_epoch')),
                    active_sha256=binding['loaded_active_sha256'], month=session[:7],
                    epoch=config.get('strategy_epoch'), process_identity=process)
    def restart(self, *, expected_process_identity, expected_active_sha256):
        if expected_process_identity!=self.expected_process or self.process()!=self.expected_process:
            raise ValueError('PROCESS_IDENTITY_CHANGED')
        pointer=self.root/'config/strategy_server_active.json'
        if sha256(pointer.read_bytes()).hexdigest()!=expected_active_sha256:
            raise ValueError('ACTIVE_CHANGED')
        # Repeat identity and active checks inside the same PowerShell operation.
        # PID alone is never authority to terminate an unrelated process.
        quote=lambda s: "'"+str(s).replace("'","''")+"'"
        identity=self.expected_process
        command=f"""$ErrorActionPreference='Stop'
$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {int(identity['pid'])}'
if(-not $p -or $p.CreationDate.ToUniversalTime().ToString('o') -ne {quote(identity['creation_date'])} -or $p.CommandLine -cne {quote(identity['command_line'])}){{throw 'PROCESS_IDENTITY_CHANGED'}}
if((Get-FileHash -LiteralPath {quote(pointer)} -Algorithm SHA256).Hash.ToLowerInvariant() -ne {quote(expected_active_sha256)}){{throw 'ACTIVE_CHANGED'}}
Stop-Process -Id $p.ProcessId -ErrorAction Stop
Wait-Process -Id $p.ProcessId -Timeout 20 -ErrorAction SilentlyContinue
if(Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue){{throw 'OLD_PROCESS_STILL_LIVE'}}
& {quote(self.root/'start_service.ps1')} -ProjectRoot {quote(self.root)}
if($LASTEXITCODE -ne 0){{throw 'START_SERVICE_FAILED'}}
"""
        self.save_state(dict(old_process=self.expected_process,restart_started_at=datetime.now(timezone.utc).timestamp(),active_sha256=expected_active_sha256))
        self.powershell(command)
        self.process()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('adoption-directory','evidence-directory','month','epoch','artifact-sha256','expected-process-json'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(); root=Path(__file__).resolve().parents[2]
    evidence=(root/args.evidence_directory).resolve()
    if Path(args.evidence_directory).is_absolute() or evidence==root or not evidence.is_relative_to(root):
        raise ValueError('PATH_OUTSIDE_ROOT')
    adapter=WindowsAdapter(root,json.loads(Path(args.expected_process_json).read_bytes()),args.month,args.artifact_sha256,state_path=evidence/'process-state.json')
    # Explicitly demand real loaded-config evidence before any restart intent.
    observed=adapter.inspect()
    resume=(root/args.evidence_directory/'restart-intent.json').exists()
    if args.execute and resume and not observed.get('healthy'):
        print(json.dumps(dict(status='RECONCILE_WAIT_NO_RESTART',runtime=observed))); return
    if args.execute and not resume and 'active_sha256' not in observed:
        raise ValueError('LOADED_RUNTIME_EVIDENCE_REQUIRED_BEFORE_EXECUTE')
    if not args.execute:
        print(json.dumps(dict(status='PREVIEW_NO_RESTART',runtime=observed))); return
    result=finish(root=root,adoption_directory=args.adoption_directory,evidence_directory=args.evidence_directory,
                  expected_month=args.month,expected_epoch=args.epoch,
                  read_account=lambda:adapter.get_json('/api/strategy-account'),
                  read_ledger=lambda:StrategyAccountStore(root/'data/strategy_account/real_strategy.sqlite3').read(),
                  inspect_runtime=adapter.inspect,restart=adapter.restart)
    print(json.dumps(result))

if __name__=='__main__': main()
