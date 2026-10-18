"""Synthetic V3 writer boundaries; actual future evidence remains unbound."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from backtest import ndx_forward_gap_parent_capture_research_v3 as pure
from test_ndx_forward_gap_parent_capture_research_v3 import fixture
from test_ndx_prospective_gap_history_research_v3 import reference
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments as payload_arguments


def checker():
    return writer.private_module(writer.CHECKER.read_bytes(),writer.CHECKER,writer.CHECKER_SHA,'_writer_test_checker')


def documents(new_dates=('2026-10-08',)):
    args=fixture(new_dates,start='2026-10-08T20:00:00+00:00')
    parent=args['parent'];plan=pure.plan_gap_parent_capture(**args);check=checker()
    refs={role:reference('next-capture/'+role)for role in writer.ROLES}
    producer=reference('next-producer');core=reference('next-core')
    sources=deepcopy(plan['source_reference_claims'])
    for item in (producer,core):writer.merge(sources,item)
    flags=dict.fromkeys(check.FALSE_FIELDS,False)
    inputs=dict(pure=core)
    doc=dict(schema='SOURCE_BOUND_FORWARD_GAP_PARENT_CAPTURE_V3',plan=plan,
        parent_references={role:parent[role]for role in writer.ROLES},input_references=inputs,
        source_hashes=sources,clock_captured_by_runner=True,external_clock_attestation_verified=False,
        quote_source_type='EXISTING_LOCAL_CACHE_READ_NO_NETWORK_REFRESH',
        current_cache_verification_scope='CAPTURE_INTERVAL_AND_PUBLICATION_GUARDS_ONLY_NOT_PERSISTENT_SOURCE_CLOSURE',
        captured_artifacts=dict(args['source_references'],tzif=args['tzif_reference']),
        current_cache_references={t:dict(path=str(writer.ROOT/'data/cache'/f'{t}.csv'),sha256=args['source_references'][t]['sha256'])for t in ('QQQ','SPY')},
        capture_started_at=args['capture_started_at'],capture_completed_at=args['capture_completed_at'],**flags)
    pub=dict(schema='FORWARD_GAP_PARENT_CAPTURE_PUBLICATION_V3',status='PUBLISHED_CAPTURE_PLAN_NOT_OBSERVATION',
        capture_reference=refs['reference'],source_hashes=deepcopy(sources),**flags)
    audited=deepcopy(sources)
    for item in refs.values():writer.merge(audited,item)
    audit=dict(schema='FORWARD_GAP_PARENT_CAPTURE_INDEPENDENT_READBACK_V3',status='PURE_FORWARD_GAP_CAPTURE_READBACK_PASS',
        capture_reference=refs['reference'],publication_reference=refs['publication_reference'],reader_sha256=refs['reader_reference']['sha256'],
        parent_references=doc['parent_references'],input_references=inputs,producer_reference=producer,source_hashes=audited,
        entire_plan_independently_reconstructed=True,snapshot_bytes_verified=True,producer_called=False,new_pure_called=False,
        plan_gap_parent_capture_called=False,current_live_cache_read_or_reverified=False,external_clock_attestation_verified=False,
        counts=dict(status=plan['status'],parent_typed_row_count=69,parent_actual_observation_count=1,parent_gap_count=8,
            candidate_session=plan['candidate_session'],diagnostic_count=len(plan['diagnostics']),
            snapshot_counts={t:plan['source_evidence'][t]['original_row_count']for t in ('QQQ','SPY')}),**flags)
    return parent,dict(document=doc,publication=pub,readback=audit,**refs),producer,core


class V3WriterTests(unittest.TestCase):
    def test_candidate_v3_baseline_roles_and_original_month(self):
        p,c,producer,core=documents()
        with patch.multiple(writer,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core):
            self.assertEqual(writer.validate_capture(p,c,checker()),'2026-10-08')
        self.assertEqual(c['document']['plan']['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')

    def test_no_new_and_bad_readback_or_attempt_or_baseline_rejected(self):
        mutations=[lambda p,c:c['readback'].update(status='PASS'),
            lambda p,c:p['document']['history']['parent_attempt_inventory'].clear(),
            lambda p,c:c['document']['plan'].update(accounted_baseline_references=p['document']['history']['baseline_references']),
            lambda p,c:c['readback']['counts'].update(parent_actual_observation_count=True),
            lambda p,c:c['readback'].update(plan_gap_parent_capture_called=True)]
        for mutate in mutations:
            p,c,producer,core=documents();mutate(p,c)
            with patch.multiple(writer,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),self.assertRaises(ValueError):
                writer.validate_capture(p,c,checker())
        p,c,producer,core=documents(())
        with patch.multiple(writer,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),self.assertRaises(ValueError):
            writer.validate_capture(p,c,checker())

    def test_all_future_pins_before_any_io(self):
        valid={role:reference('future/'+role)for role in writer.ROLES}
        for missing in (*writer.ROLES,'producer','core'):
            bound=deepcopy(valid);producer=reference('producer');core=reference('core')
            if missing in bound:bound[missing]=None
            elif missing=='producer':producer=None
            else:core=None
            with (patch.multiple(writer,CAPTURE_BOUND=bound,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
                  patch.object(Path,'exists',side_effect=AssertionError('IO'))):
                with self.assertRaisesRegex(ValueError,'Pending immutable'):writer.run(execute=True)

    def test_fixed_private_core_unaffected_by_sysmodules(self):
        with patch.dict('sys.modules',{'backtest.ndx_prospective_observation_receipt_research':None}):
            module=writer.private_module(writer.CORE.read_bytes(),writer.CORE,writer.CORE_SHA,'_private_test_payload')
            self.assertTrue(callable(module.prepare_observation_payload))
        with self.assertRaises(ValueError):writer.private_module(b'bad',writer.CORE,writer.CORE_SHA,'_bad')

    def test_attempts_arbitrary_namespace_partial_and_failure_cannot_bypass(self):
        for kind in ('start','payload','receipt','failure'):
            with tempfile.TemporaryDirectory()as tmp:
                folder=Path(tmp)/'arbitrary';folder.mkdir()
                name,obj={'start':('started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V2'}),
                    'payload':('observation_payload.json',{'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'}),
                    'receipt':('receipt.json',{'schema':'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'}),
                    'failure':('failure.json',{'status':'FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'})}[kind]
                (folder/name).write_text(json.dumps(obj))
                parent=fixture()['parent'];parent['document']['history']['observations']=[]
                with patch.object(writer,'RESEARCH',Path(tmp)),self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR'):
                    writer.attempt_inventory(parent,{})

    def test_resolved_attempt_inventory_and_new_attempt_detected(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);folder=root/'random';folder.mkdir()
            payload={'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','observation_id':'a'*64}
            payload_path=folder/'observation_payload.json';payload_path.write_bytes(writer.encode(payload))
            payload_ref=dict(path=str(payload_path),sha256=writer.sha(payload_path.read_bytes()))
            receipt={'schema':'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1','payload_reference':payload_ref}
            receipt_path=folder/'receipt.json';receipt_path.write_bytes(writer.encode(receipt))
            (folder/'started.json').write_bytes(writer.encode({'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V1'}))
            entry=dict(payload_reference=payload_ref,receipt_reference=dict(path=str(receipt_path),sha256=writer.sha(receipt_path.read_bytes())),observation_id='a'*64)
            parent={'document':{'history':{'observations':[entry]}}}
            with patch.object(writer,'RESEARCH',root):
                original=writer.attempt_inventory(parent,{})
                self.assertEqual(len(original),1)
                extra=root/'new-name';extra.mkdir();(extra/'started.json').write_bytes(writer.encode({'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V3'}))
                with self.assertRaises(ValueError):writer.attempt_inventory(parent,{})

    def test_temp_writer_preserves_late_fact_and_no_new_month(self):
        core,data,args=payload_arguments()
        args.pop('writer_started_at_utc');args.pop('writer_completed_at_utc')
        claims=core.prepare_observation_payload(**args,writer_started_at_utc='2026-10-09T14:00:00+00:00',writer_completed_at_utc='2026-10-09T14:00:01+00:00')['source_hash_claims']
        refs=dict(parent={role:reference('p/'+role)for role in writer.ROLES},capture={role:reference('c/'+role)for role in writer.ROLES})
        loaded=(args,refs,claims,core,lambda:None,{},dict(path=str(writer.CHECKER),sha256=writer.CHECKER_SHA))
        with tempfile.TemporaryDirectory()as tmp:
            out=Path(tmp)/'attempt'
            with (patch.multiple(writer,OUTPUT=out,CAPTURE_BOUND=refs['capture'],CAPTURE_PRODUCER=reference('prod'),CAPTURE_CORE=reference('capcore')),
                  patch.object(writer,'load_inputs',return_value=loaded),patch.object(writer,'resource_gate'),
                  patch.object(writer,'now',side_effect=['2026-10-09T14:00:00+00:00','2026-10-09T14:00:01+00:00','2026-10-09T14:00:02+00:00'])):
                receipt=writer.run(execute=True)
            payload=writer.decode((out/'observation_payload.json').read_bytes());r=writer.decode(Path(receipt['path']).read_bytes())
            self.assertEqual(payload['sequence'],70);self.assertFalse(payload['month_first_actual_observation'])
            self.assertEqual(r['timing_classification'],'LATE_OBSERVATION');self.assertEqual(payload['writer_adapter_schema'],writer.ADAPTER)
            self.assertTrue(all(payload[k]is False for k in writer.FLAGS))


if __name__=='__main__':unittest.main()
