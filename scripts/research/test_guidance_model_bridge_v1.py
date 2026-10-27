import copy
from hashlib import sha256
import unittest
from scripts.research.guidance_model_bridge_v1 import compare_model_rows, FIELDS
from scripts.research.test_guidance_numeric_comparator_v1 import fixture


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.sources, self.metadata = [], {}, {}
        for identity, low, high, timestamp in [('previous','100','120','2026-02-01T12:00:00Z'),
                                                ('current','90','110','2026-05-01T12:00:00Z')]:
            record, registry = fixture(low, high, timestamp)
            text = next(iter(registry.values()))['text']
            # Synthetic full document: all metadata labels included for review.
            text += '\n' + '\n'.join(f'{key}: {record[key]}' for key in FIELDS)
            digest = sha256(text.encode()).hexdigest()
            self.rows.append(dict(id=identity, low=low, high=high, quote=text.split('\n')[0]))
            self.sources[identity] = dict(url=record['source_url'], text=text, original_bytes=text.encode(),
                                         original_sha256=digest, text_sha256=digest, full_original_authenticated=True)
            self.metadata[identity] = dict(source_sha256=digest, review_reference='synthetic reviewer fixture',
                fields={key:dict(value=record[key], evidence_text=f'{key}: {record[key]}') for key in FIELDS})

    def test_complete_synthetic_review_connects(self):
        self.assertEqual(compare_model_rows(*self.rows,self.sources,self.metadata)['status'], 'NUMERIC_GUIDANCE_CUT_CANDIDATE')

    def test_model_cannot_approve_missing_review(self):
        self.rows[0].update(provided=True, currency='USD', full_original_authenticated=True)
        self.assertEqual(compare_model_rows(*self.rows,self.sources,{})['status'], 'UNKNOWN')
        for name in FIELDS:
            metadata = copy.deepcopy(self.metadata)
            del metadata['previous']['fields'][name]
            self.assertEqual(compare_model_rows(*self.rows,self.sources,metadata)['status'], 'UNKNOWN')

    def test_excerpt_or_tamper_rejected(self):
        self.sources['previous']['full_original_authenticated'] = False
        self.assertEqual(compare_model_rows(*self.rows,self.sources,self.metadata)['reason'], 'FULL_ORIGINAL_NOT_AUTHENTICATED')
        self.sources['previous']['full_original_authenticated'] = True
        self.sources['previous']['original_bytes'] += b'changed'
        self.assertEqual(compare_model_rows(*self.rows,self.sources,self.metadata)['reason'], 'SOURCE_CONTENT_BINDING_FAILED')

    def test_separate_availability_evidence_must_bind_exact_document(self):
        source = self.sources['previous']
        item = self.metadata['previous']['fields']['publication_datetime']
        evidence = item['evidence_text']
        source['text'] = source['text'].replace('\n' + evidence, '')
        source['original_bytes'] = source['text'].encode()
        digest = sha256(source['original_bytes']).hexdigest()
        source.update(original_sha256=digest, text_sha256=digest)
        self.metadata['previous']['source_sha256'] = digest
        item['availability_reference'] = 'sec-index'
        registry = {'sec-index': dict(text=evidence, text_sha256=sha256(evidence.encode()).hexdigest(),
            original_sha256=digest, document_url=source['url'], reviewed_available_at=item['value'],
            url='https://sec.example/index', review_reference='synthetic independent review')}
        result = compare_model_rows(*self.rows, self.sources, self.metadata, registry)
        self.assertEqual(result['status'], 'NUMERIC_GUIDANCE_CUT_CANDIDATE')
        for key in ('original_sha256', 'document_url', 'text_sha256', 'reviewed_available_at'):
            altered = copy.deepcopy(registry)
            altered['sec-index'][key] = 'wrong'
            self.assertEqual(compare_model_rows(*self.rows, self.sources, self.metadata, altered)['status'], 'UNKNOWN')
        self.assertEqual(compare_model_rows(*self.rows, self.sources, self.metadata)['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
