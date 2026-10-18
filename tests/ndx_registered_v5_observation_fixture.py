"""Full disposable registered V5 actual-observation chain; immutable bound hosts."""
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as gap
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as gap_reader
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as observer
from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
from backtest import ndx_gap_runtime_registration_research_v1 as gap_registration
from backtest import ndx_observation_runtime_registration_research_v1 as observation_registration
from ndx_registered_v5_parent_fixture import physical_registered_gap_parent,reference,envelope


def _capture(root,research,parent,current,name,start,end):
    value=dict(schema=capture_registration.SCHEMA,runtime_reference=reference(capture.SOURCE),
        dependency_references=capture.configured(capture.DEPENDENCIES),parent=parent,
        output_directory=str(research/name),**capture_registration.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(capture.encode(value))
    args=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    with patch.multiple(capture,RESEARCH=research,CURRENT=current),patch.object(capture,'now',side_effect=[start,end]):saved=capture.run(**args)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current):
        audit=capture_reader.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            **saved,output_directory=str(research/(name+'_audit')),execute=True)
    refs=dict(reference=saved['capture_reference'],publication_reference=saved['publication_reference'],readback_reference=audit,reader_reference=reference(capture_reader.SOURCE))
    return refs,args


def _gap(root,research,parent,current,captures,name):
    value=dict(schema=gap_registration.SCHEMA,runtime_reference=reference(gap.SOURCE),dependency_references=gap.configured(),
        parent=parent,capture=captures,output_directory=str(research/name),**gap_registration.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(gap.encode(value))
    args=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    with patch.multiple(gap,RESEARCH=research,CURRENT=current):saved=gap.run(**args)
    with patch.multiple(gap_reader,RESEARCH=research,CURRENT=current):
        audit=gap_reader.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            **saved,output_directory=str(research/(name+'_audit')),execute=True)
    refs=dict(reference=saved['history_reference'],publication_reference=saved['publication_reference'],readback_reference=audit,reader_reference=reference(gap_reader.SOURCE))
    return refs,args


def physical_registered_v5_observation(root,research):
    """Return (true V5 parent4, actual observation4, context), sequence73.

    Creates all evidence through the bound registered runtimes/readers. Only
    temporary RESEARCH/CURRENT and recorded capture/writer clocks are patched.
    Call once per fresh temporary root; no pending pins or source rewrites.
    """
    root=Path(root).resolve();research=Path(research).resolve()
    initial,initial_context=physical_registered_gap_parent(root,research)
    live_folder=root/'registered_observation_live';live_folder.mkdir(exist_ok=False);current={}
    initial_history=envelope(initial)['document']['history']
    for ticker in ('QQQ','SPY'):
        current[ticker]=live_folder/(ticker+'.csv')
        current[ticker].write_bytes(Path(initial_history['full_capture_source_references'][ticker]['path']).read_bytes())
    gap_capture,gap_capture_args=_capture(root,research,initial,current,'registered_observation_gap_capture',
        '2026-10-13T20:03:00+00:00','2026-10-13T20:03:01+00:00')
    parent,gap_args=_gap(root,research,initial,current,gap_capture,'registered_observation_gap_parent')
    candidate,candidate_args=_capture(root,research,parent,current,'registered_observation_unique_capture',
        '2026-10-13T20:05:00+00:00','2026-10-13T20:05:01+00:00')
    value=dict(schema=observation_registration.SCHEMA,runtime_reference=reference(writer.SOURCE),
        dependency_references={role:dict(path=str(path),sha256=digest)for role,(path,digest)in writer.DEPENDENCIES.items()},
        parent=parent,capture=candidate,output_directory=str(research/'registered_observation_actual'),**observation_registration.FLAGS)
    path=root/'registered_observation_actual_registration.json';path.write_bytes(writer.encode(value))
    args=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    with patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(writer,'now',side_effect=[
            '2026-10-13T20:06:00+00:00','2026-10-13T20:06:01+00:00','2026-10-13T20:06:02+00:00']):receipt=writer.run(**args)
    payload=writer.decode(Path(receipt['path']).read_bytes())['payload_reference']
    with patch.multiple(observer,RESEARCH=research,CURRENT=current):
        audit=observer.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],payload_reference=payload,receipt_reference=receipt,execute=True)
    observation=dict(payload_reference=payload,receipt_reference=receipt,audit_reference=audit,reader_reference=reference(observer.SOURCE))
    return parent,observation,dict(root=root,research=research,current=current,initial_parent=initial,initial_context=initial_context,
        gap_capture=gap_capture,gap_capture_arguments=gap_capture_args,gap_arguments=gap_args,capture=candidate,capture_arguments=candidate_args,
        observation_arguments=args,observation_registration=reference(path))
