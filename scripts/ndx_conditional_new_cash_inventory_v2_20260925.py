"""V2: project saved provider currency metadata; never regenerate V1 or quotes."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
OUTPUT = BASE / 'conditional_new_cash_inventory_20260925_v2'
V1 = BASE / 'conditional_new_cash_inventory_20260925_v1'
INVENTORY_SHA = 'b5ad918e9aef6115eba190dd46ded7433a700a29aaf2537489fb3c4e093efe63'
PUBLICATION_SHA = '5c114a17406ba2103dafa80834688ece1c04917002daf1030c437bb3e62c55f5'
SCHEMA = 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2'
GAP = 'LANE_MATRIX_CURRENCY_NOT_IN_BOUND_SAVED_FIELDS'
PARENTS = {'BAD_TAIL_projection': ('bad_tail_five_input_projection_20260923_v1/projection.json',
                         '77d03b11751322158158b66a18ecf19fd669cacfa730b99c3dbda1139b25e6be'),
 'DRAWDOWN_assembly': ('drawdown_four_input_assembly_20260923_v1/assembly.json',
                       'cb2ab027a2506a43d97e7c65494d524b1c7d7e890e7b9a2f67f863768c61aa67'),
 'LEGACY_TARGET_DISTANCE_price': ('legacy_twelve_price_only_20260923_v1/prices.json',
                                  'a50c4fd387f10262527e82ad0edd2bae7b799b67e2d08cff2e4a47030a64b342'),
 'RETURN_price': ('return_eight_price_only_20260923_v1/raw_assembly.json',
                  'e1f00af594bfcb9a9c75b02493cf62fc64622e0b280ba2774346832b530b7336')}
CHANNELS = {'ADBE': {'decoded_sha256': '8aa7fa1f6c0fe2ebee9e088f80c1097b362ad623cbed236431088214b7ac19fe',
          'raw': ('current79_new_asof_capture_20260919_v1/ADBE.response.bin',
                  '166f2652a249d6ccb03d5d69c91ab7adbe130798004ac2d643eb3f403d973feb'),
          'receipt': ('current79_new_asof_capture_20260919_v1/ADBE.receipt.json',
                      '5e33c009d5cd35c9dfc1f03283525a5bc9ea31536510224d5c88fd0b9a82a66f')},
 'ADI': {'decoded_sha256': '2e7107771fa3a151a94c5e73f37ee052f30a45962b5b9f4bec16bfff74233cbf',
         'raw': ('current79_new_asof_capture_20260919_v1/ADI.response.bin',
                 '59fb8913d083da7c38f2307d00b49e014b573bd7a6c0ad5785f1a77d712799fb'),
         'receipt': ('current79_new_asof_capture_20260919_v1/ADI.receipt.json',
                     'c3c72f8e05f5ca06b271d95689117b91f669bee502390cb6d0e72f991386a4e4')},
 'AMAT': {'decoded_sha256': '24c9ac051ba99b6717bb1a3344a2932cdfe8a85acdba82d9cd8cb2082429f4c5',
          'raw': ('current79_new_asof_capture_20260919_v1/AMAT.response.bin',
                  '0d695454cc738af21f6854f4bbe8f6a1d5e7ddd42433b06733eb211c6230c069'),
          'receipt': ('current79_new_asof_capture_20260919_v1/AMAT.receipt.json',
                      '893830f0dd6a10fae69dc7f8a2c2181ab4ac1cf997af2bee3643be8e309877ae')},
 'AVGO': {'decoded_sha256': 'c9340173a0460a87940faf823d5147db43b8616ebebabf68dd49361c65970e6b',
          'raw': ('current79_new_asof_capture_20260919_v1/AVGO.response.bin',
                  '5dfbef2f2188a8598e6dd29a94f9c483cb9da68ee01c359d58a05e4fedb5b972'),
          'receipt': ('current79_new_asof_capture_20260919_v1/AVGO.receipt.json',
                      '7bf47f466297570051004c0ea325a986d5535fa48a741634843df6cea7f0fc7e')},
 'BKR': {'decoded_sha256': 'e372d6ff5f05b60e3767ae8ae91b69ae805407a1785a3c15153792bac123011c',
         'raw': ('current79_new_asof_capture_20260919_v1/BKR.response.bin',
                 '67539f45c2c6f5f83d0d9d9c7a67f4bf7dd13aed77a2bc706d2854a6fdc6488e'),
         'receipt': ('current79_new_asof_capture_20260919_v1/BKR.receipt.json',
                     '9f532a89f72ce3b2d381ac954a4d8453ad7b1b60a69220eb850e83adde2185ed')},
 'CDNS': {'decoded_sha256': 'a7487ad01154ce3466ffac4772e43aa69c16b7f3ccc084c7ef1af7842f40246d',
          'raw': ('current79_new_asof_capture_20260919_v1/CDNS.response.bin',
                  'ae140a55233d24cd6afd7eccb9676678d2b2b854826ac459c0c515b9da3d9a48'),
          'receipt': ('current79_new_asof_capture_20260919_v1/CDNS.receipt.json',
                      '4b2b8edd98e1e59ba654e80ae0305c434915cb029e8bf9f72c0c763f9faa9911')},
 'DDOG': {'decoded_sha256': '2f052dcebb6dfc61417a3802bcfdd9c73fef80712d8053fc115af133f1a19ed1',
          'raw': ('current79_new_asof_capture_20260919_v1/DDOG.response.bin',
                  '97b3eba54dc94b45bcad8be212b3901541eed8d0029ff1b91919519722741217'),
          'receipt': ('current79_new_asof_capture_20260919_v1/DDOG.receipt.json',
                      '512685ba20962f7ff19c12ea4e660ec0f38947070783ced9cd71240b0adee159')},
 'ENPH': {'decoded_sha256': '9674ec83b89380b9f22fccb864d5e61bb3b9f270ee93b69a0b75f2250054c45f',
          'raw': ('legacy_pool_remaining_split_probe_20260912_v1/ENPH.response.bin',
                  '9674ec83b89380b9f22fccb864d5e61bb3b9f270ee93b69a0b75f2250054c45f'),
          'receipt': ('legacy_pool_remaining_split_probe_20260912_v1/ENPH.metadata.json',
                      'e0b7eb2e6e26b63f51f7ccc675217b87b41dd5e60d25313aa37322eb8adff0ce')},
 'FTNT': {'decoded_sha256': '3adbe011a23a31b32fcdb646b44e4ecffbeebf2cdc77264c91c917987e585807',
          'raw': ('current79_new_asof_capture_20260919_v1/FTNT.response.bin',
                  '44bfa3672a034373a4950e5a6bcacaef54af9eb1b7d075be036e690669906451'),
          'receipt': ('current79_new_asof_capture_20260919_v1/FTNT.receipt.json',
                      'cf2fe256b767f7fa3aad04e49b17e1e47901f9f0f7738e033d55964117794446')},
 'GOOG': {'decoded_sha256': '46db7edce1841246c636c51d3d226272037ab3c58d6b1bc417d4c1286c8e285b',
          'raw': ('current79_new_asof_capture_20260919_v1/GOOG.response.bin',
                  '7f07ef0dd9833d82edf93776756e56158b19a8dece2aa4c1a064ceba09dcde98'),
          'receipt': ('current79_new_asof_capture_20260919_v1/GOOG.receipt.json',
                      '1f05bfcc8f9984615390e35c3052d94b693e1dcbd50b6d7e30bcabc03ea4ee58')},
 'GOOGL': {'decoded_sha256': '45cd0fae754ffca877a190d56062bcd7f1394f0e4b66371a3b99ae47ffe9f657',
           'raw': ('current79_new_asof_capture_20260919_v1/GOOGL.response.bin',
                   '0501f725e58257c56add1d27bfd26df8b084872bd1619d51455278246cd8a4df'),
           'receipt': ('current79_new_asof_capture_20260919_v1/GOOGL.receipt.json',
                       '58998d14a3829db34a5a5ae1e0e49727c48b2ab821cfa5ca82d58b1e61d5796c')},
 'QCOM': {'decoded_sha256': '7dd4ee5bbe924fcc57f5052c8643dea870db608b7d59771c6f27136937e6c0a7',
          'raw': ('current79_new_asof_capture_20260919_v1/QCOM.response.bin',
                  '8a9eab309be68d1185fca2bc3ba1e48ff36d8ec617eca471df369bcea46a1fb7'),
          'receipt': ('current79_new_asof_capture_20260919_v1/QCOM.receipt.json',
                      'b81b39ee8e10dcedd28a18ff143e6018a948f7404e68b4445be0d9b6eb3fea08')},
 'TEAM': {'decoded_sha256': '0f935128e485c06d2da223949d00409a0aa6505bd75bb97f35afc5455f2f77d7',
          'raw': ('legacy_pool_remaining_split_probe_20260912_v1/TEAM.response.bin',
                  '0f935128e485c06d2da223949d00409a0aa6505bd75bb97f35afc5455f2f77d7'),
          'receipt': ('legacy_pool_remaining_split_probe_20260912_v1/TEAM.metadata.json',
                      '585d98d57dea33d6ad70e5e52add59ab6e43971e98bedb388ee7bd956c240edb')},
 'TXN': {'decoded_sha256': '9ddbd15ebf235420b6f10b9111392797afa55c3ec14a3c3e57cd1c9193caf0ad',
         'raw': ('current79_new_asof_capture_20260919_v1/TXN.response.bin',
                 '4974473a2aac45e4b610fc8e4dc1710606bde9d98fad222513e933a16fdf8e90'),
         'receipt': ('current79_new_asof_capture_20260919_v1/TXN.receipt.json',
                     '66c1612e5be97aa970ef6b5b5d560ac0067d04f5b45cc7f8f8f6155aa41d5ee9')}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


LOADED = {str(SOURCE): sha(SOURCE.read_bytes())}


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def exact(a, b):
    return encode(a) == encode(b)


def strict(sources):
    for path, digest in sources.items():
        require(sha(Path(path).read_bytes()) == digest, 'Source bytes changed: ' + path)


def normalized(path):
    return str(Path(path).resolve())


def ref(path, digest):
    return {'path': str(path), 'sha256': digest}


def read(reference, sources):
    path, digest = reference['path'], reference['sha256']
    require(path not in sources or sources[path] == digest, 'Conflicting source hash')
    raw = Path(path).read_bytes()
    require(sha(raw) == digest, 'Hard-bound bytes mismatch')
    sources[path] = digest
    return raw


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=no_duplicates)


def inspect_metadata(ticker, channel, raw, receipt, raw_ref, receipt_ref, decoded_sha):
    """Decode container for metadata; never inspect quote arrays or recompute prices."""
    require(sha(raw) == raw_ref['sha256'], 'Transport hash mismatch')
    require(type(receipt.get('http_status')) is int and receipt['http_status'] == 200, 'Receipt HTTP status')
    legacy = 'response_sha256' in receipt
    receipt_path = receipt['response_path' if legacy else 'raw_path']
    receipt_sha = receipt['response_sha256' if legacy else 'raw_sha256']
    url = receipt['request']['url'] if legacy else receipt['request_url']
    require(receipt_sha == raw_ref['sha256'] and normalized(receipt_path) == normalized(raw_ref['path']), 'Receipt raw binding mismatch')
    require(receipt['final_url'] == url == channel['request']['url'], 'Request/final URL mismatch')
    require(unquote(urlsplit(url).path).split('/')[-1] == ticker, 'URL ticker mismatch')
    require(receipt['received_at_utc'] == channel['received_at_utc'], 'Received time mismatch')
    if 'ticker' in receipt:
        require(receipt['ticker'] == ticker, 'Receipt ticker mismatch')
    saved_raw = channel.get('raw_reference', {'path': channel.get('raw_path'), 'sha256': channel.get('raw_sha256')})
    require(normalized(saved_raw['path']) == normalized(raw_ref['path']) and saved_raw['sha256'] == raw_ref['sha256'], 'Channel raw binding mismatch')
    require(channel['decoded_sha256'] == decoded_sha and channel['ticker'] == ticker, 'Channel decoded/ticker mismatch')
    if 'metadata_reference' in channel:
        require(normalized(channel['metadata_reference']['path']) == normalized(receipt_ref['path']) and channel['metadata_reference']['sha256'] == receipt_ref['sha256'], 'Channel receipt binding mismatch')
    require(len(raw) <= 4_000_000, 'Oversize raw')
    compressed = raw.startswith(b'\x1f\x8b')
    if compressed:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            decoded = stream.read(8_000_001)
    else:
        decoded = raw
    require(len(decoded) <= 8_000_000 and sha(decoded) == decoded_sha, 'Decoded hash/size mismatch')
    chart = loads(decoded)['chart']
    require(chart.get('error') is None and type(chart['result']) is list and len(chart['result']) == 1, 'Provider result/error mismatch')
    metadata = chart['result'][0]['meta']
    require(metadata['symbol'] == ticker and metadata['currency'] == 'USD', 'Provider symbol/currency conflict')
    if 'currency' in channel:
        require(channel['currency'] == 'USD', 'Saved channel currency conflict')
    return {'ticker': ticker, 'currency': 'USD', 'raw_reference': deepcopy(raw_ref),
            'receipt_reference': deepcopy(receipt_ref), 'decoded_sha256': decoded_sha,
            'transport_encoding': 'gzip' if compressed else 'identity', 'received_at_utc': receipt['received_at_utc'],
            'request_url': url, 'currency_json_pointer': '/chart/result/0/meta/currency',
            'symbol_json_pointer': '/chart/result/0/meta/symbol', 'provider_currency_metadata_observed': True,
            'historical_currency_interval_verified': False, 'provider_identity_verified': False,
            'point_in_time_verified': False}


def increment(parent, evidence, *, expected_removed=110, expected_identity=155):
    """Change only currency projection and the one named gap; preserve all else."""
    require(parent['schema'] == 'CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V1', 'Wrong parent schema')
    require(parent['branch_coordinate_count'] == 36 and len(parent['rows']) == 36, 'Wrong parent row denominator')
    require(parent['cash_fork_called'] is False and parent['point_in_time_verified'] is False and parent['promotion_allowed'] is False, 'Parent permission upgrade')
    rows = deepcopy(parent['rows'])
    removed, identity_count, changed = 0, 0, []
    for row_index, row in enumerate(rows):
        for sec_index, security in enumerate(row['securities']):
            old_gaps = security['gaps']
            identity_count += old_gaps.count('DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE')
            unknown = [item for item in security['execution_open_observations'] if item['currency'] is None]
            require((GAP in old_gaps) == bool(unknown) and old_gaps.count(GAP) <= 1, 'Currency gap/observation inconsistency')
            for price_index, item in enumerate(security['execution_open_observations']):
                if item['currency'] is not None:
                    continue
                old_reference = item['reference']
                key = (normalized(old_reference['path']), old_reference['sha256'], old_reference['json_pointer'].split('/')[-1])
                require(key in evidence, 'Unbound matrix currency source')
                proof = evidence[key]
                require(proof['currency'] == 'USD' and proof['provider_currency_metadata_observed'] is True
                        and proof['historical_currency_interval_verified'] is False, 'Currency evidence permissions mismatch')
                changed.append({'inventory_json_pointer': '/rows/' + str(row_index) + '/securities/' + str(sec_index) + '/execution_open_observations/' + str(price_index),
                                'original_observation': deepcopy(item), 'currency_evidence': deepcopy(proof)})
                item['currency'] = 'USD'
                item['currency_status'] = 'SAVED_PROVIDER_META_OBSERVED_NOT_HISTORICAL_INTERVAL_CERTIFICATION'
                item['currency_evidence'] = deepcopy(proof)
            if unknown:
                removed += 1
                security['gaps'] = [gap for gap in old_gaps if gap != GAP]
        expected_gaps = [{'security_id': security['security_id'], 'reason': gap} for security in row['securities'] for gap in security['gaps']]
        require(exact(expected_gaps, [gap for gap in row['gaps'] if gap['reason'] != GAP]), 'Parent row gap aggregation mismatch')
        row['gaps'] = expected_gaps
        # Keep V1 status/flags even when its sole missing-field gap is removed.
    require(removed == expected_removed and identity_count == expected_identity, 'Unexpected currency/identity gap denominator')
    result = deepcopy(parent)
    result['schema'] = SCHEMA
    result['rows'] = rows
    result['v1_source_hashes_preserved'] = result.pop('source_hashes')
    result['currency_increment'] = {'removed_missing_field_gap_count': removed, 'unchanged_identity_gap_count': identity_count,
                                   'row_status_semantics': 'UNCHANGED_V1_SNAPSHOT_NOT_RECOMPUTED',
                                   'current_gap_row_count': sum(bool(row['gaps']) for row in rows),
                                   'current_no_gap_row_count': sum(not row['gaps'] for row in rows),
                                   'changed_observations': changed, 'provider_currency_metadata_observed': True,
                                   'historical_currency_interval_verified': False, 'prices_recomputed': False,
                                   'identity_gap_resolved': False, 'source_authenticity_certified': False}
    return result


def build():
    strict(LOADED)
    require(set(item.name for item in V1.iterdir()) == {'inventory.json', 'publication.json'}, 'Parent publication incomplete/failed')
    sources = dict(LOADED)
    parent_ref, publication_ref = ref(V1 / 'inventory.json', INVENTORY_SHA), ref(V1 / 'publication.json', PUBLICATION_SHA)
    parent = loads(read(parent_ref, sources))
    publication = loads(read(publication_ref, sources))
    require(publication['inventory_reference']['sha256'] == INVENTORY_SHA
            and normalized(publication['inventory_reference']['path']) == normalized(parent_ref['path'])
            and publication['status'] == 'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY'
            and publication['fork_executed'] is False and exact(publication['source_hashes'], parent['source_hashes']), 'Parent publication receipt mismatch')
    evidence, channel_refs, cache = {}, [], {}
    for role, (path, digest) in PARENTS.items():
        parent_price_ref = ref(BASE / path, digest)
        require(exact(parent['input_references'][role], parent_price_ref), 'V1 parent price reference mismatch')
        document = loads(read(parent_price_ref, sources))
        nested = role in ('BAD_TAIL_projection', 'DRAWDOWN_assembly')
        channel_path = '/price_projection/channels/' if nested else '/channels/'
        channels = document['price_projection']['channels'] if nested else document['channels']
        require(len({channel['ticker'] for channel in channels}) == len(channels), 'Duplicate parent channel')
        for index, channel in enumerate(channels):
            ticker = channel['ticker']
            require(ticker in CHANNELS, 'Unbound channel')
            pins = CHANNELS[ticker]
            raw_ref, receipt_ref = (ref(BASE / pins[key][0], pins[key][1]) for key in ('raw', 'receipt'))
            if ticker not in cache:
                cache[ticker] = (read(raw_ref, sources), loads(read(receipt_ref, sources)))
            raw, receipt = cache[ticker]
            proof = inspect_metadata(ticker, channel, raw, receipt, raw_ref, receipt_ref, pins['decoded_sha256'])
            proof['channel_reference'] = dict(parent_price_ref, json_pointer=channel_path + str(index))
            evidence[(normalized(parent_price_ref['path']), digest, ticker)] = proof
            channel_refs.append(deepcopy(proof))
    require(len(channel_refs) == 29 and set(cache) == set(CHANNELS), 'Exact 29-channel/14-raw denominator required')
    result = increment(parent, evidence)
    result['currency_increment']['channel_evidence'] = channel_refs
    result['parent_inventory_reference'] = parent_ref
    result['parent_publication_reference'] = publication_ref
    result['source_hashes'] = sources
    strict(sources)
    return result


def durable(path, raw):
    with path.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def publish():
    require(not OUTPUT.exists(), 'Fixed V2 namespace exists; no retry/overwrite')
    result = build()
    strict(result['source_hashes'])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        raw = encode(result)
        path = OUTPUT / 'inventory.json'
        durable(path, raw)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and set(item.name for item in OUTPUT.iterdir()) == {'inventory.json'}, 'Output differs/orphan')
        reference = ref(path, sha(raw))
        receipt = encode({'schema': 'CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1',
                          'inventory_reference': reference, 'source_hashes': result['source_hashes'],
                          'status': 'SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY', 'fork_executed': False})
        durable(OUTPUT / 'publication.json', receipt)
        strict(result['source_hashes'])
        require(path.read_bytes() == raw and (OUTPUT / 'publication.json').read_bytes() == receipt
                and set(item.name for item in OUTPUT.iterdir()) == {'inventory.json', 'publication.json'}, 'Publication readback differs')
        return dict(reference, publication_sha256=sha(receipt))
    except Exception as error:
        durable(OUTPUT / 'failure.json', encode({'status': 'PUBLICATION_FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False}))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if not args.publish:
        parser.error('Explicit --publish required')
    print(json.dumps(publish(), indent=2))
