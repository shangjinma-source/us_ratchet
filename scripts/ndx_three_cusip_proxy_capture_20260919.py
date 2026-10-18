"""Two fund-manager original voting reports after retained SEC refusals; no retry."""
import json
from pathlib import Path
from types import FunctionType
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_three_historical_cusip_capture_20260919 as capture
BASE=ROOT/'data/cache/research/three_cusip_proxy_capture_20260919_v1'
SOURCE=Path(__file__).resolve()
URLS=(('technology_proxy','https://www.ssga.com/library-content/products/fund-docs/etfs/us/proxy-voting-results/the-technology-select-sector-spdr-fund.pdf'),
      ('energy_equipment_proxy','https://www.ssga.com/library-content/products/fund-docs/etfs/us/proxy-voting-results/spdr-sp-oil-gas-equipment-services-etf.pdf'))

def main():
    BASE.mkdir(exist_ok=False)
    sources={str(p):capture.sha(p.read_bytes()) for p in (SOURCE,Path(capture.__file__).resolve())}
    private=FunctionType(capture.capture.__code__,dict(capture.capture.__globals__,BASE=BASE))
    rows=[private(name,url,sources) for name,url in URLS]
    for p,h in sources.items():
        if capture.sha(Path(p).read_bytes())!=h:raise ValueError('Source changed')
    value=dict(schema='BOUNDED_MANAGER_PROXY_REPORT_CAPTURE_V1',captures=rows,source_hashes=sources,no_retries=True,point_in_time_verified=False,promotion_allowed=False)
    p=BASE/'manifest.json';capture.save(p,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(dict(path=str(p),sha256=capture.sha(p.read_bytes()))))

if __name__=='__main__':main()
