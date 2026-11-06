import unittest
from data.roa_account_composition import verified_roa_identities

class VerifiedRosterIdentityReuseTests(unittest.TestCase):
    def test_six_verified_holdings_do_not_reenter_monthly_resolver(self):
        roster=[dict(security_id=f's:{i}',ticker=f'T{i}') for i in range(6)]
        def unavailable(ticker):raise AssertionError('legacy resolver must not run')
        result=verified_roa_identities(securities=roster,holdings=[dict(r,quantity=2) for r in roster],resolver=unavailable)
        self.assertEqual(set(result),{r['security_id'] for r in roster})
    def test_outside_roster_still_requires_server_resolver(self):
        calls=[]
        def resolver(ticker):calls.append(ticker);return dict(ticker=ticker,security_id='s:old')
        result=verified_roa_identities(securities=[dict(security_id='s:new',ticker='NEW')],holdings=[dict(security_id='s:old',ticker='OLD',quantity=1)],resolver=resolver)
        self.assertEqual(calls,['OLD']);self.assertEqual(result['s:old']['ticker'],'OLD')
    def test_roster_ticker_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError,'ROA_HELD_IDENTITY_CHANGED'):
            verified_roa_identities(securities=[dict(security_id='s:1',ticker='A')],holdings=[dict(security_id='s:1',ticker='B')],resolver=lambda _:None)
    def test_outside_resolver_sid_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError,'ROA_HELD_IDENTITY_CHANGED'):
            verified_roa_identities(securities=[],holdings=[dict(security_id='s:1',ticker='A')],resolver=lambda _:dict(security_id='s:2',ticker='A'))
    def test_duplicate_roster_sid_rejected(self):
        with self.assertRaisesRegex(ValueError,'ROA_ROSTER_IDENTITY_CONFLICT'):
            verified_roa_identities(securities=[dict(security_id='s:1',ticker='A'),dict(security_id='s:1',ticker='B')],holdings=[],resolver=lambda _:None)

if __name__=='__main__':unittest.main()
