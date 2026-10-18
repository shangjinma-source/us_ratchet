from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timedelta
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_quantity_v2_simulation_status import snapshot,create_router
from scripts.bootstrap_current_quantity_v2_simulation import run
from test_bootstrap_current_quantity_v2_simulation import fixture,fetch,NOW


class AutomaticStatusTests(unittest.TestCase):
    def test_completed_unknown_is_not_success_and_late_marker_is_explicit(self):
        from test_current_quantity_v2_simulated_settlement import fixture as mixed_fixture,run as settle
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        with TemporaryDirectory() as folder:
            state,evidence,_=mixed_fixture();db=Path(folder)/'unknown.sqlite3';store=SimulationStore(db)
            for row in evidence.values():row['minutes']=[]
            first=store.create(state)
            current=store.apply(simulation_id=state['simulation_id'],expected_revision=first['revision'],operation_id='unknown',
                                request={'kind':'synthetic'},transform=lambda simulation:settle(simulation,evidence))
            arguments=dict(database_path=db,simulation_id=state['simulation_id'],clock=lambda:datetime.fromisoformat('2026-10-16T10:05:00-04:00'))
            result=snapshot(**arguments)
            self.assertEqual(result['status'],'AVAILABLE',result)
            self.assertEqual(result['pending_operations'],[])
            self.assertEqual(result['daily']['unresolved_order_results'],2)
            self.assertEqual(result['daily']['decision_status'],'NO_DECISION_RECORD')
            store.apply(simulation_id=state['simulation_id'],expected_revision=current['revision'],operation_id='late',
                        request={'kind':'ISOLATED_DAILY_LATE_V1','session':'2026-10-16','observed_at':'2026-10-16T10:05:00-04:00'},transform=lambda simulation:simulation)
            before=db.read_bytes();result=snapshot(**arguments)
            self.assertEqual(result['daily']['decision_status'],'LATE_NO_NEW_DECISION')
            self.assertEqual(result['daily']['unresolved_order_results'],2)
            self.assertEqual(db.read_bytes(),before)

    def test_both_sides_and_completed_simulated_fills(self):
        from test_current_quantity_v2_simulated_settlement import fixture as mixed_fixture,run as settle
        from backtest.current_quantity_v2_simulation_store import SimulationStore
        with TemporaryDirectory() as folder:
            state,evidence,_=mixed_fixture();db=Path(folder)/'mixed.sqlite3';store=SimulationStore(db)
            created=store.create(state);args=dict(database_path=db,simulation_id=state['simulation_id'])
            before=db.read_bytes();view=snapshot(**args)
            self.assertEqual(view['status'],'AVAILABLE',view)
            self.assertEqual({o['side'] for o in view['orders']},{'BUY','SELL'})
            self.assertEqual(before,db.read_bytes())
            store.apply(simulation_id=state['simulation_id'],expected_revision=created['revision'],operation_id='settle',
                        request={'kind':'synthetic'},transform=lambda simulation:settle(simulation,evidence))
            before=db.read_bytes();view=snapshot(**args)
            self.assertEqual(view['status'],'AVAILABLE',view)
            self.assertTrue(all(o['display_status']=='FILLED' for o in view['orders']))
            self.assertEqual(before,db.read_bytes())

    def test_absent_and_attempt_and_invalid_database_never_create_account(self):
        with TemporaryDirectory() as folder:
            db=Path(folder)/'simulation.sqlite3';args=dict(database_path=db,simulation_id='test')
            self.assertEqual(snapshot(**args)['status'],'WAITING_FOR_INITIALIZATION')
            self.assertFalse(db.exists())
            (db.parent/'scheduled-bootstrap-attempt.json').write_text('{}')
            self.assertEqual(snapshot(**args)['status'],'INITIALIZATION_REQUIRES_REVIEW')
            self.assertFalse(db.exists())
            db.write_bytes(b'not a database')
            self.assertEqual(snapshot(**args)['status'],'UNAVAILABLE')
            self.assertEqual(db.read_bytes(),b'not a database')

    def test_actual_bootstrap_read_only_projection_and_expired_order_label(self):
        with TemporaryDirectory() as folder:
            config,args=fixture(Path(folder));run(**args,execute=True,clock=lambda:NOW,fetch=fetch)
            db=Path(config['database_path']);before=db.read_bytes()
            arguments=dict(database_path=db,simulation_id=config['simulation_id'],initial_cash='110')
            result=snapshot(**arguments,clock=lambda:NOW)
            self.assertEqual(result['status'],'AVAILABLE',result)
            self.assertTrue(result['orders'])
            self.assertEqual(result['daily']['decision_status'],'INITIAL_ORDERS_ACCEPTED')
            self.assertTrue(all(o['display_status']=='MODEL_ORDER_OPEN' for o in result['orders']))
            later=snapshot(**arguments,clock=lambda:NOW+timedelta(days=1))
            self.assertEqual(later['daily']['decision_status'],'NO_DECISION_RECORD')
            self.assertTrue(all(o['display_status']=='AWAITING_VERIFICATION' for o in later['orders']))
            self.assertEqual(db.read_bytes(),before)
            app=FastAPI();app.include_router(create_router(**arguments));client=TestClient(app)
            response=client.get('/api/current_portfolio_research/automatic_simulation')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn(str(db),response.text)
            self.assertEqual(client.get('/api/current_portfolio_research/automatic_simulation?database_path=other').status_code,400)
            self.assertEqual(db.read_bytes(),before)


if __name__=='__main__':unittest.main()
