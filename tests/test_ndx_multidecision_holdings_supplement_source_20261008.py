"""Complete physical synthetic parents; no original account invocation."""
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch
import test_ndx_multidecision_holdings_supplement_research as fixtures
from scripts import ndx_multidecision_holdings_supplement_20261008 as source


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = source.encode(value);path.write_bytes(blob)
    return dict(path=str(path), sha256=source.sha(blob))


def environment(directory):
    root = Path(directory);args = fixtures.fixture();refs = {}
    for role, prefix in (('candidate', 'MULTIDECISION_STATEFUL_ACCOUNT'), ('control', 'MULTIDECISION_ORIGINAL_EIGHT')):
        for stage in ('inputs', 'execution'):
            key = role + '_' + stage;parent = root / key;audit_root = root / (key + '_audit')
            reader = root / (key + '_reader.py');reader.write_text('raise AssertionError("No parent execution")')
            readerref = dict(path=str(reader), sha256=source.sha(reader.read_bytes()))
            schema = prefix + '_INPUTS' if stage == 'inputs' else ('MULTIDECISION_ACCOUNT_EXECUTION' if role == 'candidate' else 'MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION')
            doc = args[key];doc['source_hashes'] = {};inspection_rows = []
            if stage == 'execution':
                doc['input_references'] = {label: refs[role + '_inputs' + suffix] for label, suffix in [('inputs',''),('publication','_publication'),('readback','_audit'),('reader','_reader')]}
                doc['source_hashes'] = {item['path']: item['sha256'] for item in doc['input_references'].values()}
                for index, row in enumerate(doc['rows']):
                    folder = parent / 'tracks' / f'{index:02d}'
                    row['started_reference'] = write(folder / 'started.json', dict(input_references=doc['input_references']))
                    row['postcheck_reference'] = write(folder / 'postcheck.json', dict(outcome=row['outcome']))
                    bundle = args['raw_documents'][role][index]
                    if bundle is not None:
                        raw = bundle['document'];raw['started_reference'] = row['started_reference'];raw['input_references'] = doc['input_references']
                        row['raw_reference'] = write(folder / 'raw_result.json', raw)
                    inspection_rows.append(dict(track_index=index, coordinate=[row['fx_mode'],row['lane'],row['track']], outcome=row['outcome'],
                        saved_references={name: row[name] for name in ('started_reference','raw_reference','postcheck_reference')}, inspection=None if bundle is None else dict(status='PASS')))
            started = write(parent / 'started.json', dict(source_hashes=doc['source_hashes']))
            refkey = 'inputs_reference' if stage == 'inputs' else 'result_reference'
            docref = write(parent / ('inputs.json' if stage == 'inputs' else 'result.json'), doc)
            status = 'PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK' if stage == 'execution' else ('PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS' if role == 'candidate' else 'PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS')
            pub = dict(schema=schema+'_PUBLICATION_V1', status=status, source_hashes=doc['source_hashes'], started_reference=started, point_in_time_verified=False,promotion_allowed=False)
            pub[refkey] = docref
            if stage == 'execution':pub['input_references'] = doc['input_references']
            pubref = write(parent / 'publication.json', pub)
            sources = {**doc['source_hashes'], **{item['path']:item['sha256'] for item in (docref,pubref,readerref,started)}}
            for row in inspection_rows:
                for item in row['saved_references'].values():
                    if item is not None:sources[item['path']] = item['sha256']
            audit = dict(schema=schema+'_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=readerref['sha256'], publication_reference=pubref,source_hashes=sources,point_in_time_verified=False,promotion_allowed=False)
            audit[refkey]=docref
            if stage == 'execution':audit['rows']=inspection_rows
            auditref = write(audit_root / 'independent_readback.json', audit)
            write(audit_root / 'started.json', {refkey:docref,'publication_reference':pubref,'source_hashes':sources})
            refs.update({key:docref,key+'_publication':pubref,key+'_audit':auditref,key+'_reader':readerref})
    return dict(BOUND={key:(value['path'],value['sha256']) for key,value in refs.items()},PURE_SHA=source.sha(source.PURE.read_bytes()),OUTPUT=root/'output')


class Tests(unittest.TestCase):
    def test_full_physical_source_and_create_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.multiple(source, **environment(directory)):
                ref=source.run(execute=True);doc=json.loads(Path(ref['path']).read_bytes())
                self.assertEqual(doc['supplement']['counts']['saved_risk_rows'],2400)
                self.assertEqual(doc['supplement']['counts']['missing_risk_rows'],480)
                self.assertEqual({p.name for p in source.OUTPUT.iterdir()},{'started.json','supplement.json','publication.json'})
                with self.assertRaises(ValueError):source.run(execute=True)

    def test_pending_failed_or_unindexed_source_stops_before_output(self):
        for attack in ('pending','failure','orphan'):
            with self.subTest(attack=attack),tempfile.TemporaryDirectory() as directory:
                env=environment(directory)
                if attack=='pending':env['PURE_SHA']=None
                else:(Path(env['BOUND']['candidate_execution'][0]).parent/('failure.json' if attack=='failure' else 'extra.json')).write_text('{}')
                with patch.multiple(source,**env):
                    with self.assertRaises(ValueError):source.run(execute=True)
                    self.assertFalse(source.OUTPUT.exists())


if __name__=='__main__':unittest.main()
