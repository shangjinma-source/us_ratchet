"""Full physical IO integration in disposable synthetic namespaces only.

The fixed actual V3 parent is read-only. Every Oct8 future source/capture/receipt
in this test is synthetic and temporary; no formal research output is created.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_forward_gap_parent_source_capture_20261009_v3 as capture_producer
from scripts import ndx_forward_gap_parent_capture_independent_readback_20261009_v3 as capture_reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from scripts import ndx_prospective_observation_independent_readback_v3_20261009 as reader


def write(path,value,raw=False):
    blob=value if raw else writer.encode(value)
    path.write_bytes(blob)
    return {'path':str(path),'sha256':writer.sha(blob)}


def physical_capture(root):
    """Build a fully physical synthetic future capture around the fixed real parent."""
    p=capture_producer;r=capture_reader
    initial={str(p.SOURCE):p.LOADED_SHA}
    dependencies=p.configured(p.DEPENDENCIES)
    raw={key:p.consume(item,initial) for key,item in dependencies.items()}
    pure_ref=p.reference(str(p.PURE),p.PURE_SHA)
    raw['pure']=p.consume(pure_ref,initial)
    parents=p.configured(p.PARENT_BOUND);parent=p.load_parent(parents,initial);h=parent['document']['history']
    baseline={t:p.consume(h['captured_source_references'][t],initial) for t in r.TICKERS}
    actual={t:p.consume(h['baseline_references'][t],initial) for t in r.TICKERS}
    tzif=p.consume(h['tzif_reference'],initial)
    folder=root/'synthetic_capture';folder.mkdir()
    current={t:baseline[t]+b'2026-10-08,100,110,90,100,1000\n' for t in r.TICKERS}
    snapshots={t:write(folder/(t+'.csv'),current[t],True) for t in r.TICKERS}
    tzref=write(folder/'New_York.tzif',tzif,True)
    core=p.private_core(raw)
    start='2026-10-08T20:00:00+00:00';end='2026-10-08T20:00:01+00:00'
    plan=core.plan_gap_parent_capture(parent=parent,source_bytes=current,source_references=snapshots,
        accounted_baseline_bytes=baseline,actual_baseline_bytes=actual,capture_started_at=start,
        capture_completed_at=end,tzif_bytes=tzif,tzif_reference=tzref)
    sources=dict(initial)
    for item in (*snapshots.values(),tzref):p.merge(sources,item)
    inputs=dict(dependencies,pure=pure_ref,tzif=h['tzif_reference'])
    started=write(folder/'started.json',dict(schema='FORWARD_GAP_PARENT_CAPTURE_STARTED_V3',
        parent_references=parents,input_references=inputs,source_hashes=initial,retry_allowed=False,**p.FLAGS))
    capture=write(folder/'capture.json',dict(schema='SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3',
        plan=plan,parent_references=parents,input_references=inputs,captured_artifacts=dict(snapshots,tzif=tzref),
        current_cache_references={t:{'path':str(p.CURRENT[t]),'sha256':snapshots[t]['sha256']} for t in r.TICKERS},
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        capture_started_at=start,capture_completed_at=end,clock_captured_by_runner=True,
        external_clock_attestation_verified=False,quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        source_hashes=sources,**p.FLAGS))
    publication=write(folder/'publication.json',dict(schema='FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3',
        status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',capture_reference=capture,source_hashes=sources,**p.FLAGS))
    audited=dict(sources)
    for item in (capture,publication,started,{'path':str(r.SOURCE),'sha256':r.LOADED_SHA}):p.merge(audited,item)
    audit_folder=root/'synthetic_capture_audit';audit_folder.mkdir()
    write(audit_folder/'started.json',{'schema':'SYNTHETIC_CAPTURE_AUDIT_START'})
    audit=write(audit_folder/'independent_readback.json',dict(schema='FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3',
        status='PURE_FORWARD_GAP_CAPTURE_READBACK_PASS',capture_reference=capture,publication_reference=publication,
        parent_references=parents,input_references=inputs,producer_reference={'path':str(p.SOURCE),'sha256':p.LOADED_SHA},
        reader_sha256=r.LOADED_SHA,source_hashes=audited,counts=dict(status=plan['status'],parent_typed_row_count=69,
        parent_actual_observation_count=1,parent_gap_count=8,candidate_session='2026-10-08',diagnostic_count=0,
        snapshot_counts={t:plan['source_evidence'][t]['original_row_count'] for t in r.TICKERS}),
        entire_plan_independently_reconstructed=True,producer_called=False,new_pure_called=False,snapshot_bytes_verified=True,
        plan_gap_parent_capture_called=False,current_live_cache_read_or_reverified=False,
        external_clock_attestation_verified=False,started_reference_observed_not_external_anchor=started,
        started_externally_authenticated=False,**dict.fromkeys(r.FALSE_FIELDS,False)))
    return dict(reference=capture,publication_reference=publication,readback_reference=audit,
        reader_reference={'path':str(r.SOURCE),'sha256':r.LOADED_SHA}), {'path':str(p.SOURCE),'sha256':p.LOADED_SHA},pure_ref


class FullTemporaryReaderTests(unittest.TestCase):
    def test_real_load_inputs_and_readback_physical_closure_then_createonly(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_v3_') as folder:
            root=Path(folder);captures,producer,core=physical_capture(root);output=root/'synthetic_observation'
            with (patch.multiple(writer,OUTPUT=output,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
                  patch.object(writer,'now',side_effect=['2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00','2026-10-09T13:30:00+00:00'])):
                receipt_ref=writer.run(execute=True)
            payload_ref={'path':str(output/'observation_payload.json'),'sha256':writer.sha((output/'observation_payload.json').read_bytes())}
            with patch.multiple(reader,BASE=output,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core,
                WRITER=(str(writer.SOURCE),writer.LOADED_SHA),PAYLOAD_SHA=payload_ref['sha256'],RECEIPT_SHA=receipt_ref['sha256']):
                result=reader.readback(execute=True)
                report=reader.decode(Path(result['path']).read_bytes())
                self.assertEqual(report['status'],'PASS')
                self.assertEqual(report['counts']['parent_typed_row_count'],69)
                self.assertEqual(report['counts']['parent_actual_observation_count'],1)
                self.assertEqual(report['counts']['parent_gap_count'],8)
                self.assertEqual(report['counts']['timing_classification'],'LATE_OBSERVATION')
                self.assertFalse(report['counts']['month_first_actual_observation'])
                self.assertFalse(report['writer_called']);self.assertFalse(report['payload_core_called'])
                self.assertTrue(all(report[key] is False for key in reader.WRITER_FALSE))
                for path,digest in report['source_hashes'].items():self.assertEqual(writer.sha(Path(path).read_bytes()),digest)
                with self.assertRaises(ValueError):reader.readback(execute=True)
                self.assertFalse((output/'failure.json').exists())

    def test_physical_source_claim_lie_is_rejected_and_preserved(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_v3_claim_') as folder:
            root=Path(folder);captures,producer,core=physical_capture(root);output=root/'synthetic_observation'
            with (patch.multiple(writer,OUTPUT=output,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
                  patch.object(writer,'now',side_effect=['2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00','2026-10-08T20:01:02+00:00'])):
                writer.run(execute=True)
            # Coordinated evidence tampering is externally re-pinned in this test.
            # The independently derived producer source closure must still reject it.
            docs={name:reader.decode((output/name).read_bytes()) for name in ('started.json','observation_payload.json','receipt.json')}
            for doc in docs.values():doc['source_hashes']['synthetic-forged-authority']='f'*64
            write(output/'started.json',docs['started.json'])
            payload_ref=write(output/'observation_payload.json',docs['observation_payload.json'])
            docs['receipt.json']['payload_reference']=payload_ref
            receipt_ref=write(output/'receipt.json',docs['receipt.json'])
            with patch.multiple(reader,BASE=output,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core,
                WRITER=(str(writer.SOURCE),writer.LOADED_SHA),PAYLOAD_SHA=payload_ref['sha256'],RECEIPT_SHA=receipt_ref['sha256']):
                with self.assertRaisesRegex(ValueError,'Independent complete producer source closure'):
                    reader.readback(execute=True)
                failure=reader.decode((output/'failure.json').read_bytes())
                self.assertEqual(failure['status'],'INDEPENDENT_READBACK_FAILED_NO_RETRY')
                self.assertTrue(failure['partial_evidence_preserved'])
                self.assertFalse((output/'independent_readback.json').exists())
                self.assertTrue((output/'observation_payload.json').is_file())
                with self.assertRaises(ValueError):reader.readback(execute=True)

    def test_physical_capture_inventory_and_snapshot_drift_stop_before_current_output(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_v3_drift_') as folder:
            root=Path(folder);captures,producer,core=physical_capture(root)
            output=root/'synthetic_observation'
            with patch.multiple(reader,BASE=output,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core,
                WRITER=(str(writer.SOURCE),writer.LOADED_SHA),PAYLOAD_SHA='a'*64,RECEIPT_SHA='b'*64):
                extra=root/'synthetic_capture/extra';extra.mkdir()
                with self.assertRaisesRegex(ValueError,'Exact immutable namespace'):reader.load_inputs()
                extra.rmdir()
                (root/'synthetic_capture/QQQ.csv').write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError,'Pinned bytes'):reader.load_inputs()
                self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
