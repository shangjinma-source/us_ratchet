"""Create-only publication of the reviewed eight-document mapping extension."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest.ndx_conditional_business_mapping_v2_research import build_conditional_business_mapping_v2


if __name__ == '__main__':
    report = build_conditional_business_mapping_v2()
    source = Path(__file__).resolve()
    report['source_hashes'][str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    output = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/conditional_business_mapping_v2_20260912.json'
    with output.open('x',encoding='utf8') as stream:
        json.dump(report,stream,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        complete_rows=report['input_security_rows'],per_date_mapped=[r['conditionally_mapped_security_count'] for r in report['audit']])))
