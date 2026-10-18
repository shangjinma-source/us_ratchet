"""Three accession-addressed public filing mirrors, explicitly not SEC transport."""
import json
from pathlib import Path
from types import FunctionType
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_three_historical_cusip_capture_20260919 as capture
BASE=ROOT/'data/cache/research/three_cusip_mirror_capture_20260919_v1'
PARENT=capture.BASE/'manifest.json';PARENT_SHA='a284757f9cc856a52353b19fbd9c9733688280cd485c89ced8266586a8cfd689'

def main():
    if capture.sha(PARENT.read_bytes())!=PARENT_SHA:raise ValueError('Historical selections changed')
    parent=json.loads(PARENT.read_bytes());BASE.mkdir(exist_ok=False)
    sources=dict(parent['source_hashes']);sources[str(PARENT)]=PARENT_SHA
    p=Path(__file__).resolve();sources[str(p)]=capture.sha(p.read_bytes())
    private=FunctionType(capture.capture.__code__,dict(capture.capture.__globals__,BASE=BASE))
    rows=[]
    for selection in parent['selections']:
        url=f"https://cdn.yahoofinance.com/prod/sec-filings/{selection['cik']}/{selection['accession'].replace('-','')}/{selection['primary_document']}"
        row=private(selection['ticker']+'_mirror',url,sources);row['original_selection']=selection;rows.append(row)
    for p,h in sources.items():
        if capture.sha(Path(p).read_bytes())!=h:raise ValueError('Source changed')
    report=dict(schema='THREE_ACCESSION_FILING_MIRROR_CAPTURE_V1',captures=rows,source_hashes=sources,official_sec_transport=False,no_retries=True,point_in_time_verified=False)
    p=BASE/'manifest.json';capture.save(p,(json.dumps(report,sort_keys=True,indent=2)+'\n').encode());print(json.dumps(dict(path=str(p),sha256=capture.sha(p.read_bytes()))))

if __name__=='__main__':main()
