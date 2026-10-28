"""Server-owned freshness seal for a reference projection; no trade permission.

The caller reads authoritative versions again immediately before publication.
Neither a browser-supplied seal nor cached versions satisfy that requirement.
This pure guard cannot make separate account/configuration reads atomic.
"""
from copy import deepcopy

from core.news_investment_review_v1 import moment
from core.reentry_buy_scope_v1 import digest, require, valid_hash


def seal_projection(*, projection, configuration_sha256):
    require(valid_hash(configuration_sha256), 'PUBLICATION_CONFIG_HASH')
    require(projection.get('schema') == 'REFERENCE_PREVIEW_PROJECTION_V1',
            'PUBLICATION_PROJECTION_SCHEMA')
    require(projection.get('executable') is False, 'PUBLICATION_NOT_EXECUTION')
    binding = projection['binding']
    require(digest(binding) == projection['binding_sha256'], 'PUBLICATION_BINDING_HASH')
    require(moment(projection['generated_at']) < moment(projection['valid_until']),
            'PUBLICATION_INVALID_INTERVAL')
    return dict(schema='REFERENCE_PUBLICATION_SEAL_V1',
                projection_sha256=digest(projection),
                original_binding=deepcopy(binding['original_binding']),
                reference_version=binding['reference_version'],
                reference_state_sha256=binding['reference_state_sha256'],
                configuration_sha256=configuration_sha256,
                generated_at=projection['generated_at'],
                valid_until=projection['valid_until'])


def check_publication(*, projection, seal, current_binding,
                      current_reference_state, current_configuration_sha256, now):
    """Reject late results, including AI results with unchanged three request IDs.

    This checks consistency only. Source authentication, server-owned activation
    authority and existing execution gates are prerequisites, not outputs.
    """
    require(seal.get('schema') == 'REFERENCE_PUBLICATION_SEAL_V1',
            'PUBLICATION_SEAL_SCHEMA')
    expected = seal_projection(projection=projection,
                               configuration_sha256=seal['configuration_sha256'])
    require(seal == expected, 'PUBLICATION_SEALED_RESULT_CHANGED')
    require(current_binding == seal['original_binding'], 'PUBLICATION_ACCOUNT_TARGET_CHANGED')
    require(current_reference_state.get('account_id') == current_binding['account_id'],
            'PUBLICATION_REFERENCE_ACCOUNT_CHANGED')
    require(current_reference_state.get('version') == seal['reference_version'] and
            digest(current_reference_state) == seal['reference_state_sha256'],
            'PUBLICATION_REFERENCE_CHANGED')
    require(current_configuration_sha256 == seal['configuration_sha256'],
            'PUBLICATION_CONFIGURATION_CHANGED')
    require(moment(seal['generated_at']) <= moment(now) < moment(seal['valid_until']),
            'PUBLICATION_EXPIRED_OR_FUTURE')
    return dict(status='REFERENCE_PUBLICATION_CONSISTENCY_CHECKED',
                checked_at=now, valid_until=seal['valid_until'],
                projection_sha256=seal['projection_sha256'],
                reference_version=seal['reference_version'], executable=False,
                account_mutated=False, source_authentication_performed=False)
