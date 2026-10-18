from copy import deepcopy
from datetime import timedelta
import json
import base64
from hashlib import sha256
import unittest
from data.current_quantity_v2_bounded_unit_review import BoundedPublicUnitReview
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_service import decode_execution_package
from data.current_quantity_v2_paper_chain import build_continuation
from test_current_quantity_v2_current_cash_continuation_sources import SourcesTests


def feed(title='Unrelated market notice'):
    return ('<rss><channel><title>Nasdaq</title><item><title>'+title+'</title><description>Public notice</description><pubDate>Thu, 15 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>').encode()

class BoundedTests(SourcesTests):
    # Reuse actual tiny decision/ledger fixture, not mocked pure approval.
    def setup_bounded(self,title='Unrelated market notice'):
        state,source,clock,calls=self.fixture();rss=[]
        reader=BoundedPublicUnitReview(fetch=lambda:(rss.append(1) or {'status':200,'body':feed(title)}),clock=lambda:clock[0])
        source.unit_review_reader=reader
        return state,source,clock,calls,rss

    def test_bounded_capture_replay_no_additional_fetch(self):
        state,source,clock,calls,rss=self.setup_bounded();r=source.capture(state)
        package=source.resolve(r['account_id'],r['decision_id'])
        inputs=decode_execution_package(package,needed={'A','B'},now=clock[0])
        result=build_continuation(state,execution_inputs=inputs,now=clock[0])
        self.assertEqual(result['binding']['target_quantities'],{'A':6,'B':4})
        self.assertFalse(result['unit_review']['coverage_complete']);self.assertEqual(len(rss),1)
        bad=deepcopy(inputs);bad['unit_continuity']['A']['bounded_evidence']['files'].pop(next(iter(bad['unit_continuity']['A']['bounded_evidence']['files'])))
        with self.assertRaisesRegex(ValueError,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):build_continuation(state,execution_inputs=bad,now=clock[0])
        bad=deepcopy(inputs);e=bad['unit_continuity']['A']['bounded_evidence'];p=e['rss_raw_path'];raw=feed('Different unrelated notice');e['files'][p]=base64.b64encode(raw).decode();e['source_hashes'][p]=sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):build_continuation(state,execution_inputs=bad,now=clock[0])
        with self.assertRaises(ValueError):build_continuation(state,execution_inputs=inputs,now=clock[0]+timedelta(seconds=121))

    def test_alias_future_candidate_and_constructor_zero_io(self):
        reader=BoundedPublicUnitReview(fetch=lambda:self.fail('constructor fetch'),clock=lambda:self.fail('constructor clock'))
        state,source,clock,_,_=self.setup_bounded('Example Holdings future reorganization')
        original=source.fetch
        def named(ticker):
            d=json.loads(original(ticker));d['chart']['result'][0]['meta']['longName']='Example Holdings';return canonical(d)
        source.fetch=named
        with self.assertRaisesRegex(ValueError,'BOUNDED_UNIT_CHANGE_CANDIDATE'):source.capture(state)
        state,source,clock,_,_=self.setup_bounded();source.unit_review_reader.fetch=lambda:{'status':200,'body':b'<html>error</html>'}
        with self.assertRaisesRegex(ValueError,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):source.capture(state)

    def test_candidates_transport_and_raw_action_block(self):
        state,source,clock,_,_=self.setup_bounded('AAA announces split')
        with self.assertRaisesRegex(ValueError,'BOUNDED_UNIT_CHANGE_CANDIDATE'):source.capture(state)

    def test_publication_anomalies_and_encoded_name_block(self):
        for published in (b'',b'Sat, 17 Oct 2026 08:00:00 GMT'):
            state,source,clock,_,_=self.setup_bounded()
            raw=feed().replace(b'Thu, 15 Oct 2026 08:00:00 GMT',published)
            source.unit_review_reader.fetch=lambda:{'status':200,'body':raw}
            with self.assertRaisesRegex(ValueError,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):source.capture(state)
        state,source,clock,_,_=self.setup_bounded('Example&amp;nbsp;&lt;b&gt;Holdings&lt;/b&gt; split')
        original=source.fetch
        def named(ticker):
            d=json.loads(original(ticker));d['chart']['result'][0]['meta']['longName']='Example Holdings';return canonical(d)
        source.fetch=named
        with self.assertRaisesRegex(ValueError,'BOUNDED_UNIT_CHANGE_CANDIDATE'):source.capture(state)

    def test_ticker_boundary_transport_and_raw_action(self):
        state,source,clock,_,_=self.setup_bounded('XAAAX unrelated')
        source.capture(state) # ticker boundary, not substring
        source.unit_review_reader.fetch=lambda:{'status':503,'body':feed()}
        with self.assertRaisesRegex(ValueError,'BOUNDED_PUBLIC_REVIEW_UNAVAILABLE'):source.capture(state)
        state,source,clock,_,_=self.setup_bounded();original=source.fetch
        def action(ticker):
            d=json.loads(original(ticker));d['chart']['result'][0]['events']={'splits':{'x':{'date':1}}};return canonical(d)
        source.fetch=action
        with self.assertRaisesRegex(ValueError,'BOUNDED_UNIT_CHANGE_CANDIDATE'):source.capture(state)

if __name__=='__main__':unittest.main()
