"""Explicitly approved short official accounting inference, never signal data."""
from pathlib import Path
from hashlib import sha256
import json
ROOT=Path(__file__).resolve().parents[2]
REVIEW='tmp/pullback_action_sources_20261105/anss_root_review.json'
EXPECTED='80c82bd34eefa7f64837c1f9c5e20d40244d65ed31f6363e64f62e9f88b28710'
def need(ok,why):
 if not ok:raise ValueError(why)
def append_review(document,review,window):
 raw=(ROOT/REVIEW).read_bytes();need(sha256(raw).hexdigest()==EXPECTED,'ROOT_REVIEW_PIN');approval=json.loads(raw);path=approval['evidence_path'];raw=(ROOT/path).read_bytes();need(sha256(raw).hexdigest()==approval['evidence_sha256'],'EVIDENCE_PIN');evidence=json.loads(raw);pins={REVIEW:EXPECTED,path:approval['evidence_sha256'],**evidence['source_hashes']}
 for p,h in pins.items():need(sha256((ROOT/p).read_bytes()).hexdigest()==h,'SOURCE_PIN:'+p)
 early=window=='2021_2023';sid='research:security:anss' if early else 'security:0001013462:03662Q105';start,end=approval['intervals'][0 if early else 1];source='tmp/andrewmvd_inventory_20261025/ANSS_stocks.csv' if early else 'tmp/anss_terminal_bridge_20261026/ANSS_price_candidate.csv'
 need(document['assembled']['price_source_references'][sid]==[source] and document['source_hashes'][source]==pins[source],'EXACT_PRICE_BINDING')
 begins=[d for d in document['assembled']['session_dates'] if start<=d<end] if early else [start]
 rows=[dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=sid,ticker='ANSS',start_exclusive=d,end_inclusive=end,selected_price_sources=[source],source_references=[REVIEW,path,source],evidence_scope='ROOT_REVIEWED_CONDITIONAL_OFFICIAL_EQUITY_ROLLFORWARD_NO_DIV_SPLIT_ONLY',limitations=approval['conditions']) for d in begins]
 review['rows'].extend(rows);review['source_hashes'].update(pins);return dict(rows=rows,source_hashes=pins)
