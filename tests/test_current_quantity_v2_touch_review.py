import json,unittest
from datetime import datetime,timezone
from hashlib import sha256
from data.current_quantity_v2_touch_review import review_generated_reference
from data.current_research_intraday_execution import decode_intraday_reference

class TouchTests(unittest.TestCase):
    def fixture(self,low=11,capture='2026-10-15T14:02:00+00:00',minute='2026-10-15T14:01:00+00:00'):
        files={};pins={}
        def stamp(s):return int(datetime.fromisoformat(s).timestamp())
        def save(path,value):
            raw=json.dumps(value).encode();files[path]=raw;pins[path]=sha256(raw).hexdigest();return raw
        def make(name,at,minute,low):
            rawpath=name+'.raw';receiptpath=name+'.receipt'
            raw=save(rawpath,{'chart':{'error':None,'result':[{'meta':{'symbol':'AAA','currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1m','regularMarketPrice':12,'regularMarketTime':stamp(at),'currentTradingPeriod':{'regular':{'start':stamp('2026-10-15T13:30:00+00:00'),'end':stamp('2026-10-15T20:00:00+00:00')}}},'timestamp':[stamp(minute)],'indicators':{'quote':[{'open':[12],'high':[13],'low':[low],'close':[12],'volume':[100]}]}}]}})
            save(receiptpath,dict(security_id='A',ticker='AAA',raw_path=rawpath,raw_sha256=pins[rawpath],captured_at=at))
            refs=[dict(role=role,security_id='A',ticker='AAA',original_source_path=path,path=path,sha256=pins[path],captured_at=at) for role,path in [('ORIGINAL_QUOTE',rawpath),('ORIGINAL_QUOTE_RECEIPT',receiptpath)]]
            value=dict(schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',observed_at=at,captures=refs)
            return raw,value
        raw,orig=make('o','2026-10-15T14:00:05+00:00','2026-10-15T13:59:00+00:00',10)
        ref=decode_intraday_reference(raw,ticker='AAA',now=datetime.fromisoformat(orig['observed_at']))
        orig.update(reference_valid_until=ref['refresh_by'],orders=[dict(security_id='A',side='BUY',limit_price='10')],rows=[dict(security_id='A',ticker='AAA',limit_price='10',reference=ref)])
        save('event',orig);_,later=make('l',capture,minute,low);save('later',later)
        return dict(event_path='event',subsequent_event_paths=['later'],files=files,source_hashes=pins),save,orig
    def test_complete_touch_no_touch_partial_and_missing(self):
        for low,status in [(10,'TOUCH_IN_COMPLETE_MINUTE'),(11,'NO_TOUCH_IN_COMPLETE_MINUTES')]:
            args,_,_=self.fixture(low);r=review_generated_reference(**args)['orders'][0];self.assertEqual(r['status'],status);self.assertTrue(r['edge_intervals_not_evaluated'])
        for kwargs in [dict(capture='2026-10-15T14:01:59+00:00'),dict(minute='2026-10-15T14:00:00+00:00')]:
            args,_,_=self.fixture(10,**kwargs);self.assertEqual(review_generated_reference(**args)['orders'][0]['status'],'UNKNOWN')
        args,save,orig=self.fixture();orig['captures']=[];save('event',orig);self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],'SOURCE_EVIDENCE_MISSING')
    def test_unbounded_window_rejected_before_minute_range(self):
        args,save,orig=self.fixture();orig['reference_valid_until']='9999-01-01T00:00:00+00:00';save('event',orig)
        self.assertEqual(review_generated_reference(**args)['reason'],'INVALID_REFERENCE_WINDOW')

    def test_conflict_hash_and_sell(self):
        args,save,orig=self.fixture(10)
        later=json.loads(args['files']['later']);raw=json.loads(args['files']['l.raw']);raw['chart']['result'][0]['indicators']['quote'][0]['low']=[11]
        save('other.raw',raw);receipt=json.loads(args['files']['l.receipt']);receipt.update(raw_path='other.raw',raw_sha256=args['source_hashes']['other.raw']);save('other.receipt',receipt)
        for r,path in zip(later['captures'],['other.raw','other.receipt']):r.update(path=path,original_source_path=path,sha256=args['source_hashes'][path])
        save('other',later);args['subsequent_event_paths'].append('other');self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],'CONFLICTING_MINUTE')
        args['files']['l.raw']+=b' ';self.assertEqual(review_generated_reference(**args)['orders'][0]['status'],'UNKNOWN')
        args,save,orig=self.fixture();orig['orders'][0].update(side='SELL',limit_price='13');orig['rows'][0]['limit_price']='13';save('event',orig);self.assertEqual(review_generated_reference(**args)['orders'][0]['status'],'TOUCH_IN_COMPLETE_MINUTE')

class PullbackTouchTests(unittest.TestCase):
    def fixture(self):
        from test_current_quantity_v2_pullback_sources import payload
        from data.current_quantity_v2_pullback_sources import candidate_from_yahoo_bytes
        files={};pins={}
        def save(path,value):
            raw=value if isinstance(value,bytes) else json.dumps(value).encode();files[path]=raw;pins[path]=sha256(raw).hexdigest();return raw
        captured='2026-10-15T13:32:15+00:00';raw=save('quote.raw',json.dumps(payload()).encode())
        reference=decode_intraday_reference(raw,ticker='SNDK',now=datetime.fromisoformat(captured),captured_at=datetime.fromisoformat(captured))
        candidate=candidate_from_yahoo_bytes(raw=raw,expected_sha256=pins['quote.raw'],security_id='SNDK-ID',ticker='SNDK',session=reference['session'],session_open=reference['session_open'],session_close=reference['session_close'],captured_at=captured,checked_at=captured,now=captured,rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120,previous_cap=None)['candidate']
        reference['pullback']=dict(candidate,prior_cap=None,status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED',cap_record_hash='a'*64)
        save('quote.receipt',dict(security_id='SNDK-ID',ticker='SNDK',raw_path='quote.raw',raw_sha256=pins['quote.raw'],captured_at=captured))
        captures=[dict(role=role,security_id='SNDK-ID',ticker='SNDK',original_source_path=path,path=path,sha256=pins[path],captured_at=captured) for role,path in [('ORIGINAL_QUOTE','quote.raw'),('ORIGINAL_QUOTE_RECEIPT','quote.receipt')]]
        event=dict(schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',observed_at=captured,reference_valid_until=reference['refresh_by'],captures=captures,orders=[dict(security_id='SNDK-ID',side='BUY',limit_price=candidate['limit_price'])],rows=[dict(security_id='SNDK-ID',ticker='SNDK',limit_price=candidate['limit_price'],reference=reference)])
        save('event',event)
        return dict(event_path='event',subsequent_event_paths=[],files=files,source_hashes=pins),save,event
    def test_current_policy_without_prior_recomputes_and_discloses_provenance_limit(self):
        args,save,event=self.fixture();row=review_generated_reference(**args)['orders'][0]
        self.assertEqual(row['reason'],'INCOMPLETE_MINUTE_COVERAGE');self.assertEqual(row['original_rule_verification'],'RAW_MINUTES_FIXED_POLICY_NO_PRIOR_CAP_RECOMPUTED');self.assertFalse(row['cap_history_authenticated'])
        for field,value,expected in [('prior_cap',{'limit_price':'1'},'ORIGINAL_PULLBACK_PRIOR_EVIDENCE_REQUIRED'),('limit_price','1','ORIGINAL_PULLBACK_REPLAY_MISMATCH')]:
            args,save,event=self.fixture();event['rows'][0]['reference']['pullback'][field]=value;save('event',event)
            self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],expected)
    def test_changed_policy_raw_or_order_cannot_bypass(self):
        args,save,event=self.fixture();event['rows'][0]['reference']['pullback']['policy']['rebound_fraction']='1/3';save('event',event)
        self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],'ORIGINAL_PULLBACK_POLICY_UNSUPPORTED')
        args,save,event=self.fixture();event['rows'][0]['limit_price']=event['orders'][0]['limit_price']='1';save('event',event)
        self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],'ORIGINAL_PULLBACK_LIMIT_MISMATCH')
        args,_,_=self.fixture();args['files']['quote.raw']+=b' '
        self.assertEqual(review_generated_reference(**args)['orders'][0]['reason'],'SOURCE_EVIDENCE_MISSING')

if __name__=='__main__':unittest.main()
