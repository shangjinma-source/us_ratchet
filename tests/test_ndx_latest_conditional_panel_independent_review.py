import unittest
from test_ndx_latest_conditional_panel_research import fixture
from backtest import ndx_latest_conditional_panel_research as panel


class IndependentPanelTests(unittest.TestCase):
    def test_unselected_observed_issuer_must_still_be_canonical_cik(self):
        args=fixture();args['observed_rows'][-1]['issuer_id']='issuer:not-a-cik'
        with self.assertRaises(ValueError):panel.assemble_conditional_panel(**args)

    def test_selected_mapping_rejects_mutated_universe_and_numeric_frames(self):
        for field in ('risk_chain','issuer_id','returns'):
            value=panel.assemble_conditional_panel(**fixture())
            sid=value['universe'].iloc[0]['security_id']
            if field=='returns':value['returns'].iloc[0,0]=0.123
            else:value['universe'].loc[0,field]='fabricated'
            with self.subTest(field=field),self.assertRaises(ValueError):panel.selected_mapping(value,[sid])

    def test_extra_nested_authentication_flags_rejected(self):
        for collection in ('coordinate_assumptions','risk_assumptions','channel_audits'):
            args=fixture()
            args[collection]['T0']['point_in_time_verified']=True
            with self.subTest(collection=collection),self.assertRaises(ValueError):panel.assemble_conditional_panel(**args)

    def test_boolean_share_ratio_is_not_one_share(self):
        args=fixture();value=args['channels']['T0']
        value['price_returns'][0]['declared_share_ratio']=True
        args['channel_audits']['T0']['channel_sha256']=panel.canonical_sha(value)
        with self.assertRaises(ValueError):panel.assemble_conditional_panel(**args)

    def test_finite_decimal_cannot_overflow_float64_panel(self):
        args=fixture();value=args['channels']['T0']
        for row in value['price_rows']:row['nominal_close']='1e400'
        for row in value['liquidity']['rows']:row['dollar_volume']='1e406'
        value['liquidity']['median_dollar_volume_usd']='1e406'
        args['channel_audits']['T0']['channel_sha256']=panel.canonical_sha(value)
        with self.assertRaises(ValueError):panel.assemble_conditional_panel(**args)


if __name__=='__main__':unittest.main()
