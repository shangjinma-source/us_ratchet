"""Run the existing monthly continuity reviewer from a journal-admitted parent."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import pinned, reject_links
from data.strategy_verified_context_monthly_capture_v1 import capture_session
from data.strategy_verified_context_monthly_normalizer_v1 import (
    NORMALIZATION_CODE_PATHS, derive_identity_binding, normalize_verified_capture,
)


def capture_registered_continuity(*, root, directory, security_id, parent, configuration,
        authority, read_binding, expected_binding, clock, fetch_daily=None, fetch_official=None):
    root=Path(root).absolute();directory=Path(directory).absolute();reject_links(directory)
    require(directory.resolve().is_relative_to(root.resolve()) and directory.resolve()!=root.resolve(),
            'PAPER_CONTINUITY_ROOT')
    require(not directory.exists(),'PAPER_CONTINUITY_RECOVERY_REQUIRED')
    require(read_binding()==expected_binding,'PAPER_CONTINUITY_SNAPSHOT_CHANGED')
    raw=parent['receipt_bytes'];digest=parent['trusted_parent_sha256']
    require(sha256(raw).hexdigest()==digest,'PAPER_CONTINUITY_PARENT_HASH')
    receipt=json.loads(raw);files=parent['files']
    require(set(files)==set(receipt['source_sha256']) and len(files)<=2000 and
        sum(map(len,files.values()))<=32*1024*1024 and all(
            sha256(body).hexdigest()==receipt['source_sha256'][name] for name,body in files.items()),
        'PAPER_CONTINUITY_PARENT_CLOSURE')
    inputs=json.loads(files[receipt['normalized_inputs_path']])
    require(security_id in inputs['histories'],'PAPER_CONTINUITY_PARENT_SECURITY')
    directory.mkdir(parents=True,exist_ok=False)
    workspace=directory/'source-root';workspace.mkdir()
    def save(name,body):
        require(type(name)is str and '\\' not in name and ':' not in name and
            not PurePosixPath(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')),
            'PAPER_CONTINUITY_SOURCE_PATH')
        path=workspace/name;reject_links(path);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():require(path.read_bytes()==body,'PAPER_CONTINUITY_SOURCE_COLLISION')
        else:
            with path.open('xb') as stream:stream.write(body)
        require(path.read_bytes()==body,'PAPER_CONTINUITY_SOURCE_READBACK')
        return dict(path=name,sha256=sha256(body).hexdigest())
    try:
        for name,body in files.items():save(name,body)
        reference=save('paper-registered-parents/'+digest+'.json',raw)
        identity_raw=derive_identity_binding(root=workspace,parent_reference=reference,security_id=security_id)
        identity=save('paper-derived-identities/'+sha256(identity_raw).hexdigest()+'.json',identity_raw)
        calendar=configuration['calendar'];save(calendar['path'],pinned(root,calendar))
        pins=[]
        for name in sorted(NORMALIZATION_CODE_PATHS):
            body=authority['descriptor_arguments']['code_bytes'][name]
            require((Path(__file__).resolve().parents[1]/name).read_bytes()==body,'PAPER_CONTINUITY_EXECUTING_CODE')
            pins.append(save(name,body))
        config=dict(schema='SERVER_MONTHLY_WINDOW_CAPTURE_V1',calendar=calendar,identity_review=identity,
            security=json.loads(identity_raw)['security'],source_pins=pins,
            monthly_decision_date=configuration['monthly_decision_date'],
            output_root='paper-continuity-capture/'+sha256(security_id.encode()).hexdigest())
        config_raw=canonical(config);config_hash=sha256(config_raw).hexdigest()
        captured=capture_session(root=workspace,configuration_bytes=config_raw,configuration_sha256=config_hash,
            execute=True,fetch_daily=fetch_daily,fetch_official=fetch_official,clock=clock)
        require(captured['status']=='CAPTURED_MONTHLY_WINDOW_UNIT_REVIEW_REQUIRED','PAPER_CONTINUITY_CAPTURE_INCOMPLETE')
        reviewed=normalize_verified_capture(root=workspace,capture_directory=captured['output'],
            expected_configuration_sha256=config_hash,parent_reference=reference,clock=clock)
        require(reviewed['status']=='CONDITIONAL_HISTORY_READY_NOT_ACCOUNT_ADMITTED',
            reviewed.get('reason','PAPER_CONTINUITY_REVIEW_FAILED'))
        require(read_binding()==expected_binding,'PAPER_CONTINUITY_SNAPSHOT_CHANGED')
        with (directory/'complete.json').open('xb') as stream:
            stream.write(canonical(dict(status=reviewed['status'],parent_sha256=digest,
                source_operation_id=parent['source_operation_id'],
                receipt_sha256=sha256(canonical(reviewed['receipt'])).hexdigest(),account_mutated=False)))
        return reviewed
    except BaseException as error:
        with (directory/'failed.json').open('xb') as stream:
            stream.write(canonical(dict(status='FAILED_PRESERVED',reason=str(error),automatic_retry=False)))
        raise
