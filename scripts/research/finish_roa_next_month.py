"""Resume next-month drafting and Action-only scheduler binding after adoption."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from scripts.research.draft_roa_next_month import draft
from scripts.run_local_roa_monthly_preparation import run as preview_launcher


def task_sha256():
    command = "$x=Export-ScheduledTask -TaskName 'UsRatchet-ROA-Monthly-Preparation';$h=[Security.Cryptography.SHA256]::Create();try{([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($x)))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=30,check=True)
    value=result.stdout.strip()
    if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('TASK_HASH_UNAVAILABLE')
    return value


def finish_next(*, root, request, output_directory, python_path, expected_task_sha256,
                read_task=task_sha256, invoke=subprocess.run):
    root=Path(root).resolve()
    def path(name):
        p=(root/name).resolve()
        if Path(name).is_absolute() or not p.is_relative_to(root/'tmp') or p==root/'tmp':raise ValueError('PRIVATE_TMP_OUTPUT_REQUIRED')
        return p
    out=path(output_directory);plan_dir=output_directory+'/next-month'
    request_raw=json.dumps(request,sort_keys=True).encode()
    scope=dict(request_sha256=sha256(request_raw).hexdigest(),python_path=python_path,expected_task_sha256=expected_task_sha256)
    if out.exists():
        if json.loads((out/'scope.json').read_bytes())!=scope:raise ValueError('SUCCESSOR_SCOPE_CHANGED')
    else:
        out.mkdir(parents=True,exist_ok=False)
        (out/'scope.json').write_text(json.dumps(scope))
    saved=path(plan_dir)/'draft.json'
    if saved.exists():
        planned=json.loads(saved.read_bytes())
        for name,digest in planned['source_hashes'].items():
            p=(root/name).resolve()
            if not p.is_relative_to(root) or sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('DRAFT_SOURCE_CHANGED')
    else:
        if path(plan_dir).exists():raise ValueError('PARTIAL_DRAFT_RECONCILE_NO_OVERWRITE')
        planned=draft(root=root,request=request,output_directory=plan_dir,python_path=python_path)
    launcher=planned['launcher']
    preview_launcher(root=root,descriptor_path=launcher['path'],descriptor_sha256=launcher['sha256'])
    evidence=output_directory+'/task-binding'
    receipt_path=path(evidence)/'success.json'
    if not receipt_path.exists():
        if path(evidence).exists():raise ValueError('TASK_UPDATE_UNCERTAIN_RECONCILE_NO_REPEAT')
        if read_task()!=expected_task_sha256:raise ValueError('TASK_CHANGED_BEFORE_BINDING')
        command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(root/'scripts/rebind_local_roa_monthly_preparation.ps1'),
                 '-ConfigPath',str(root/launcher['path']),'-ConfigSha256',launcher['sha256'],
                 '-ExpectedTaskSha256',expected_task_sha256,'-EvidenceDirectory',evidence,'-Apply']
        invoke(command,cwd=root,capture_output=True,text=True,timeout=120,check=True)
    receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    if (receipt.get('Status')!='ACTION_REBOUND_NO_TASK_STARTED' or receipt.get('ConfigSha256')!=launcher['sha256']
            or receipt.get('BeforeSha256')!=expected_task_sha256 or not receipt.get('NonActionFieldsUnchanged')
            or read_task()!=receipt.get('AfterSha256')):
        raise ValueError('TASK_BINDING_NOT_VERIFIED')
    result=dict(status='NEXT_MONTH_TASK_BOUND',target_month=planned['target_month'],launcher=launcher,
                task_receipt=evidence+'/success.json',account_writes=False,task_started=False)
    (out/'success.json').write_text(json.dumps(result,indent=2))
    return result
