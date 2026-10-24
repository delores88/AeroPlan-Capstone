"""Run integrity, import provenance, and export/view consistency."""
import base64
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app.store import Store
from app.ingest import stage_files,commit_import
from app.results import filtered,result_view,export_run


def fixture():
    rows=[dict(site_id='S1',part_id='P1',family='Engine',criticality='A',model='sba',
               buffer_z=2,baseline_cost=10,selected_cost=12,baseline_fill=.98,selected_fill=.96,
               demand=100,validation_feasible=True),
          dict(site_id='S2',part_id='P2',family='Electrical',criticality='B',model='ma8',
               buffer_z=1,baseline_cost=5,selected_cost=4,baseline_fill=.90,selected_fill=.95,
               demand=20,validation_feasible=False)]
    return dict(series=rows,policies=rows,replications=[],weekly=[],cohorts={'site':[]},forecasts={},
                provenance={'dataset':{}},summary={},inference={})


class IntegrityTests(unittest.TestCase):
    def test_completed_run_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory));rid=store.new_run('input',{'target':.95})
            store.finish_run(rid,result={'answer':1})
            with self.assertRaisesRegex(ValueError,'immutable'):
                store.finish_run(rid,result={'answer':2})
            self.assertEqual(store.run(rid)['result'],{'answer':1})

    def test_reading_store_does_not_interrupt_running_record(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory));rid=store.new_run('input',{})
            other=Store(Path(directory))
            self.assertEqual(other.run(rid)['status'],'running')
            other.recover_interrupted()
            self.assertEqual(other.run(rid)['status'],'interrupted')

    def test_import_rejects_changed_preview_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory))
            files={'parts_master.csv':b'part_id,unit_cost,lead_time_days\nP1,10,7\n',
                   'supply_chain_history.csv':b'site_id,part_id,week,demand\nS1,P1,2024-01-01,3\n'}
            stage=stage_files(store,[dict(name=k,content=base64.b64encode(v).decode()) for k,v in files.items()])
            (store.root/'staging'/stage['id']/'parts_master.csv').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed after preview'):
                commit_import(store,stage['id'],stage['suggested_mapping'],'Changed')
            self.assertEqual(store.datasets(),[])

    def test_filtered_export_matches_view_and_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory));run=dict(id='012345abcdef',dataset='input',status='complete',config={},result=fixture())
            query={'site':['S1'],'q':['p1'],'view':['inventory']}
            view=result_view(run,query)
            csv,_=export_run(run,store,query,'csv')
            self.assertEqual(view['total'],1)
            self.assertIn(b'P1',csv);self.assertNotIn(b'P2',csv)
            run['result']['series']*=51
            self.assertEqual(len(result_view(run,{'view':['inventory']})['rows']),50)
            self.assertEqual(len(export_run(run,store,{},'csv')[0].decode('utf-8-sig').splitlines()),103)

    def test_zip_checksum_manifest_covers_actual_export_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory));inputs=store.root/'datasets'/'input';inputs.mkdir(parents=True)
            (inputs/'source_csvs.zip').write_bytes(b'inputs')
            run=dict(id='012345abcdef',dataset='input',status='complete',config={},result=fixture())
            blob,_=export_run(run,store,{},'zip')
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                    digest,name=line.split('  ',1)
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)
                self.assertEqual(json.loads(archive.read('result.json'))['id'],run['id'])

    def test_pending_run_has_no_result_views(self):
        with self.assertRaisesRegex(ValueError,'no completed'):
            result_view(dict(status='running'),{})

if __name__=='__main__':unittest.main()
