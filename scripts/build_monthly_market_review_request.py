"""Construct market-only publication evidence, without reading an account.

Known-source screening is bounded, not exhaustive action certification. Actual
holdings and pending orders must be reviewed separately before runtime adoption.
This function performs no writes, fetching, selection or account initialization.
"""
import json
from hashlib import sha256
from pathlib import Path

from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources as IdentityReader
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_known_source_review import review
from scripts.prepare_monthly_captured_training import build


class _MarketIdentityReader:
    """Reuse the identity-only validator without constructing an account provider."""
    _path = staticmethod(IdentityReader._path)
    _identity = IdentityReader._identity

    def __init__(self, manifest_path):
        self.identity_manifest_path = self._path(manifest_path)


def _safe_location(root, name):
    IdentityReader._path(name)
    path = root
    for part in Path(name).parts:
        path = path / part
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                'MARKET_REVIEW_LINK_FORBIDDEN')
    require(path.resolve().is_relative_to(root), 'MARKET_REVIEW_PATH_ESCAPE')


def construct(*, preparation_arguments, settings, inputs, output_prefix):
    require(type(inputs) is dict and set(inputs) == {
        'schema', 'source_hashes', 'feed_path', 'feed_receipt_path',
        'policy_path', 'identity_manifest_path'}, 'MARKET_REVIEW_INPUT_FIELDS')
    require(inputs['schema'] == 'MONTHLY_MARKET_REVIEW_INPUTS_V1', 'MARKET_REVIEW_SCHEMA')
    now = stamp(preparation_arguments['clock']())
    preparation = dict(preparation_arguments, clock=lambda: now)
    original_root = Path(preparation['root']).absolute()
    require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                    for p in [original_root, *original_root.parents]), 'MARKET_REVIEW_LINK_FORBIDDEN')
    root = original_root.resolve()
    _safe_location(root, output_prefix)
    reader = MonthlyFileConfiguration(root=root, path='unused.json', sha256_value='0'*64, clock=lambda: now)
    pins = dict(inputs['source_hashes'])
    require(type(inputs['source_hashes']) is dict and 0 < len(pins) <= 2000, 'SOURCE_PIN_LIMIT')
    fixed = settings['fixed_source_hashes']
    require(type(fixed) is dict, 'MARKET_REVIEW_FIXED_PINS_REQUIRED')
    for path, digest in fixed.items():
        require(path not in pins or pins[path] == digest, 'MARKET_REVIEW_PIN_CONFLICT')
        pins[path] = digest
    for path in pins:
        _safe_location(root, path)
    files = reader._package(pins)['files']
    for key in ('feed_path', 'feed_receipt_path', 'policy_path', 'identity_manifest_path'):
        require(inputs[key] in files, 'MARKET_REVIEW_SOURCE_MISSING')
    require(settings['calendar_path'] in fixed and settings['schedule_path'] in fixed,
            'MARKET_REVIEW_FIXED_CALENDAR_REQUIRED')
    manifest, compiled, _ = build(**preparation)
    # Reject linked training dependencies too; all bytes are rechecked at return.
    for path, digest in manifest['source_hashes'].items():
        _safe_location(root, path)
        require(path not in pins or pins[path] == digest, 'MARKET_REVIEW_PIN_CONFLICT')
        pins[path] = digest
    domain = compiled['input']['search_arguments']['metadata']
    identity_reader = _MarketIdentityReader(inputs['identity_manifest_path'])
    decision = dict(decision_date=manifest['decision_date'], binding=dict(search_arguments=dict(metadata=domain)))
    identities = {sid: identity_reader._identity(decision, files, pins, sid, manifest['decision_date'])
                  for sid in domain}
    calendar = json.loads(files[settings['calendar_path']])
    require(calendar['decision_date'] == manifest['decision_date'] and
            stamp(calendar['decision_close_at']) <= now, 'MARKET_REVIEW_CLOSE_TIME_INVALID')
    result = review(preparation_arguments=preparation, feed_raw=files[inputs['feed_path']],
                    feed_receipt_raw=files[inputs['feed_receipt_path']], policy_raw=files[inputs['policy_path']],
                    evidence_prefix=output_prefix+'/screen')
    artifacts = dict(result['evidence_files'])
    review_path, identity_path = output_prefix+'/review.json', output_prefix+'/identities.json'
    artifacts[review_path] = canonical(result['review'])
    artifacts[identity_path] = canonical(dict(securities=identities, source_references=sorted(pins)))
    combined = dict(pins)
    for path, raw in artifacts.items():
        _safe_location(root, path)
        require(path not in combined and not (root/path).exists(), 'MARKET_REVIEW_OUTPUT_SOURCE_COLLISION')
        combined[path] = sha256(raw).hexdigest()
    reader._package(pins)  # Source mutation during construction is not accepted.
    request = dict(preparation_arguments={k: v for k, v in preparation.items()
                                         if k not in ('root', 'clock', 'plan_validator')},
                   supplemental_hashes=combined, calendar_path=settings['calendar_path'],
                   schedule_path=settings['schedule_path'], identities_path=identity_path,
                   held_bar_sources={}, review_path=review_path, output_directory=settings['publish_output'])
    unresolved = result['review']['unresolved']
    return dict(status='WAITING_REVIEW' if unresolved else 'READY_REQUEST',
                reason='KNOWN_SOURCE_UNRESOLVED' if unresolved else None,
                request=None if unresolved else request, artifacts=artifacts,
                unresolved=unresolved, account_writes=False)
