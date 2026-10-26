import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('candidate_news_content',Path(__file__).resolve().parents[1]/'docs/candidates/news_content_gate.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class NewsContentTests(unittest.TestCase):
    def test_long_headline_is_not_body(self):
        title='Federal Reserve '+('headline '*20)
        self.assertEqual(module.analysis_skip_reason(dict(title=title,source_text='<b>'+title.upper()+'</b>')),'SKIPPED_INSUFFICIENT_TEXT')
    def test_real_extra_body_allowed(self):
        self.assertIsNone(module.analysis_skip_reason(dict(title='Announcement',source_text='The company reported revenue and provided a detailed outlook for the upcoming fiscal year.')))
    def test_metadata_and_awards_skipped(self):
        self.assertEqual(module.analysis_skip_reason(dict(content_kind='SEC_METADATA_ONLY')),'SKIPPED_METADATA_ONLY')
        self.assertEqual(module.analysis_skip_reason(dict(title='Award',source_text='body '*40,noise_hint='LOW_INFORMATION_EMPLOYER_AWARD')),'SKIPPED_LOW_INFORMATION')

if __name__=='__main__':unittest.main()
