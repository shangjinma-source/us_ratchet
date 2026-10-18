import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_path_comparison_independent_readback_20261003 as m
from scripts import ndx_single_replacement_path_comparison_20261003 as publisher
from test_ndx_single_replacement_path_comparison_20261003 import physical

@contextmanager
def published(root,blocked=False):
    with physical(root,blocked=blocked) as registration:
        comparison=publisher.run(registration_reference=registration,execute=True)['comparison']
        parent=Path(comparison['path']).parent
        publication=dict(path=str(parent/'publication.json'),sha256=m.sha((parent/'publication.json').read_bytes()))
        original_private=m.private
        def private(reference,sources):
            module=original_private(reference,sources)
            if reference['path']==str(m.PRODUCER):
                # Only fixture locations are substituted in the authenticated private
                # module; real load_inputs, project_cases and guard remain executed.
                module.BOUND=publisher.BOUND
                module.FUTURE_PATHS=publisher.FUTURE_PATHS
                module.OUTPUT=publisher.OUTPUT
                module.load_adapter=publisher.load_adapter
            return module
        with patch.multiple(m,PRODUCER_SHA=m.sha(m.PRODUCER.read_bytes()),PARENT=parent,OUTPUT=root/'independent'),patch.object(m,'private',side_effect=private):
            yield dict(registration_reference=registration,comparison_reference=comparison,publication_reference=publication,execute=True)

class Tests(unittest.TestCase):
    def test_physical_twenty_roles_and_private_inspector_no_public_numerics(self):
        from backtest import ndx_single_replacement_path_comparison_research as business
        from backtest import ndx_cash_fork_reference_window_research as metrics
        with tempfile.TemporaryDirectory() as tmp,published(Path(tmp),blocked=True) as arguments:
            with patch.object(business,'compare_selected_single_replacement_paths',side_effect=AssertionError('No comparison recomputation')),patch.object(metrics,'metrics',side_effect=AssertionError('No metrics producer')),patch.object(publisher,'run',side_effect=AssertionError('No publisher execution')):
                reference=m.readback(**arguments)
            report=json.loads(Path(reference['path']).read_bytes())
            self.assertEqual(report['status'],'PASS');self.assertEqual(len(report['input_references']),20)
            self.assertEqual(report['inspection']['scenario_count'],40)
            self.assertEqual(report['inspection']['candidate_status_counts']['NO_FEASIBLE'],1)
            self.assertEqual(report['inspection']['candidate_status_counts']['BLOCKED_TEMPLATE_PRICE_GAP'],1)
            self.assertIs(report['shared_source_authentication_and_case_projection'],True)
            self.assertIs(report['comparison_producer_called'],False)
            with self.assertRaisesRegex(ValueError,'retry'):m.readback(**arguments)

    def test_resigned_saved_drawdown_fails_after_durable_started(self):
        with tempfile.TemporaryDirectory() as tmp,published(Path(tmp)) as arguments:
            document=json.loads((m.PARENT/'comparison.json').read_bytes())
            raw=json.loads((m.PARENT/'raw_comparison.json').read_bytes())
            document['comparison']['rows'][0]['metrics']['candidate']['maximum_drawdown']={'numerator':'999','denominator':'1000'}
            raw['result']=document['comparison']
            raw_bytes=m.encode(raw);(m.PARENT/'raw_comparison.json').write_bytes(raw_bytes)
            document['raw_reference']['sha256']=m.sha(raw_bytes)
            document_bytes=m.encode(document);(m.PARENT/'comparison.json').write_bytes(document_bytes)
            pub=json.loads((m.PARENT/'publication.json').read_bytes())
            pub['raw_reference']=document['raw_reference'];pub['comparison_reference']['sha256']=m.sha(document_bytes)
            pub_bytes=m.encode(pub);(m.PARENT/'publication.json').write_bytes(pub_bytes)
            arguments['comparison_reference']=pub['comparison_reference']
            arguments['publication_reference']['sha256']=m.sha(pub_bytes)
            with self.assertRaises(ValueError):m.readback(**arguments)
            failure=json.loads((m.OUTPUT/'failure.json').read_bytes())
            self.assertIs(failure['arithmetic_inspection_completed'],False)
            self.assertTrue((m.OUTPUT/'started.json').exists())
            with self.assertRaisesRegex(ValueError,'retry'):m.readback(**arguments)

    def test_after_arithmetic_drift_records_completed_but_not_pass(self):
        for target in ('parent','own'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp,published(Path(tmp)) as arguments:
                original=m.save
                def save(name,value):
                    reference=original(name,value)
                    if name=='independent_readback.json':
                        path=m.PARENT/'unregistered.txt' if target=='parent' else m.OUTPUT/'started.json'
                        path.write_bytes(b'late')
                    return reference
                with patch.object(m,'save',side_effect=save),self.assertRaises(ValueError):m.readback(**arguments)
                failure=json.loads((m.OUTPUT/'failure.json').read_bytes())
                self.assertIs(failure['arithmetic_inspection_completed'],True)
                self.assertEqual(failure['status'],'FAILED_DO_NOT_RETRY_OR_CONSUME')
                self.assertTrue((m.OUTPUT/'independent_readback.json').exists())

    def test_default_and_pending_anchors_before_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No source IO')),patch.object(Path,'exists',side_effect=AssertionError('No directory IO')):
            with self.assertRaisesRegex(ValueError,'before IO'):m.readback(execute=True)
            references=dict(registration_reference=dict(path=str(m.ROOT/'reg.json'),sha256='a'*64),comparison_reference=dict(path=str(m.PARENT/'comparison.json'),sha256='b'*64),publication_reference=dict(path=str(m.PARENT/'publication.json'),sha256='c'*64))
            with patch.object(m,'PRODUCER_SHA',None),self.assertRaisesRegex(ValueError,'before IO'):m.readback(**references,execute=True)

if __name__=='__main__':unittest.main()
