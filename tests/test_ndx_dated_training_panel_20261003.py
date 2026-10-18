"""Only synthetic 77 fixtures and temporary failed publication."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_training_panel_20261003 as m
from backtest import ndx_dated_training_panel_research as core
from test_ndx_dated_training_panel_research import fixture as pure_fixture


def fixture():
    args=pure_fixture();source=args['channels_document'];source['source_hashes']={}
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in m.BOUND};refs['channels']=args['channels_reference'];refs['parent_panel']=args['parent_panel_reference'];refs['channels_readback']=args['independent_readback_reference']
    pub=dict(schema='BULK_LONG_WINDOW_CHANNELS_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_INDEPENDENT_READBACK',channels_reference=refs['channels'],source_hashes={},point_in_time_verified=False,legal_training_input_admitted=False,fit_performed=False)
    audit=dict(schema='BULK_LONG_WINDOW_CHANNELS_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256=refs['channels']['sha256'],publication_sha256=refs['channels_publication']['sha256'],reader_sha256=refs['channels_reader']['sha256'],security_count=77,issuer_count=76,training_return_rows=9702,evaluation_return_rows=9702,original_provenance_count=101,preserved_sidecar_count=7,point_in_time_verified=False,legal_training_input_admitted=False,fit_performed=False,per_channel=[])
    for row in source['rows']:
        c=row['channel'];c.update(raw_reference=dict(path=c['ticker']+'.raw',sha256='b'*64),receipt_reference=dict(path=c['ticker']+'.receipt',sha256='c'*64),quote_rows_sha256='d'*64)
        audit['per_channel'].append(dict(ticker=c['ticker'],**{k:deepcopy(c[k]) for k in ('raw_reference','receipt_reference','quote_rows_sha256','training_returns_sha256','evaluation_returns_sha256')}))
    columns=list(source['rows'][0]['coordinate']);universe=dict(columns=columns,data=[[r['coordinate'][k] for k in columns] for r in source['rows']])
    parent=dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',panel=dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1',universe=universe,observed_provenance_and_missing=deepcopy(source['original_provenance_and_missing'])),**deepcopy(source['preserved_evidence_sidecars']))
    return dict(channels=source,channels_publication=pub,channels_readback=audit,parent_panel=parent),refs


class WrapperTests(unittest.TestCase):
    def test_projection_integration(self):
        docs,refs=fixture();args=m.project_inputs(docs,refs);panel=core.prepare_dated_training_panel(**args);m.validate_result(panel,args)
        self.assertEqual(panel['fit_payload']['cutoff'],'2026-03-20');self.assertEqual(panel['preserved_evidence_sidecars'],docs['channels']['preserved_evidence_sidecars'])

    def test_readback_scope_and_coordinates_fail_closed(self):
        changes=[lambda d:d['channels_readback'].update(training_return_rows=True),lambda d:d['channels_readback']['per_channel'][0].update(training_returns_sha256='e'*64),lambda d:d['parent_panel']['panel']['universe']['data'][0].__setitem__(0,'RENAMED'),lambda d:d['channels_publication'].update(point_in_time_verified=0)]
        for change in changes:
            with self.subTest(change=change):
                docs,refs=fixture();change(docs)
                with self.assertRaises(ValueError):m.project_inputs(docs,refs)

    def test_false_execute_and_existing_namespace(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',side_effect=AssertionError('not requested')):
            self.assertEqual(m.run()['status'],'NOT_EXECUTED')
            with self.assertRaises(ValueError):m.run(execute=1)
            m.OUTPUT.mkdir()
            with self.assertRaises(ValueError):m.run(execute=True)

    def test_runtime_and_source_guard_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source';p.write_bytes(b'old');sources={str(p):m.sha(b'old')};run=m.runtime();m.guard(sources,run)
            p.write_bytes(b'new')
            with self.assertRaises(ValueError):m.guard(sources,run)
            with patch.object(m,'runtime',return_value=dict(changed=True)):
                with self.assertRaises(ValueError):m.guard({},run)

    def test_postwrite_failure_preserved_no_retry(self):
        docs,refs=fixture();panel=dict(fixture=True)
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=(docs,refs,{},m.runtime(),core)),patch.object(m,'project_inputs',return_value={}),patch.object(core,'prepare_dated_training_panel',return_value=panel),patch.object(m,'validate_result'),patch.object(m,'guard',side_effect=[None,None,ValueError('late drift')]):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'panel.json').exists());self.assertTrue((m.OUTPUT/'publication.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
