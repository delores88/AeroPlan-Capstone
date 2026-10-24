"""Dependency-free regression tests. Run: python -m unittest discover -s tests -v."""
import base64,copy,hashlib,io,json,math,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from datetime import date,timedelta
from http.client import HTTPConnection
from app.forecast import forecasts,metrics,segment,future
from app.engine import DEFAULTS,config_checked,target_stock,simulate,lead_profile,run_experiment,Cancelled
from app.ingest import num,parsedate,read_csv,stage_files,commit_import
from app.store import Store
from app.server import Application,LocalServer
from app.reports import csv_bytes,pdf_report,html_report,export_zip
ROOT=Path(__file__).resolve().parents[1]

def upload(name,raw):return {'name':name,'content':base64.b64encode(raw).decode()}

def small_files():
    return [upload('parts_master.csv',b'part_id,unit_cost,lead_time_days\nP1,25,14\n'),upload('supply_chain_history.csv',b'site_id,part_id,week,demand\nS1,P1,2024-01-01,4\nS1,P1,2024-01-08,0\n')]

class ForecastTests(unittest.TestCase):
    def test_all_forecasts_are_causal(self):
        y=[0,0,5,0,12,1,0,7]*15;changed=y[:70]+[999]*50
        a,b=forecasts(y),forecasts(changed)
        for m in a:self.assertEqual(a[m][:71],b[m][:71],m)
    def test_output_includes_next_step(self):
        for values in forecasts([1,2,3]).values():self.assertEqual(len(values),4)
    def test_naive_and_ma8(self):
        f=forecasts(list(range(1,11)));self.assertEqual(f['naive'][-1],10);self.assertEqual(f['ma8'][-1],6.5)
    def test_seasonal_naive(self):
        self.assertEqual(forecasts(list(range(60)))['seasonal52'][59],7)
    def test_seasonal_fallback(self):self.assertEqual(future([2,4],'seasonal52',1),[3])
    def test_zero_demand_metrics(self):
        m=metrics([0,0],[1,1]);self.assertIsNone(m['wape']);self.assertIsNone(m['bias']);self.assertEqual(m['mae'],1)
    def test_signed_metrics(self):
        m=metrics([2,4],[3,5]);self.assertEqual(m['mae'],1);self.assertEqual(m['rmse'],1);self.assertAlmostEqual(m['bias'],1/3)
    def test_segments(self):
        self.assertEqual(segment([2]*20)['segment'],'Smooth');self.assertEqual(segment([0]*20)['segment'],'No demand');self.assertEqual(segment([0,0,2]*10)['segment'],'Intermittent')
    def test_tsb_decay(self):
        f=forecasts([10]*10+[0]*20)['tsb'];self.assertLess(f[-1],f[10])
    def test_future_nonnegative(self):
        for m in forecasts([0,5,0,12]):self.assertTrue(all(x>=0 for x in future([0,5,0,12],m,13)))

class ImportTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name))
    def tearDown(self):self.temp.cleanup()
    def do_import(self,files=None,**kwargs):
        s=stage_files(self.store,files or small_files());return commit_import(self.store,s['id'],s['suggested_mapping'],'Test',**kwargs)
    def test_import_optional_tables_absent(self):
        m=self.do_import();self.assertEqual(m['history_rows'],2);self.assertEqual(m['purchase_orders'],0)
    def test_lead_weeks_converted(self):
        self.do_import(lead_unit='weeks');self.assertEqual(self.store.load()[1]['P1']['lead_time_days'],98)
    def test_immutable_versions(self):
        a=self.do_import();b=self.do_import();self.assertNotEqual(a['id'],b['id']);self.assertEqual(len(self.store.datasets()),2)
    def test_duplicate_reject_preserves_active(self):
        old=self.do_import();fs=small_files();fs[1]=upload('supply_chain_history.csv',b'site_id,part_id,week,demand\nS1,P1,2024-01-01,4\nS1,P1,2024-01-01,7\n')
        with self.assertRaisesRegex(ValueError,'duplicate'):self.do_import(fs)
        self.assertEqual(self.store.get_setting('active_dataset'),old['id'])
    def test_orphan_rejected(self):
        fs=small_files();fs[1]=upload('supply_chain_history.csv',b'site_id,part_id,week,demand\nS1,OTHER,2024-01-01,4\n')
        with self.assertRaisesRegex(ValueError,'missing from parts'):self.do_import(fs)
    def test_negative_demand_rejected(self):
        fs=small_files();fs[1]=upload('supply_chain_history.csv',b'site_id,part_id,week,demand\nS1,P1,2024-01-01,-4\n')
        with self.assertRaisesRegex(ValueError,'nonnegative'):self.do_import(fs)
    def test_invalid_zip(self):
        with self.assertRaises(ValueError):stage_files(self.store,[upload('bad.zip',b'notzip')])
    def test_zip_paths_not_extracted(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../../safe.csv','a,b\n1,2\n')
        s=stage_files(self.store,[upload('data.zip',b.getvalue())]);self.assertIn('safe.csv',s['files']);self.assertFalse((Path(self.temp.name).parent/'safe.csv').exists())
    def test_duplicate_headers_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):read_csv(b'x,x\n1,2\n')
    def test_number_checks(self):
        for x in ['-1','inf','-inf','1e999','$20','1,200']:
            with self.assertRaises(ValueError):num(x,True)
    def test_dates_and_week(self):
        self.assertEqual(parsedate('2024-W01'),'2024-01-01');self.assertEqual(parsedate('04/03/2024','mdy'),'2024-04-03');self.assertEqual(parsedate('04/03/2024','dmy'),'2024-03-04')
    def test_invalid_dates(self):
        with self.assertRaises(ValueError):parsedate('2024-02-30')
    def test_semicolon_utf8_bom(self):
        h,r=read_csv('\ufeffx;y\n1;2\n'.encode());self.assertEqual(h,['x','y']);self.assertEqual(r[0]['y'],'2')

class PolicyTests(unittest.TestCase):
    def test_configuration_boundaries(self):
        for raw in [{'target':float('nan')},{'target':2},{'review_weeks':1.5},{'models':[]},{'use_empirical':'false'},{'seed':-1}]:
            with self.assertRaises(ValueError):config_checked(raw)
    def test_target_increases_with_buffer(self):
        lead={'mean_days':14,'std_days':3};self.assertGreater(target_stock(10,3,lead,DEFAULTS,2),target_stock(10,3,lead,DEFAULTS,0))
    def test_receipt_timing_and_conservation(self):
        s=simulate([2]*8,[2]*9,0,8,dict(stock=0,backlog=0,pipeline=[]),{'mean_days':7,'std_days':0},DEFAULTS,0,0,10,[1]*8,trace=True)
        self.assertEqual(s['trace'][0]['receipts'],0);self.assertEqual(s['trace'][1]['receipts'],0);self.assertGreater(s['trace'][2]['receipts'],0)
        received=sum(r['receipts'] for r in s['trace']);self.assertAlmostEqual(received-16,s['state']['stock']-s['state']['backlog']);self.assertAlmostEqual(sum(r['carrying_cost'] for r in s['trace']),s['carrying_cost'])
    def test_late_backlog_not_immediate_fill(self):
        s=simulate([0],[0,0],0,1,dict(stock=4,backlog=4,pipeline=[]),{'mean_days':7,'std_days':0},DEFAULTS,0,0,10,[1],trace=True)
        self.assertEqual(s['immediate_filled'],0);self.assertEqual(s['end_backlog'],0);self.assertIsNone(s['fill_rate'])
    def test_score_window_counts_only_test_orders(self):
        s=simulate([2]*8,[2]*9,0,8,dict(stock=0,backlog=0,pipeline=[]),{'mean_days':7,'std_days':0},DEFAULTS,0,0,10,[1]*8,score_start=5,trace=True)
        self.assertEqual(s['weeks'],3);self.assertEqual(s['ordered_units'],sum(r['ordered'] for r in s['trace']));self.assertEqual(s['demand'],6)
    def test_lead_distribution_excludes_future_receipts(self):
        orders=[dict(part_id='P',site_id='S',order_date='2020-01-01',receipt_date='2020-01-15') for _ in range(3)]
        orders.append(dict(part_id='P',site_id='S',order_date='2020-01-01',receipt_date='2020-12-15'))
        lp=lead_profile({'part_id':'P','lead_time_days':30},orders,'S','2020-02-01',DEFAULTS)
        self.assertEqual(lp['sample_count'],3);self.assertEqual(lp['mean_days'],14)
    def test_insufficient_pos_fallback(self):
        lp=lead_profile({'part_id':'P','lead_time_days':21},[],'S','2020-02-01',DEFAULTS);self.assertEqual(lp['mean_days'],21);self.assertEqual(lp['sample_count'],0)

class IntegratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.app=Application(ROOT,Path(cls.temp.name),demo=True);cls.dataset=cls.app.data();cls.result=run_experiment(cls.dataset,{'max_series':12});cls.rid=cls.app.store.new_run(cls.dataset[0]['id'],cls.result['config']);cls.app.store.finish_run(cls.rid,result=cls.result);cls.record=cls.app.store.run(cls.rid)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_demo_provenance_forced(self):self.assertEqual(self.dataset[0]['source_kind'],'demo');self.assertEqual(self.dataset[0]['history_rows'],28080)
    def test_repeatable_calculations(self):
        r=run_experiment(self.dataset,{'max_series':12});self.assertEqual(r['summary'],self.result['summary']);self.assertEqual(r['bootstrap'],self.result['bootstrap'])
    def test_heldout_demand_cannot_select_models_or_buffers(self):
        d=copy.deepcopy(self.dataset);cut=self.result['split']['test_start']
        for rows in d[2].values():
            for row in rows:
                if row['week']>=cut:row['demand']*=50
        r=run_experiment(d,{'max_series':12})
        self.assertEqual([(s['model'],s['buffer_z'],s['lead']) for s in r['series']],[(s['model'],s['buffer_z'],s['lead']) for s in self.result['series']])
    def test_infeasible_targets_remain_visible(self):
        r=run_experiment(self.dataset,{'max_series':12,'target':.999});self.assertTrue(all(s['validation_feasible']==(s['validation_policy']['fill_rate'] is None or s['validation_policy']['fill_rate']>=.999) for s in r['series']))
    def test_missing_weeks_excluded(self):
        d=copy.deepcopy(self.dataset);k=sorted(d[2])[0];d[2][k].pop(20);r=run_experiment(d,{'max_series':12});self.assertEqual(len(r['skipped']),1)
    def test_cancellation(self):
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):run_experiment(self.dataset,{'max_series':12},cancel=event)
    def test_pdf_structure_and_demo_marking(self):
        p=pdf_report(self.record);self.assertTrue(p.startswith(b'%PDF-1.4'));self.assertIn(b'%%EOF',p);self.assertIn(b'DEMONSTRATION',p.upper())
    def test_html_offline_and_escaped_notes(self):
        b=html_report(self.record,{'author':'<script>bad</script>','notes':'<img src=x onerror=alert(1)>'}).decode();self.assertIn('&lt;script&gt;bad',b);self.assertNotIn('<script>bad',b);self.assertNotIn('fetch(',b);self.assertNotIn('src="https:',b)
    def test_csv_formula_safety(self):self.assertIn(b"'=2+2",csv_bytes([{'x':'=2+2'}]))
    def test_evidence_export_and_hashes(self):
        raw=export_zip(self.record,self.dataset,methodology=(ROOT/'docs/METHODOLOGY.md').read_text(encoding='utf-8'))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('DEMONSTRATION_NOTICE.txt',z.namelist());self.assertIn('Instructor_Report.pdf',z.namelist())
            for line in z.read('SHA256SUMS.txt').decode().splitlines():
                digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
    def test_import_export_reproduction(self):
        raw=export_zip(self.record,self.dataset);z=zipfile.ZipFile(io.BytesIO(raw));fs=[upload(Path(n).name,z.read(n)) for n in z.namelist() if n.startswith('inputs/') and n.endswith('.csv')]
        with tempfile.TemporaryDirectory() as tmp:
            st=Store(Path(tmp));p=stage_files(st,fs);commit_import(st,p['id'],p['suggested_mapping'],'Reimport');r=run_experiment(st.load(),self.result['config']);self.assertEqual(r['summary']['baseline'],self.result['summary']['baseline']);self.assertEqual(r['summary']['optimized'],self.result['summary']['optimized'])

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.app=Application(ROOT,Path(cls.tmp.name),demo=True);cls.server=LocalServer(0,cls.app);cls.port=cls.server.server_address[1];cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def req(self,path='/',method='GET',headers=None,body=None):
        c=HTTPConnection('127.0.0.1',self.port);c.request(method,path,body=body,headers=headers or {});r=c.getresponse();status=r.status;out=r.read();c.close();return status,out
    def test_health(self):self.assertEqual(self.req('/api/health')[0],200)
    def test_host_rebinding_blocked(self):self.assertEqual(self.req('/api/health',headers={'Host':'evil.example'})[0],403)
    def test_post_without_token_blocked(self):self.assertEqual(self.req('/api/notes','POST',{'Content-Type':'application/json'},'{}')[0],403)
    def test_foreign_origin_blocked(self):self.assertEqual(self.req('/api/notes','POST',{'Content-Type':'application/json','X-AeroPlan-Token':self.app.token,'Origin':'https://evil.example'},'{}')[0],403)
    def test_notes_and_methodology(self):
        status,_=self.req('/api/notes','POST',{'Content-Type':'application/json','X-AeroPlan-Token':self.app.token},json.dumps({'author':'Tester','question':'Question','notes':'Note'}));self.assertEqual(status,200);self.assertEqual(self.req('/api/methodology')[0],200)
    def test_no_arbitrary_static_path(self):self.assertNotEqual(self.req('/app/server.py')[0],200)
    def test_data_page(self):
        status,b=self.req('/api/table?table=history&page=1');self.assertEqual(status,200);self.assertEqual(len(json.loads(b)['rows']),50)

if __name__=='__main__':unittest.main()
