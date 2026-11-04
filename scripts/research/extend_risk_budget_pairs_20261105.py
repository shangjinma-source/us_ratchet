"""On-demand frozen (decision, SID) gross returns; zero network/account replay."""
import gzip,json,hashlib
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
PARENT='tmp/risk_budget_64d_inventory_20261105/risk_inputs.json'
PARENT_SHA='c1fbdb4891d573be29657238dc8f4718d7685edb6769edbada1e3ceeae1c4592'

class PairCompiler:
    def __init__(self):
        self.pins={};self.cache={};self.windows={}
        self.parent=self.read(PARENT,PARENT_SHA)
        for path,expected in self.parent['source_hashes'].items():self.verify(path,expected)
        for label,path in [('early','tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'),
                           ('later','tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json')]:
            prepared=self.read(path,self.parent['source_hashes'][path])
            for outer in prepared['windows']:
                w=outer.get('window',outer);date=w.get('decision_cutoff',w.get('decision_date'))
                self.windows[(label,date)]=w
    def verify(self,path,expected):
        actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('SOURCE_HASH_MISMATCH:'+path)
        self.pins[path]=actual
    def read(self,path,expected=None):
        if path in self.cache:return self.cache[path]
        raw=(ROOT/path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
        if expected is not None and actual!=expected:raise ValueError('SOURCE_HASH_MISMATCH:'+path)
        self.pins[path]=actual
        value=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=str)
        self.cache[path]=value;return value
    def receipt(self,source,ticker):
        folder=Path(source).parent
        manifest=folder/'manifest.json'
        if (ROOT/manifest).exists():
            d=self.read(manifest.as_posix())
            matches=[r for r in d.get('rows',[]) if r.get('ticker')==ticker and r.get('sha256')==self.pins[source]]
            if len(matches)==1:return matches[0],manifest.as_posix()
        receipt=folder/(ticker+'.receipt.json')
        if (ROOT/receipt).exists():return self.read(receipt.as_posix()),receipt.as_posix()
        raise ValueError('EXPLICIT_EVENTS_REQUEST_RECEIPT_MISSING')
    def compile_pair(self,label,date,sid):
        """Reuses admitted same-date returns or compiles a complete no-event window.

        Eventful new pairs remain blocked until their exact coordinate mapping is
        reviewed; existing economic/supplement review is not an automatic wildcard.
        """
        existing=next(r for r in self.parent['windows'] if r['window']==label and r['decision_date']==date)
        if sid in existing['arguments']['stock_gross_returns']:
            return dict(status='CONDITIONAL_INPUT_READY',gross=existing['arguments']['stock_gross_returns'][sid],basis='PARENT_ALREADY_REVIEWED_PAIR')
        w=self.windows[(label,date)];days=w['training_dates'][-64:]
        c=next(c for c in w['candidates'] if c.get('security_id')==sid)
        if c['status']!='READY_CONDITIONAL' or len(c.get('training_close',[]))!=253:raise ValueError('TRAINING_NOT_READY')
        ticker=c['ticker'];source=c['training_source'].replace('\\','/')
        body=self.read(source)['chart']['result'][0]
        receipt,receipt_path=self.receipt(source,ticker)
        requested=parse_qs(urlparse(receipt.get('request_url',receipt.get('url',''))).query).get('events',[])
        if receipt.get('http_status')!=200 or not requested or not {'div','splits'}<=set(requested[0].split(',')):raise ValueError('EXPLICIT_SUCCESSFUL_DIV_SPLIT_REQUEST_REQUIRED')
        recorded=receipt.get('raw_sha256',receipt.get('sha256'))
        if recorded and recorded!=self.pins[source]:raise ValueError('RECEIPT_RAW_HASH_MISMATCH')
        if receipt.get('body_truncated'):raise ValueError('TRUNCATED_SOURCE')
        if body['meta']['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH')
        for kind,events in body.get('events',{}).items():
            for event in events.values():
                eday=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
                if days[0]<eday<=date:raise ValueError('EVENTFUL_PAIR_NEEDS_EXPLICIT_MAPPING:'+kind+':'+eday)
        if ticker in {'EXC','WDC','HON','CMCSA','ILMN','MTCH','AZN','TRI'}:raise ValueError('COMPLEX_TRAINING_COORDINATE_REVIEW_REQUIRED')
        rawprices={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():F(str(body['indicators']['quote'][0]['close'][i]))
                   for i,t in enumerate(body['timestamp']) if body['indicators']['quote'][0]['close'][i] is not None}
        values=list(map(F,c['training_close'][-64:]))
        if not set(days)<=set(rawprices):raise ValueError('SOURCE_64_DAY_GAP')
        factors={values[i]/rawprices[d] for i,d in enumerate(days)}
        if len(factors)!=1:raise ValueError('NONCONSTANT_TRAINING_SOURCE_COORDINATE')
        gross={d:str(values[i]/values[i-1]) for i,d in enumerate(days) if i}
        if set(gross)!=set(existing['arguments']['qqq_gross_returns']):raise ValueError('QQQ_DATE_MISMATCH')
        for i,d in enumerate(days[1:],1):
            if F(gross[d])!=rawprices[d]/rawprices[days[i-1]]:raise ValueError('INDEPENDENT_RAW_RETURN_MISMATCH')
        return dict(status='CONDITIONAL_INPUT_READY',gross=gross,basis='COMPLETE_LOCAL_NO_REPORTED_EVENT_WINDOW',
                    ticker=ticker,source=source,receipt_path=receipt_path,source_sha256=self.pins[source],
                    first_close=days[0],last_close=date,training_to_raw_factor=str(next(iter(factors))),
                    limits='Explicit div/splits provider request and full64 closes; no reported interval events, not exhaustive official/PIT certification.')

def main():
    compiler=PairCompiler()
    label,date,sid='early','2021-02-26','research:security:pton'
    result=compiler.compile_pair(label,date,sid)
    extension=deepcopy(compiler.parent)
    row=next(r for r in extension['windows'] if r['window']==label and r['decision_date']==date)
    row['arguments']['stock_gross_returns'][sid]=result['gross']
    row['extension_pair_evidence']=[dict(decision_date=date,security_id=sid,**{k:v for k,v in result.items() if k!='gross'})]
    extension['parent_artifact']=dict(path=PARENT,sha256=PARENT_SHA)
    extension['extension_scope']='One explicitly requested PTON pair; baseline targets/equity unchanged; dynamic callers supply current targets/equity.'
    extension['source_hashes'].update(compiler.pins)
    extension['source_hashes'][Path(__file__).relative_to(ROOT).as_posix()]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    out=ROOT/'tmp/risk_budget_pair_extension_20261105';out.mkdir(exist_ok=True)
    (out/'risk_inputs_pton_v1.json').write_text(json.dumps(extension,indent=2),encoding='utf8')
    # Inventory only frozen best_by_k frontier supports, no new optimization.
    inventory=[]
    for label,base in [('early','tmp/recent_continuous_baseline_20261026_v7'),('later','tmp/old_continuous_baseline_20261026_v9')]:
        for (window,date),training in compiler.windows.items():
            if window!=label:continue
            selection=compiler.read(base+'/'+date+'.selection.json')
            sids=set()
            for record in selection['raw_selection']['search_result']['best_by_k'].values():
                sids.update(s for s,q in record['quantities'].items() if q>0)
            for sid in sorted(sids):
                try:r=compiler.compile_pair(label,date,sid);status=r['basis']
                except (ValueError,KeyError,IndexError,StopIteration) as error:status='BLOCKED:'+str(error)
                inventory.append(dict(window=label,date=date,security_id=sid,status=status))
    counts={}
    for r in inventory:counts[r['status']]=counts.get(r['status'],0)+1
    (out/'frontier_local_inventory.json').write_text(json.dumps(dict(rows=inventory,counts=counts,source_hashes=compiler.pins,network_calls=0,economic_runs=0),indent=2),encoding='utf8')
    print(json.dumps(dict(extension_sha256=hashlib.sha256((out/'risk_inputs_pton_v1.json').read_bytes()).hexdigest(),pair_status=result['status'],frontier_pairs=len(inventory),counts=counts)))

if __name__=='__main__':main()
