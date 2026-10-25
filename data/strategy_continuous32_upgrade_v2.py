"""Versioned blob-backed upgrade; original one-shot claims remain untouched.

All source budgets and durable evidence readback precede the selection claim.
Existing unknown claims still require review; this is not a reselection recovery.
"""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from contextlib import closing
import json
from core.strategy_account_ledger import canonical,require
from data.strategy_continuous32_upgrade import Continuous32ResearchUpgrade
from data.strategy_profiled_runtime_archive import require_archived_configuration
from data.strategy_continuous32_target_decision import PROFILE_ID,validate_result
from data.strategy_continuous32_target_service import StrategyContinuous32TargetService
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data.strategy_upgrade_blob_store_v1 import validate_files,save_sources,load_sources
from scripts.register_quantity_v2_paper_protocol import safe_path


class Continuous32ResearchUpgradeV2(Continuous32ResearchUpgrade):
    def _capture(self,runtime,state):
        value=super()._capture(runtime,state)
        sources=value['source_package']
        validate_files(sources['files'],sources['source_hashes'])
        return value

    def _package(self):
        package=super()._package()
        for name in ('data/strategy_continuous32_upgrade_v2.py',
                     'data/strategy_upgrade_blob_store_v1.py'):
            expected=package['source_hashes'].get(name)
            require(expected and sha256(safe_path(self.root,name).read_bytes()).hexdigest()==expected
                    and sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()==expected,
                    'UPGRADE_V2_IMPLEMENTATION_CHANGED')
        return package

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
                require(not directory.exists(), 'UPGRADE_SOURCE_STORAGE_RECOVERY_REQUIRED')
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
                require(not directory.exists(), 'UPGRADE_SOURCE_STORAGE_RECOVERY_REQUIRED')
                validated_evidence=self._capture(runtime,state)
                sources=validated_evidence['source_package']
                validate_files(sources['files'],sources['source_hashes'])
                require(self.monthly.current()==prior and self._package()==p,'UPGRADE_PREFLIGHT_CHANGED')
                directory.mkdir(parents=True,exist_ok=True)
                source_reference=save_sources(directory/'sources-v2',sources['files'],sources['source_hashes'])
                require(self.monthly.accounts.read()==state and self.monthly.current()==prior and self._package()==p,'UPGRADE_PREFLIGHT_CHANGED')
                from data.strategy_account_target_inputs import build_target_inputs
                build_target_inputs(state=state,now=self.monthly.clock().isoformat(),
                    maximum_mark_age_seconds=runtime.selection.age,**validated_evidence)
                runtime.selection._pins()
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
                require(captures[0]==sources['files'],'UPGRADE_SELECTION_SOURCE_CHANGED')
                self._write(prepared,dict(schema='UPGRADE_PREPARED_BLOBS_V2',package_sha256=self.digest,decision=decision,source_reference=source_reference))
            require(prepared.stat().st_size<=48*1024*1024,'UPGRADE_EVIDENCE_BUDGET')
            value=json.loads(prepared.read_bytes())
            require(set(value)=={'schema','package_sha256','decision','source_reference'} and value['schema']=='UPGRADE_PREPARED_BLOBS_V2','UPGRADE_PREPARED_SCHEMA')
            decision=value['decision'];payload=decision['payload'];binding=payload['input_binding']
            require(value['package_sha256']==self.digest and sha256(canonical(payload)).hexdigest()==decision['decision_id'] and sha256(canonical(binding)).hexdigest()==payload['input_id'],'UPGRADE_PREPARED_HASH_CHANGED')
            require(binding['account_id']==state['account_id'] and binding['account_revision']==state['revision'] and binding['selector_profile']==PROFILE_ID and binding['continuous_iterations']==32,'UPGRADE_PREPARED_BINDING_CHANGED')
            files=load_sources(directory/'sources-v2',value['source_reference'])
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
