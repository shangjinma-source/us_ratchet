"""Read the existing AMD filing and seal corrected paragraph boundaries only."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_business_heading_excerpt_research as revised
from data import ndx_taxonomy_review as previous


def main():
    path = ROOT / 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0000002488/000000248822000016/amd-20211225.htm'
    expected = '5ab3b2564e1b5f18a1fc6b8b60a307abc3be32ee902a59955b3038c504dbfd36'
    manifest_path = path.with_name(path.name + '.manifest.json')
    manifest_sha = '6a3dbea9c8638d8aad5374fbd21e107dae87bd01161a2c40f980a4b2baae8189'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_sha:
        raise ValueError('Existing AMD evidence changed')
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest['content_sha256'] != expected or manifest['content_bytes'] != len(raw)
            or manifest['cik'] != '0000002488' or manifest['form'] != '10-K'
            or manifest['accession_number'] != '0000002488-22-000016'):
        raise ValueError('Existing filing descriptor conflicts with raw')
    old = previous.extract_business_section(raw, '10-K')
    new = revised.extract_business_heading_excerpt(raw)
    markers = ['We are a global semiconductor company primarily offering',
               'Computing and Graphics Markets', 'The Enterprise, Embedded and Semi-Custom Markets']
    if any(marker not in new['section_text'] or marker in old['section_text'] for marker in markers):
        raise ValueError('Expected real prose-cross-reference truncation counterexample absent')
    sources = {str(source): hashlib.sha256(source.read_bytes()).hexdigest() for source in (
        path, manifest_path, Path(__file__).resolve(), Path(previous.__file__).resolve(), Path(revised.__file__).resolve())}
    result = dict(schema='ndx_amd_business_excerpt_research_v1', source_hashes=sources,
        original_extraction=old, revised_extraction=new, original_source_metadata=manifest,
        original_section_character_count=len(old['section_text']),
        revised_section_character_count=len(new['section_text']),
        documented_failure='PROSE_SEE_PART_I_ITEM1A_CROSS_REFERENCE_TRUNCATED_BEFORE_ACTUAL_BUSINESS_OVERVIEW',
        intended_use='MANUAL_REVIEW_OF_EXISTING_DATED_BUSINESS_EVIDENCE_FOR_NEW_SCOPE_RISK_MAPPING',
        old_parser_modified=False, old_review_registry_modified=False,
        new_network_capture_performed=False, return_or_price_data_read=False,
        risk_chain_assigned=False, filing_publication_time_independently_reverified=False,
        full_ndx_membership_verified=False, point_in_time_verified=False, promotion_allowed=False)
    output = ROOT / 'data/cache/research/local_business_excerpt_research_20260912_v1/AMD_excerpt_review.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    for source, digest in sources.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during excerpt review')
    with output.open('x', encoding='utf8') as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        original_characters=len(old['section_text']), revised_characters=len(new['section_text']))))


if __name__ == '__main__':
    main()
