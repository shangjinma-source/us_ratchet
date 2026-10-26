import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from data.news_desk import parse_feed,published,command,analyze,save_snapshot

class NewsDeskTests(unittest.TestCase):
    def test_real_timestamp_not_fetch_substitute(self):
        raw=b'<rss><channel><item><title>Fact</title><link>https://example.com/a</link><description>&lt;b&gt;Hello&lt;/b&gt;</description></item></channel></rss>'
        event=parse_feed(raw,dict(name='official',tickers=['NVDA'],relevance='company'),'2026-10-27T00:00:00+00:00')[0]
        self.assertIsNone(event['published_at']);self.assertEqual(event['summary'],'Hello');self.assertEqual(event['analysis_status'],'NOT_ANALYZED')

    def test_unsafe_link_excluded(self):
        self.assertEqual(parse_feed(b'<rss><item><title>x</title><link>javascript:alert(1)</link></item></rss>',{},'now'),[])

    def test_no_implicit_timezone(self):self.assertIsNone(published('Mon, 26 Oct 2026 12:00:00'))

    def test_cli_explicit_model_no_shell_or_config(self):
        args=command('codex',Path('work'),Path('schema'),Path('answer'))
        self.assertIn('gpt-6.1-sol',args);self.assertIn('--ignore-user-config',args)
        self.assertIn('read-only',args);self.assertIn('shell_tool',args);self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)

    def test_missing_cli_preserves_real_article(self):
        with TemporaryDirectory() as directory:
            event=dict(id='a',title='fact',url='https://example.com/a',source='official',published_at=None,source_text='body '*30,tickers=[],summary='body')
            snapshot=dict(events=[event])
            with patch('data.news_desk.shutil.which',return_value=None):analyze(snapshot,directory,limit=1)
            self.assertEqual(event['summary'],'body');self.assertEqual(snapshot['analysis_summary']['status'],'FAILED')
            self.assertEqual(snapshot['analysis_summary']['attempts'],0)

    def test_exact_disabled_host_warning_only(self):
        from data.news_desk import validate_trace_item
        validate_trace_item(dict(type='error',message='Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; enable `features.code_mode_host` and install `codex-code-mode-host`.'))
        with self.assertRaises(RuntimeError):validate_trace_item(dict(type='error',message='unknown failure'))
        with self.assertRaises(RuntimeError):validate_trace_item(dict(type='command_execution',command='whoami'))

    def test_metadata_skipped_without_cli(self):
        with TemporaryDirectory() as directory:
            event=dict(source='SEC issuer',source_text='metadata '*30)
            with patch('data.news_desk.shutil.which',side_effect=AssertionError('No CLI expected')):
                snapshot=analyze(dict(events=[event]),directory)
            self.assertEqual(snapshot['analysis_summary']['attempts'],0)
            self.assertEqual(event['analysis_status'],'SKIPPED_METADATA_ONLY')

    def test_budget_rejected(self):
        with self.assertRaises(ValueError):analyze({},'.',limit=100)

    def test_atomic_snapshot(self):
        with TemporaryDirectory() as directory:
            path=save_snapshot({'events':[]},directory)
            self.assertTrue(path.exists());self.assertFalse(path.with_suffix('.pending.json').exists())

if __name__=='__main__':unittest.main()
