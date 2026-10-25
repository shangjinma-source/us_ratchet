"""Explicit same-month research upgrade, never a monthly data publication.

One durable claim permits one selection. Uncertain selection without prepared
output requires review; a saved candidate may only be published, not reselected.
"""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from contextlib import closing
import base64,json,os
from core.strategy_account_ledger import canonical,require
from data.strategy_profiled_runtime_archive import require_archived_configuration
from data.strategy_continuous32_target_decision import PROFILE_ID,validate_result
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService,MINIMUM_RUNTIME_PATHS
from data.strategy_account_monthly_release import validate_account_identity_coverage
from scripts.register_quantity_v2_paper_protocol import safe_path

class Continuous32ResearchUpgrade:
    def __init__(self,*,monthly,package_path,package_sha256,validate_code):
        self.monthly=monthly;self.root=Path(monthly.root);self.path=safe_path(self.root,package_path)
        self.digest=package_sha256;self.gate=validate_code

    def _package(self):
        self.gate();raw=self.path.read_bytes()
        require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==self.digest,'UPGRADE_PACKAGE_CHANGED')
        package=json.loads(raw)
        require(set(package)=={'schema','purpose','target_month','upgrade_event_id','previous_target_id','account_revision','original_configuration_sha256','upgraded_configuration','reviewed_training','source_hashes','base_snapshot','upgrade_archive'},'UPGRADE_PACKAGE_FIELDS')
        require(package['schema']=='CONTINUOUS32_RESEARCH_UPGRADE_V1' and package['purpose']=='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION','UPGRADE_PURPOSE_REQUIRED')
        name='data/strategy_continuous32_upgrade.py'
        require(type(package['source_hashes'])is dict and name in package['source_hashes'] and sha256(safe_path(self.root,name).read_bytes()).hexdigest()==package['source_hashes'][name] and sha256(Path(__file__).read_bytes()).hexdigest()==package['source_hashes'][name],'UPGRADE_IMPLEMENTATION_CHANGED')
        require(package['target_month']==self.monthly._month(),'UPGRADE_MONTH_EXPIRED')
        expected_snapshot=dict(package['base_snapshot'],archive_path=package['upgrade_archive']['path'],archive_sha256=package['upgrade_archive']['sha256'])
        require(dict(self.monthly._active_snapshot or {})==expected_snapshot,'UPGRADE_SNAPSHOT_NOT_ADMITTED')
        require(type(package['upgrade_event_id'])is str and 0<len(package['upgrade_event_id'])<=128,'UPGRADE_EVENT_INVALID')
        return package

    def _write(self,path,value):
        raw=canonical(value);require(len(raw)<=48*1024*1024,'UPGRADE_EVIDENCE_BUDGET')
        with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())

    def _capture(self,runtime,state):
        from data.strategy_account_target_inputs import build_target_inputs
        value=deepcopy(runtime.selection.provider(state));package=value['source_package']
        for name in MINIMUM_RUNTIME_PATHS:
            raw=(runtime.selection.root/name).read_bytes();digest=runtime.selection.pins[name]
            require(sha256(raw).hexdigest()==digest,'UPGRADE_SOURCE_CHANGED')
            require(name not in package['source_hashes'] or package['source_hashes'][name]==digest,'UPGRADE_SOURCE_CONFLICT')
            require(name not in package['files'] or package['files'][name]==raw,'UPGRADE_SOURCE_CONFLICT')
            package['files'][name]=raw;package['source_hashes'][name]=digest
        build_target_inputs(state=state,now=self.monthly.clock().isoformat(),maximum_mark_age_seconds=runtime.selection.age,**value)
        runtime.selection._pins()
        require(self.monthly.accounts.read()==state,'UPGRADE_SOURCE_ACCOUNT_CHANGED')
        return value

    def preflight(self,*,event_id):
        """Capture/validate source evidence only: no claim, selector or target write."""
        return self._run(event_id=event_id,preflight_only=True)

    def execute(self,*,event_id):
        return self._run(event_id=event_id,preflight_only=False)

    def _run(self,*,event_id,preflight_only):
        with self.monthly.snapshot_operation():
            p=self._package();require(event_id==p['upgrade_event_id'],'EXPLICIT_UPGRADE_EVENT_REQUIRED')
            request=dict(event_id=event_id,reason='EXPLICIT_RECONFIGURE',expected_revision=p['account_revision'],previous_target_id=p['previous_target_id'])
            saved=self.monthly.targets.operation(event_id)
            if saved:
                require(saved['payload']['request']==dict(request,upgrade_package_sha256=self.digest),'UPGRADE_PUBLICATION_CONFLICT')
                return dict(status='UPGRADE_PUBLISHED',target=saved,selection_started=False)
            state=self.monthly.accounts.read();prior=self.monthly.current()
            require(state and state['revision']==p['account_revision'] and prior and prior['target_id']==p['previous_target_id'],'UPGRADE_STALE_SNAPSHOT')
            require(prior['payload']['decision']['payload']['input_binding'].get('selector_profile') is None,'UPGRADE_REQUIRES_ORIGINAL_TARGET')
            _,original=self.monthly._for_target(prior)
            require(sha256(canonical(original)).hexdigest()==p['original_configuration_sha256'],'UPGRADE_ORIGINAL_CONFIGURATION_CHANGED')
            ref=p['upgraded_configuration'];raw=safe_path(self.root,ref['path']).read_bytes()
            require(sha256(raw).hexdigest()==ref['sha256'],'UPGRADE_CONFIGURATION_CHANGED')
            config=json.loads(raw)
            require(config['schema']=='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1' and config['selector_profile']==PROFILE_ID,'UPGRADE_PROFILE_REQUIRED')
            for key in ('target_month','training_manifest','training_sha256','training_closed_at','identity_manifest','identity_sha256'):
                require(config[key]==original[key],'UPGRADE_SAVED_DATA_CHANGED')
            require(p['reviewed_training']==dict(path=original['training_manifest'],sha256=original['training_sha256'],closed_at=original['training_closed_at']),'UPGRADE_TRAINING_REVIEW_BINDING')
            require_archived_configuration(root=self.root,archive_path=self.monthly.archive_path,archive_sha256=self.monthly.archive_sha256,configuration=config)
            validate_account_identity_coverage(self.root,config,state)
            runtime=self.monthly._runtime(config);require(type(runtime.selection)is StrategyContinuous32TargetService,'UPGRADE_RUNTIME_REQUIRED')
            directory=safe_path(self.root,'data/strategy_account/research_upgrades/'+self.digest)
            claim=directory/'claim.json';prepared=directory/'prepared.json'
            claim_value=dict(package_sha256=self.digest,request=request,account_state=state)
            if preflight_only:
                self._capture(runtime,state)
                require(self.monthly.current()==prior and self._package()==p,'UPGRADE_PREFLIGHT_CHANGED')
                return dict(status='UPGRADE_SOURCE_PREFLIGHT_READY_NOT_EXECUTED',selection_started=False,claim_created=False)

            selection_started=False
            if claim.exists():
                require(json.loads(claim.read_bytes())==claim_value,'UPGRADE_CLAIM_CHANGED')
                require(prepared.is_file(),'UPGRADE_SELECTION_RECOVERY_REQUIRED')
            else:
                # Source collection/validation precedes the one-shot selection claim.
                # Failed or stale quotes leave no claim and may be refreshed later.
                validated_evidence=self._capture(runtime,state)
                require(self.monthly.current()==prior and self._package()==p,'UPGRADE_PREFLIGHT_CHANGED')
                directory.mkdir(parents=True,exist_ok=True)
                self._write(claim,claim_value)
                selection_started=True
                captures=[]
                def evidence(snapshot):
                    require(snapshot==state and not captures,'UPGRADE_CAPTURE_REUSE_INVALID')
                    value=deepcopy(validated_evidence)
                    captures.append(value['source_package']['files']);return value
                selector=StrategyContinuous32TargetService(store=self.monthly.accounts,evidence_provider=evidence,runtime_root=runtime.selection.root,runtime_pins=runtime.selection.pins,maximum_mark_age_seconds=runtime.selection.age,execution_fee_bps=runtime.selection.fees,clock=self.monthly.clock)
                result=selector.select();require(result['status']=='READY',result.get('reason','UPGRADE_SELECTION_FAILED'))
                decision,_,captured=selector.current
                require(captured==state and len(captures)==1,'UPGRADE_SELECTION_SNAPSHOT_CHANGED')
                require(len(captures[0])<=2000 and sum(map(len,captures[0].values()))<=32*1024*1024,'UPGRADE_SOURCE_BUDGET')
                self._write(prepared,dict(package_sha256=self.digest,decision=decision,source_files={name:base64.b64encode(raw).decode() for name,raw in captures[0].items()}))
            require(prepared.stat().st_size<=48*1024*1024,'UPGRADE_EVIDENCE_BUDGET')
            value=json.loads(prepared.read_bytes());decision=value['decision'];payload=decision['payload'];binding=payload['input_binding']
            require(value['package_sha256']==self.digest and sha256(canonical(payload)).hexdigest()==decision['decision_id'] and sha256(canonical(binding)).hexdigest()==payload['input_id'],'UPGRADE_PREPARED_HASH_CHANGED')
            require(binding['account_id']==state['account_id'] and binding['account_revision']==state['revision'] and binding['selector_profile']==PROFILE_ID and binding['continuous_iterations']==32,'UPGRADE_PREPARED_BINDING_CHANGED')
            files={k:base64.b64decode(v,validate=True) for k,v in value['source_files'].items()}
            require(len(files)<=2000 and sum(map(len,files.values()))<=32*1024*1024,'UPGRADE_SOURCE_BUDGET')
            require(binding['strategy_shares']==state['shares'] and binding['total_uninvested_cash']==state['total_uninvested_cash'],'UPGRADE_ACCOUNT_BINDING_CHANGED')
            require(set(files)==set(binding['source_hashes']) and all(sha256(v).hexdigest()==binding['source_hashes'][k] for k,v in files.items()),'UPGRADE_SOURCE_CLOSURE_CHANGED')
            require(validate_result(payload['search_result'],binding['search_arguments'])==payload['target_quantities'],'UPGRADE_DECISION_CHANGED')
            runtime.selection._fresh(decision,runtime.selection._now());runtime.selection._pins();training,_=runtime.execution_provider.__self__.training()
            require(all(binding['source_hashes'].get(n)==h for n,h in training['source_hashes'].items()),'UPGRADE_TRAINING_SOURCE_CHANGED')
            with closing(self.monthly.accounts._connect(False)) as con:
                try:
                    con.execute('BEGIN IMMEDIATE');current,_=self.monthly.accounts._read(con)
                    require(current==state and self.monthly.current()==prior,'UPGRADE_SNAPSHOT_CHANGED')
                    require(self._package()==p,'UPGRADE_PACKAGE_CHANGED');runtime.selection._pins();runtime.selection._fresh(decision,runtime.selection._now())
                    target=self.monthly.targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id=state['account_id'],target_month=p['target_month'],created_at=self.monthly.clock().isoformat(),request=dict(request,upgrade_package_sha256=self.digest),previous_target_id=prior['target_id'],decision=decision,target_quantities=payload['target_quantities'],runtime_pins=deepcopy(runtime.selection.pins)))
                finally:con.rollback()
            return dict(status='UPGRADE_PUBLISHED',target=target,selection_started=selection_started)


def upgrade_snapshot_provider(*,root,package_path,package_sha256,base_provider,clock,validate_code):
    """Fixed, explicitly reviewed same-month archive extension; no active DB write."""
    from zoneinfo import ZoneInfo
    root=Path(root)
    def read(ref):
        raw=safe_path(root,ref['path']).read_bytes()
        require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==ref['sha256'],'UPGRADE_SNAPSHOT_SOURCE_CHANGED')
        return json.loads(raw)
    def snapshot():
        validate_code();p=read(dict(path=package_path,sha256=package_sha256))
        require(p['schema']=='CONTINUOUS32_RESEARCH_UPGRADE_V1' and p['purpose']=='EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION','UPGRADE_PURPOSE_REQUIRED')
        require(clock().astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')==p['target_month'],'UPGRADE_MONTH_EXPIRED')
        base=base_provider();require(base==p['base_snapshot'],'UPGRADE_BASE_SNAPSHOT_CHANGED')
        old=read(dict(path=base['archive_path'],sha256=base['archive_sha256']));new=read(p['upgrade_archive'])
        require(old['schema'] in {'REAL_STRATEGY_RUNTIME_ARCHIVE_V1','PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'} and new['schema']=='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1' and all(entry in new['entries'] for entry in old['entries']),'UPGRADE_ARCHIVE_HISTORY_CHANGED')
        validate_code()
        return dict(base,archive_path=p['upgrade_archive']['path'],archive_sha256=p['upgrade_archive']['sha256'])
    return snapshot
