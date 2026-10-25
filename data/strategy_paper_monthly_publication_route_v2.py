"""Resolve preauthorized monthly producer slots; no capture or account writes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import pinned, reject_links
from data.strategy_paper_application_descriptor_v2 import NY, stamp
from data.strategy_paper_monthly_training_bridge_v2 import load_monthly_training
from scripts.build_real_monthly_release_entry import build


def load_published_month(*, root, policy_reference, runtime_pins, output_root, clock=None):
    root=Path(root).absolute()
    clock=clock or (lambda:datetime.now(timezone.utc))
    now=stamp(clock());month=now.astimezone(NY).strftime('%Y-%m')
    policy_raw=pinned(root,policy_reference);policy=json.loads(policy_raw)
    require(policy.get('schema')=='PAPER_MONTHLY_PUBLICATION_ROUTE_V2' and
        policy.get('authorization')=='READ_COMPLETED_MARKET_ONLY', 'PAPER_MONTHLY_ROUTE_POLICY')
    slots=policy['slots']
    require(type(slots)is dict and 0<len(slots)<=24,'PAPER_MONTHLY_ROUTE_SLOTS')
    require(month in slots,'PAPER_MONTHLY_ROUTE_NOT_SCHEDULED')
    slot=slots[month]
    require(set(slot)=={'complete_path','expected_binding','producer_inputs','runtime_descriptor'},
        'PAPER_MONTHLY_ROUTE_SLOT_FIELDS')
    binding=slot['expected_binding']
    require(set(binding)=={'coordinator_sha256','bootstrap_sha256','policy_path','policy_sha256','output_directory'},
        'PAPER_MONTHLY_ROUTE_BINDING_FIELDS')
    inputs=slot['producer_inputs']
    require(set(inputs)=={'coordinator','bootstrap','policy'},'PAPER_MONTHLY_ROUTE_INPUTS')
    require(inputs['coordinator']['sha256']==binding['coordinator_sha256'] and
        inputs['bootstrap']['sha256']==binding['bootstrap_sha256'] and
        inputs['policy']==dict(path=binding['policy_path'],sha256=binding['policy_sha256']),
        'PAPER_MONTHLY_ROUTE_INPUT_BINDING')
    for reference in inputs.values():pinned(root,reference)
    require(slot['complete_path']==binding['output_directory']+'/complete.json','PAPER_MONTHLY_ROUTE_PATH')
    # Validate the logical path before observing any mutable completion bytes.
    from scripts.prepare_real_monthly_release import _safe
    complete_path=_safe(root,slot['complete_path'])
    reject_links(complete_path)
    require(not (complete_path.parent/'failed.json').exists(),'PAPER_MONTHLY_ROUTE_FAILED_PRESERVED')
    require(complete_path.is_file(),'PAPER_MONTHLY_ROUTE_WAIT_COMPLETION')
    require(complete_path.stat().st_size<=8*1024*1024,'PAPER_MONTHLY_ROUTE_COMPLETION_BUDGET')
    raw=complete_path.read_bytes();receipt=json.loads(raw)
    require(receipt['binding']==binding and stamp(receipt['at'])<=now,'PAPER_MONTHLY_ROUTE_COMPLETION_BINDING')
    descriptor=slot['runtime_descriptor'];pinned(root,descriptor)
    entry=build(root=root,complete_path=slot['complete_path'],complete_sha256=sha256(raw).hexdigest(),
        descriptor_path=descriptor['path'],descriptor_sha256=descriptor['sha256'])
    require(entry['target_month']==month,'PAPER_MONTHLY_ROUTE_MONTH')
    # Content-addressed derived routing is allowed only after the fixed policy
    # and the actual producer/publication/compiler checks above succeed.
    registry=canonical(dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1',entries=[entry]))
    digest=sha256(registry).hexdigest()
    directory=Path(output_root).absolute();reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()) and directory.resolve()!=root.resolve(),
        'PAPER_MONTHLY_ROUTE_OUTPUT')
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(digest+'.json');reject_links(path)
    if not path.exists():
        try:
            with path.open('xb') as stream:stream.write(registry)
        except FileExistsError:pass
    require(path.read_bytes()==registry,'PAPER_MONTHLY_ROUTE_REGISTRY_CHANGED')
    loaded=load_monthly_training(root=root,registry_path=path.relative_to(root).as_posix(),
        registry_sha256=digest,runtime_pins=runtime_pins,output_root=directory/'selection',clock=clock)
    require(complete_path.read_bytes()==raw and pinned(root,policy_reference)==policy_raw and
        not (complete_path.parent/'failed.json').exists(),'PAPER_MONTHLY_ROUTE_CHANGED_DURING_READ')
    loaded['producer_complete_sha256']=sha256(raw).hexdigest()
    loaded['publication_policy_reference']=dict(policy_reference)
    return loaded
