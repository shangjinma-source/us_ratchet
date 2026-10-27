import importlib.util
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from data import news_desk as module


class ProvenanceTests(unittest.TestCase):
    def test_cached_analysis_preserves_each_source_limitation_and_provenance(self):
        for kind,warnings in [('RSS_EXCERPT',['RSS excerpt only']),
                              ('ISSUER_RELEASE_BODY',['Issuer assertion only','Truncated to 6000 characters'])]:
            with self.subTest(kind=kind),TemporaryDirectory() as folder:
                event=dict(id='a',title='Results announcement',url='https://example.com/a',source='issuer',
                    published_at='2026-10-26T12:00:00Z',source_text='Public facts with sufficient source detail. '*10,
                    tickers=['MRNA'],content_kind=kind,content_sha256='a'*64,uncertainty=warnings,
                    collected_at='2026-10-26T13:00:00Z')
                original=deepcopy(event)
                public=[module.analysis_public_event(event)]
                key=sha256(json.dumps(dict(version=module.PROMPT_VERSION,model=module.MODEL,effort='medium',events=public),sort_keys=True).encode()).hexdigest()
                result=dict(events=[dict(id='a',summary='Summary',evidence=[event['url']],uncertainty=[],
                    mechanism='Mechanism',horizon='Days',importance='medium',strategy_effect='NO_CHANGE_RESEARCH_ONLY')])
                cache=Path(folder)/'analysis';cache.mkdir();(cache/f'{key}.json').write_text(json.dumps(result))
                with patch.object(module.subprocess,'Popen',side_effect=AssertionError('No model calls')):
                    value=module.analyze(dict(events=[event]),folder)
                self.assertEqual(value['analysis_summary']['status'],'CACHED')
                self.assertEqual(event['source_uncertainty'],warnings)
                self.assertEqual(event['uncertainty'],warnings)
                self.assertEqual(event['analysis_uncertainty'],[])
                for field in ('url','source','published_at','collected_at','source_text','content_kind','content_sha256'):
                    self.assertEqual(event[field],original[field])
                self.assertEqual(module.analysis_public_event(event),public[0])

    def test_reanalysis_replaces_model_caveats_without_losing_source_or_cache_scope(self):
        event=dict(uncertainty=['source'])
        module.merge_analysis(event,dict(uncertainty=['old model','source']))
        module.merge_analysis(event,dict(uncertainty=['new model']))
        self.assertEqual(event['uncertainty'],['source','new model'])
        self.assertEqual(event['source_uncertainty'],['source'])


if __name__=='__main__':unittest.main()
