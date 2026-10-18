"""Capture the public issuer listing; currency evidence only, not historical PIT."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root/'data/cache/research/fund_012922_currency_source_20261002_v1'
    if destination.exists():
        raise ValueError('Capture namespace exists; no overwrite/retry')
    url = 'https://e.efunds.com.cn/cart/subscriptions?form=&fundCode=012922'
    request = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        status, final_url = response.status, response.url
    text = raw.decode('utf-8')
    if status != 200 or '012922' not in text or '人民币份额' not in text or '全球成长精选' not in text:
        raise ValueError('Issuer listing not identified; do not infer currency')
    destination.mkdir(parents=True, exist_ok=False)
    with (destination/'issuer_listing.html').open('xb') as stream:
        stream.write(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {'schema':'FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1',
        'fund_code':'012922','currency_evidence':'ISSUER_LISTING_CNY_SHARE_CLASS',
        'currency':'CNY','source_url':url,'final_url':final_url,'http_status':status,
        'captured_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_reference':{'path':str(destination/'issuer_listing.html'),'sha256':digest},
        'historical_2023_class_continuity_verified':False,'point_in_time_verified':False,
        'fx_rates_supplied':False,'subscription_terms_verified':False,
        'nav_dataset_currency_binding_certified':False,'promotion_allowed':False,
        'orders_executed':False,'scope':'CURRENT_PUBLIC_ISSUER_LISTING_NOT_HISTORICAL_NAV_OR_EXECUTION_CERTIFICATION'}
    payload = (json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    with (destination/'manifest.json').open('xb') as stream:
        stream.write(payload)
    if (destination/'issuer_listing.html').read_bytes()!=raw or (destination/'manifest.json').read_bytes()!=payload:
        raise ValueError('Capture readback changed')
    print(json.dumps({'source_sha256':digest,'manifest_sha256':hashlib.sha256(payload).hexdigest(),'path':str(destination)},indent=2))


if __name__ == '__main__':
    main()
