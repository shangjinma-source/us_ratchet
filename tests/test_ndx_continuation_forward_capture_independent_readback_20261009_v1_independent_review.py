"""Independent controlled-shared-API tests, not real R2/continuous acceptance."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_continuation_forward_capture_independent_readback_20261009_v1 as reader
from test_ndx_continuation_forward_capture_independent_readback_20261009_v1 import reader_fixture, run_reader
from test_ndx_continuation_forward_capture_runtime_20261009_v1_independent_review import run_pipeline


def rewrite(context,published,document,publication,started=None):
    folder=Path(published['capture_reference']['path']).parent
    if started is not None:(folder/'started.json').write_bytes(reader.encode(started))
    (folder/'capture.json').write_bytes(reader.encode(document))
    result=deepcopy(published)
    result['capture_reference']=reader.reference(str(folder/'capture.json'),reader.digest((folder/'capture.json').read_bytes()))
    publication['capture_reference']=result['capture_reference']
    (folder/'publication.json').write_bytes(reader.encode(publication))
    result['publication_reference']=reader.reference(str(folder/'publication.json'),reader.digest((folder/'publication.json').read_bytes()))
    return result


class IndependentContinuationCaptureReaderTests(unittest.TestCase):
    def test_unknown_headers_private_input_and_self_role_reject_before_trap(self):
        with TemporaryDirectory(prefix='INDEPENDENT_C_READER_HEADERS_') as directory:
            context=reader_fixture(Path(directory));published=run_pipeline(context)
            d=reader.decode(Path(published['capture_reference']['path']).read_bytes())
            p=reader.decode(Path(published['publication_reference']['path']).read_bytes())
            trap=Path(directory)/'NEVER_READ';trap.write_bytes(b'TRAP');ref=reader.reference(str(trap),reader.digest(b'TRAP'))
            original=reader.consume
            def guarded(item,sources,**kwargs):
                if item['path']==str(trap):raise AssertionError('Artifact trap selected IO')
                return original(item,sources,**kwargs)
            for attack in ('unknown_B','unknown_C','private_I','wrong_role','wrong_self'):
                with self.subTest(attack=attack):
                    doc=deepcopy(d);pub=deepcopy(p)
                    if attack=='unknown_B':doc['implementation_pair_binding_reference']=ref
                    elif attack=='unknown_C':doc['consumer_role_registry_reference']=ref
                    elif attack=='private_I':doc['reader_input_references']={'runtime':ref}
                    elif attack=='wrong_role':doc['consumer_role']='gap_publisher'
                    doc['source_hashes'][str(trap)]=ref['sha256'];pub['source_hashes'][str(trap)]=ref['sha256']
                    changed=rewrite(context,published,doc,pub)
                    family=context['replay'].inspect_host_continuation_family
                    def wrong_family(**kwargs):
                        value=family(**kwargs)
                        if attack=='wrong_self':value['consumer_registry_view']['consumer_references']['capture_independent_reader']=ref
                        return value
                    with patch.object(context['replay'],'inspect_host_continuation_family',side_effect=wrong_family),patch.object(reader,'consume',side_effect=guarded),self.assertRaises(ValueError):
                        run_reader(context,changed)
                    self.assertFalse((context['research']/'capture_reader').exists())

    def test_resigned_all_source_maps_missing_or_extra_do_not_authorize_io(self):
        with TemporaryDirectory(prefix='INDEPENDENT_C_READER_SOURCE_MAPS_') as directory:
            context=reader_fixture(Path(directory));published=run_pipeline(context)
            folder=Path(published['capture_reference']['path']).parent
            d=reader.decode((folder/'capture.json').read_bytes());p=reader.decode((folder/'publication.json').read_bytes());s=reader.decode((folder/'started.json').read_bytes())
            trap=Path(directory)/'UNAUTHORIZED_SOURCE';trap.write_bytes(b'TRAP');ref=reader.reference(str(trap),reader.digest(b'TRAP'))
            for attack in ('omit_B','omit_K','omit_peer','omit_metadata','extra'):
                with self.subTest(attack=attack):
                    doc,pub,start=deepcopy(d),deepcopy(p),deepcopy(s)
                    key={'omit_B':context['args']['implementation_pair_binding_path'],'omit_K':str(reader.ANCESTRY_CONTRACT[0]),
                        'omit_peer':context['stub']['path'],'omit_metadata':str(reader.CONSUMER_METADATA_CORE[0])}.get(attack)
                    for obj in (doc,pub,start):
                        if attack=='extra':obj['source_hashes'][ref['path']]=ref['sha256']
                        else:del obj['source_hashes'][key]
                    changed=rewrite(context,published,doc,pub,start)
                    original=reader.consume
                    def guarded(item,sources,**kwargs):
                        if item['path']==ref['path']:raise AssertionError('Source claims authorized IO')
                        return original(item,sources,**kwargs)
                    with patch.object(reader,'consume',side_effect=guarded),self.assertRaisesRegex(ValueError,'Whole independent continuation capture'):
                        run_reader(context,changed)
                    self.assertFalse((context['research']/'capture_reader').exists())

    def test_independent_code_current_exclusion_report_and_final_start_guard(self):
        for attack in (False,True):
            with self.subTest(post_report_start_drift=attack),TemporaryDirectory(prefix='INDEPENDENT_C_READER_OUTPUT_') as directory:
                context=reader_fixture(Path(directory));published=run_pipeline(context)
                original_compile=reader.compile_private;original_read=Path.read_bytes;original_save=reader.save_bytes
                denied={reader.canonical_path(str(reader.ROOT/reader.DEPENDENCIES[key][0])) for key in ('capture_core','scoped','base')}
                denied|={reader.canonical_path(str(reader.PREFIX_CORE[0])),reader.canonical_path(str(reader.GAP_CORE[0]))}
                def compile_guard(path,*args,**kwargs):
                    if reader.canonical_path(str(path)) in denied:raise AssertionError('Business code executed')
                    return original_compile(path,*args,**kwargs)
                def read_guard(path):
                    if path in context['current'].values():raise AssertionError('Reader read live cache')
                    return original_read(path)
                def save_guard(path,raw):
                    result=original_save(path,raw)
                    if attack and path.name=='independent_readback.json':
                        start=path.parent/'started.json';start.write_bytes(original_read(start)+b'\n')
                    return result
                with patch.object(reader,'compile_private',side_effect=compile_guard),patch.object(Path,'read_bytes',read_guard),patch.object(reader,'save_bytes',side_effect=save_guard):
                    if attack:
                        with self.assertRaisesRegex(ValueError,'Source SHA changed'):run_reader(context,published)
                    else:result=run_reader(context,published)
                output=context['research']/'capture_reader'
                if attack:
                    failure=reader.decode((output/'failure.json').read_bytes())
                    for key in reader.FLAGS:self.assertIs(failure[key],False)
                    with self.assertRaisesRegex(ValueError,'create-only'):run_reader(context,published)
                else:
                    report=reader.decode(Path(result['path']).read_bytes());start=reader.decode((output/'started.json').read_bytes())
                    self.assertEqual(set(x.name for x in output.iterdir()),{'started.json','independent_readback.json'})
                    self.assertEqual(len(report['reader_input_references']),13)
                    self.assertEqual(start['reader_input_references'],report['reader_input_references'])
                    for obj in (start,report):
                        for key in reader.FLAGS:self.assertIs(obj[key],False)
                    for path,sha in report['source_hashes'].items():self.assertEqual(reader.digest(Path(path).read_bytes()),sha)


if __name__=='__main__':unittest.main()
