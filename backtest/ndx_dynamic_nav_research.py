"""Version-bound retrospective native-currency NAV, no publication-time claim."""
import hashlib
import io
import json

import pandas as pd
import numpy as np


def load_nav(*, csv_path, manifest_path, expected_csv_sha256,
             expected_manifest_sha256, calendar):
    raw = csv_path.read_bytes()
    sidecar = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_csv_sha256:
        raise ValueError('NAV CSV identity differs')
    if hashlib.sha256(sidecar).hexdigest() != expected_manifest_sha256:
        raise ValueError('NAV manifest identity differs')
    manifest = json.loads(sidecar)
    frame = pd.read_csv(io.BytesIO(raw))
    if (manifest['content_sha256'] != expected_csv_sha256
            or manifest['content_bytes'] != len(raw)
            or manifest['row_count'] != len(frame)
            or manifest['fund_code'] != '012922'):
        raise ValueError('NAV manifest binding differs')
    dates = pd.to_datetime(frame['Date'], errors='raise')
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError('NAV dates must be unique and sorted')
    if (not isinstance(calendar, pd.DatetimeIndex) or len(calendar) < 2
            or not calendar.is_unique or not calendar.is_monotonic_increasing):
        raise ValueError('Explicit ordered calendar required')
    values = pd.to_numeric(frame['Close'], errors='raise')
    if pd.api.types.is_bool_dtype(values) or not np.isfinite(values).all() or not values.gt(0).all():
        raise ValueError('Invalid NAV')
    observed = pd.DataFrame({'nav_date': dates, 'nav': values})
    aligned = pd.merge_asof(pd.DataFrame({'session': calendar}), observed,
                            left_on='session', right_on='nav_date', direction='backward')
    if aligned['nav'].isna().any():
        raise ValueError('No prior NAV for a requested session')
    index = aligned['nav'] / aligned['nav'].iloc[0]
    peak = index.cummax()
    return dict(role='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV',
        rows=[dict(session=str(row.session.date()), nav_date=str(row.nav_date.date()),
                   nav=float(row.nav), equity_index=float(index.iloc[position]))
              for position, row in enumerate(aligned.itertuples(index=False))],
        path_return=float(index.iloc[-1] - 1),
        path_max_drawdown=float((1-index/peak).max()),
        annualized_return_252_session=float(index.iloc[-1] ** (252/(len(index)-1))-1),
        source_hashes={str(csv_path): expected_csv_sha256,
                       str(manifest_path): expected_manifest_sha256},
        alignment='BACKWARD_NAV_DATE_NOT_PUBLICATION_TIME',
        publication_time_verified=False, historical_revision_free_verified=False,
        fx_modelled=False, subscription_redemption_fees_modelled=False,
        promotion_allowed=False)
