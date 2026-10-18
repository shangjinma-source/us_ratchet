import unittest
from scripts import ndx_explicit_path_independent_audit_20260919 as m
from test_ndx_explicit_path_independent_audit_20260919 import fixture


class Tests(unittest.TestCase):
    def test_no_overlap_preserves_all_prior_but_disables_anchor(self):
        args=fixture();prior={'OLD'+sid:w for sid,w in args['previous'].items()};args['previous']=prior
        fit=args['fitted'];fit['previous_target_weights']=dict(prior);fit['surviving_anchor_mass']=0.
        fit['anchor_by_security']={sid:0. for sid in args['selected']};fit['effective_anchor_strength']=0.
        result=m.inspect_period(**args)
        self.assertEqual(result['surviving_anchor_mass'],'0');self.assertEqual(result['effective_anchor_strength'],'0')
        self.assertEqual(result['exiting_sids'],sorted(prior))
        self.assertEqual(result['newly_entering_sids'],sorted(args['selected']))
        fit['previous_target_weights']={}
        with self.assertRaises(ValueError):m.inspect_period(**args)

    def test_nonanchored_spec_keeps_prior_metadata_but_strength_zero(self):
        args=fixture();args['weight_spec']='constrained_fixed_shrinkage';args['fitted']['weight_spec']=args['weight_spec']
        args['fitted']['effective_anchor_strength']=0.
        result=m.inspect_period(**args);self.assertEqual(result['effective_anchor_strength'],'0')
        args['fitted']['anchor_by_security']={s:0. for s in args['selected']}
        with self.assertRaises(ValueError):m.inspect_period(**args)

    def test_new_same_sid_ticker_is_checked_against_matrix_not_old_ticker(self):
        args=fixture();args['selected']['B']['ticker']='RENAMED';args['fitted']['targets']['B']['ticker']='RENAMED'
        args['returns'].rename(columns={'B':'RENAMED'},inplace=True)
        names=[args['selected'][sid]['ticker'] for sid in sorted(args['selected'])]
        matrix=dict(dates=[x.date().isoformat() for x in args['returns'].index],tickers=names,returns=args['returns'][names].to_numpy().tolist())
        args['fitted']['fit_data_sha256']=m.digest(matrix)
        self.assertEqual(m.inspect_period(**args)['fit_rows'],126)
        args['fitted']['targets']['B']['ticker']='B'
        with self.assertRaises(ValueError):m.inspect_period(**args)


if __name__=='__main__':unittest.main()
