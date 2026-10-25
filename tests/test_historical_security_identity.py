from backtest.historical_security_identity import resolve_identity, validate_claim, validate_records


def records():
    def row(ticker,issuer,sid,start,end):
        return dict(ticker=ticker,issuer_id=issuer,security_id=sid,start=start,end=end,source_references=['fixture'])
    return [row('HANS','beverage','beverage_common','2007-01-01','2012-01-08'),
            row('MNST','beverage','beverage_common','2012-01-09','2020-01-01'),
            row('MNST','worldwide','worldwide_common','2007-01-01','2008-11-09'),
            row('LMCK','liberty','liberty_c','2014-07-24','2016-01-01')]


def test_reused_ticker_remains_distinct_issuer():
    assert resolve_identity(records(),'MNST','2008-01-01')['issuer_id']=='worldwide'
    assert resolve_identity(records(),'HANS','2008-01-01')['issuer_id']=='beverage'
    try:validate_claim(records(),ticker='MNST',asof='2008-01-01',issuer_id='beverage',security_id='beverage_common')
    except ValueError as error:assert str(error)=='DATED_IDENTITY_CLAIM_MISMATCH'
    else:raise AssertionError('Cross-issuer alias admitted')


def test_future_security_cannot_be_backfilled():
    try:resolve_identity(records(),'LMCK','2008-01-01')
    except ValueError as error:assert str(error).startswith('NO_UNIQUE_DATED_IDENTITY')
    else:raise AssertionError('Future issue admitted')


def test_overlap_and_issuer_change_rejected():
    for extra in (dict(records()[2]),dict(records()[0],ticker='OTHER',issuer_id='wrong')):
        try:validate_records(records()+[extra])
        except ValueError:pass
        else:raise AssertionError('Invalid mapping admitted')


def test_symbol_change_trading_date_boundary():
    assert resolve_identity(records(),'HANS','2012-01-06')['issuer_id']=='beverage'
    assert resolve_identity(records(),'MNST','2012-01-09')['issuer_id']=='beverage'
    try:resolve_identity(records(),'MNST','2012-01-06')
    except ValueError:pass
    else:raise AssertionError('Name approval used as trading date')


def test_compact_dates_and_untyped_fields_rejected():
    for patch in [dict(start='20070101'),dict(end='20120108'),dict(ticker=123),dict(issuer_id=' '),
                  dict(source_references='source'),dict(source_references=[True]),dict(source_references=[' '])]:
        altered=records();altered[0].update(patch)
        try:validate_records(altered)
        except ValueError:pass
        else:raise AssertionError('Invalid field accepted')
    try:resolve_identity(records(),'HANS','20080101')
    except ValueError:pass
    else:raise AssertionError('Compact query date accepted')
