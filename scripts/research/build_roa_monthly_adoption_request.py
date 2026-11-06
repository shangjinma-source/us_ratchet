"""Derive a monthly adoption request from a completed pinned preparation job.
Read-only unless --output writes a new private request; never adopts or restarts.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from scripts.inspect_roa_monthly_preparation import inspect
from scripts.run_local_roa_monthly_preparation import run as preview
from scripts.research.finish_roa_monthly_windows import WindowsAdapter
from scripts.research.finish_roa_next_month import task_sha256


def observe_runtime(root):
    adapter=WindowsAdapter(root,{},'', '')
    owner=adapter.listener()
    if not owner:raise ValueError('RUNNING_SERVICE_REQUIRED')
    binding=adapter.get_json('/api/strategy-roa/runtime-binding')
    config=adapter.get_json('/api/strategy-roa/config')
    if adapter.listener()!=owner:raise ValueError('SERVICE_CHANGED_DURING_READ')
    return dict(process=owner,binding=binding,config=config)


def build(*,root,descriptor_path,descriptor_sha256,observe=observe_runtime,read_task=task_sha256):
    root=Path(root).resolve();checked={}
    def path(name):
        p=(root/name).resolve()
        if Path(name).is_absolute() or p==root or not p.is_relative_to(root):raise ValueError('PATH_OUTSIDE_ROOT')
        return p
    def ref(name):return dict(path=name,sha256=sha256(path(name).read_bytes()).hexdigest())
    def read(reference):
        raw=path(reference['path']).read_bytes()
        if sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('INPUT_CHANGED')
        checked[reference['path']]=reference['sha256'];return json.loads(raw)
    state=inspect(root=root,descriptor_path=descriptor_path,descriptor_sha256=descriptor_sha256)
    if state['status']!='PREPARED_PENDING_REVALIDATION':
        status='WAIT_PREPARED_MONTH' if state['status']=='CONFIGURATION_VALID_NO_COMPLETION' else 'PREPARATION_REVIEW_REQUIRED'
        return dict(status=status,preparation=state,request_created=False)
    preview(root=root,descriptor_path=descriptor_path,descriptor_sha256=descriptor_sha256)
    descriptor=read(dict(path=descriptor_path,sha256=descriptor_sha256))
    job=read(descriptor['request']);saved=read(ref(state['evidence']))
    publication_ref=ref(state['publication_directory'].rstrip('/')+'/validated.json')
    publication=read(publication_ref)
    if (saved.get('exit_code')!=0 or saved['result'].get('status')!='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED'
            or publication.get('status')!='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED'
            or publication.get('month')!=job['package']['expected_month']
            or publication.get('expected_active')!=job['active']):raise ValueError('COMPLETION_PUBLICATION_CONFLICT')
    read(publication['registration']);active=read(job['active'])
    capture_dir=job['capture']['output_directory'].rstrip('/')
    seal_ref=ref(capture_dir+'/runner_receipt.json');seal=read(seal_ref)
    inputs={}
    for key,name in (('manifest','manifest.json'),('completion','completion.json')):
        reference=dict(path=capture_dir+'/'+name,sha256=seal['output_hashes'][capture_dir+'/'+name])
        read(reference)
        if publication['source_hashes'].get(reference['path'])!=reference['sha256']:raise ValueError('CAPTURE_PUBLICATION_CONFLICT')
        inputs[key]=reference
    plan=read(job['capture']['plan'])
    inputs.update(capture_receipt=seal_ref,training_calendar=job['package']['training_calendar'],session_calendar=job['package']['session_calendar'],calendar_path=plan['calendar_path'],calendar_source_hashes=plan['calendar_source_hashes'])
    runtime=observe(root)
    expected_config=dict(path=active['configuration_path'],sha256=active['configuration_sha256'])
    if (runtime['binding'].get('loaded_active_sha256')!=job['active']['sha256']
            or runtime['binding'].get('loaded_configuration')!=expected_config
            or runtime['config'].get('active') is not True or not runtime['config'].get('strategy_epoch')):
        raise ValueError('LOADED_CURRENT_RELEASE_REQUIRED')
    request=dict(active=job['active'],registration=publication['registration'],publication=publication_ref,
                 month=publication['month'],epoch=runtime['config']['strategy_epoch'],expected_process=runtime['process'],
                 successor=dict(inputs=inputs,python_path=descriptor['python_path'],expected_task_sha256=read_task()))
    for name,digest in checked.items():
        if sha256(path(name).read_bytes()).hexdigest()!=digest:raise ValueError('INPUT_CHANGED_DURING_BUILD')
    return dict(status='ADOPTION_REQUEST_PREPARED_NOT_EXECUTED',request=request,source_hashes=checked,
                successor_calendar_fully_validated=False,account_writes=False,task_changed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('descriptor-path','descriptor-sha256'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--output')
    args=parser.parse_args();root=Path(__file__).resolve().parents[2]
    result=build(root=root,descriptor_path=args.descriptor_path,descriptor_sha256=args.descriptor_sha256)
    if args.output and 'request' in result:
        destination=(root/args.output).resolve()
        if Path(args.output).is_absolute() or not destination.is_relative_to(root/'tmp'):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('x',encoding='utf-8') as stream:json.dump(result['request'],stream,indent=2)
        result['request_file']=dict(path=destination.relative_to(root).as_posix(),sha256=sha256(destination.read_bytes()).hexdigest())
    print(json.dumps(result))

if __name__=='__main__':main()
