"""Loopback-only HTTP API. No external service clients or runtime downloads."""
from __future__ import annotations
import base64, hashlib, json, logging, math, mimetypes, os, re, secrets, threading
from collections import Counter,defaultdict
from datetime import date
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from . import VERSION
from .store import Store
from .ingest import stage_files,commit_import
from .demo import create_demo
from .forecast import MODELS,segment,mean
from .engine import Cancelled
from .results import result_view,export_run,capture_source,source_identity
from .reports import html_report,pdf_report,export_zip,csv_bytes,series_rows
from .schema import TABLES,SOURCE_URL

class Application:
    def __init__(self,root,workspace,demo=False):
        self.root=Path(root).resolve();self.store=Store(Path(workspace));self.token=secrets.token_urlsafe(32)
        self.lock=threading.RLock();self.cached={};self.progress={};self.active_run=None;self.cancel_event=None;self.result_cache={}
        self.store.recover_interrupted()
        if not self.store.datasets():
            archive=self.root/'data'/('demonstration.zip' if demo else 'aerospace-v1.zip')
            if demo and not archive.exists():create_demo(archive)
            if not archive.exists():raise ValueError('The bundled aerospace-v1.zip dataset is missing.')
            if not demo and hashlib.sha256(archive.read_bytes()).hexdigest()!='844ba09645c33a09dbb2be28b9a8f560815ef38929ddcc818b33ecc3df2d8168':
                raise ValueError('Bundled dataset checksum does not match version 1.')
            stage=stage_files(self.store,[dict(name=archive.name,content=base64.b64encode(archive.read_bytes()).decode())])
            commit_import(self.store,stage['id'],stage['suggested_mapping'],
                'Industrial demonstration' if demo else 'Aerospace supply chain · Version 1','demo' if demo else 'kaggle')
        if self.store.get_setting('author_notes') is None:
            self.store.set_setting('author_notes',dict(author='Ben Van Dorn',question='How do demand-model selection and service-constrained inventory policies change simulated inventory investment and part availability relative to a fixed-buffer baseline?',notes=''))
    def data(self,did=None):
        did=did or self.store.get_setting('active_dataset')
        with self.lock:
            if did not in self.cached:
                self.cached={did:self.store.load(did)}
            return self.cached[did]
    def overview(self,did=None):
        meta,parts,groups,orders,quality=self.data(did);totals=defaultdict(float);segments=Counter();items=[]
        stockvalue=0.;stockcoverage=0;backlog=0.;blocked=0.;zero=0;demand=0.
        for (site,pid),rs in groups.items():
            s=segment([x['demand'] for x in rs]);segments[s['segment']]+=1;latest=rs[-1]
            for row in rs:totals[row['week']]+=row['demand'];zero+=int(row['demand']==0);demand+=row['demand']
            if latest['on_hand'] is not None:stockvalue+=latest['on_hand']*parts[pid]['unit_cost'];stockcoverage+=1
            backlog+=latest.get('backorders') or 0.;blocked+=latest.get('blocked_stock') or 0.
            items.append(dict(site_id=site,part_id=pid,family=parts[pid]['family'],criticality=parts[pid]['criticality'],description=parts[pid]['description'],**s,
              total_demand=sum(x['demand'] for x in rs),weeks=len(rs),latest_on_hand=latest['on_hand'],latest_backorders=latest.get('backorders')))
        supplier=defaultdict(list)
        for o in orders:supplier[o.get('supplier_id') or 'Unspecified'].append(o)
        suppliers=[]
        for sid,rows in sorted(supplier.items()):
            closed=[o for o in rows if o.get('receipt_date') and o['receipt_date']<=meta['end']]
            dated=[o for o in closed if o.get('promised_date')]
            full=[o for o in dated if o.get('quantity') is not None and o.get('received_quantity') is not None]
            lts=[(date.fromisoformat(o['receipt_date'])-date.fromisoformat(o['order_date'])).days for o in closed]
            suppliers.append(dict(supplier_id=sid,orders=len(rows),closed_orders=len(closed),mean_lead_days=mean(lts) if lts else None,
              on_time_rate=sum(o['receipt_date']<=o['promised_date'] for o in dated)/len(dated) if dated else None,
              otif=sum(o['receipt_date']<=o['promised_date'] and o['received_quantity']>=o['quantity'] for o in full)/len(full) if full else None))
        return dict(metadata=meta,datasets=self.store.datasets(),segments=dict(segments),trend=[dict(week=k,demand=v) for k,v in sorted(totals.items())],
          total_demand=demand,zero_demand_share=zero/meta['history_rows'],latest_on_hand_value=stockvalue,stock_snapshot_series=stockcoverage,
          latest_backorders=backlog,latest_blocked=blocked,series=items,suppliers=suppliers,
          sites=sorted({k[0] for k in groups}),families=sorted({p['family'] for p in parts.values()}),criticalities=sorted({p['criticality'] for p in parts.values()}))
    def start_run(self,raw):
        from .runner import check_new_run,run_configured
        c=check_new_run(raw)
        with self.lock:
            if self.active_run:raise ValueError('Another evaluation is still running. Finish or cancel it first.')
            did=self.store.get_setting('active_dataset');rid=self.store.new_run(did,c);self.active_run=rid;event=threading.Event();self.cancel_event=event
            self.progress[rid]=dict(done=0,total=1,message='Preparing local data',status='running')
        def work():
            try:
                folder=self.store.root/'runs'/rid;folder.mkdir(parents=True,exist_ok=False)
                source=capture_source(self.root,folder)
                (folder/'source.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
                def update(done,total,message):
                    with self.lock:self.progress[rid]=dict(done=done,total=total,message=message,status='running')
                def freeze(snapshot):
                    snapshot={**snapshot,'run_id':rid,'source':source,'dataset_id':did}
                    with (folder/'frozen.json').open('x',encoding='utf-8') as out:
                        json.dump(snapshot,out,indent=2,allow_nan=False)
                result=run_configured(self.data(did),c,update,event,freeze_callback=freeze)
                if event.is_set():raise Cancelled('Cancelled before results were saved.')
                if source_identity(self.root)!=source:raise ValueError('Application code changed during evaluation. Create a new run.')
                result['provenance']['source']=source
                result['dataset']=self.store.metadata(did)
                self.store.finish_run(rid,result=result)
                with self.lock:self.progress[rid]=dict(done=1,total=1,message='Complete',status='complete')
            except Cancelled as e:
                self.store.finish_run(rid,error=str(e),status='cancelled')
                with self.lock:self.progress[rid]=dict(done=0,total=1,message=str(e),status='cancelled')
            except Exception as e:
                logging.exception('Experiment failed')
                self.store.finish_run(rid,error=str(e))
                with self.lock:self.progress[rid]=dict(done=0,total=1,message=str(e),status='failed')
            finally:
                with self.lock:self.active_run=None;self.cancel_event=None
        threading.Thread(target=work,name='AeroPlan-experiment',daemon=True).start()
        return rid
    def run(self,rid):
        with self.lock:
            if rid in self.result_cache:return self.result_cache[rid]
        run=self.store.run(rid)
        if run['status']=='complete':
            with self.lock:
                self.result_cache={rid:run}
        return run

class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,port,application):
        self.app=application;super().__init__(('127.0.0.1',port),Handler)

class Handler(BaseHTTPRequestHandler):
    server_version='AeroPlanLocal/'+VERSION
    def log_message(self,fmt,*args):logging.info(fmt,*args)
    def trusted(self):
        port=self.server.server_address[1]
        return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
    def headers_out(self,code,ctype,length,filename=None):
        self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(length));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers()
    def send_blob(self,body,ctype='application/json; charset=utf-8',code=200,filename=None):
        self.headers_out(code,ctype,len(body),filename)
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def json(self,obj,code=200):self.send_blob(json.dumps(obj,allow_nan=False).encode(),code=code)
    def bad(self,msg,code=400):self.json({'error':str(msg)},code)
    def do_GET(self):
        if not self.trusted():self.bad('Host is not allowed.',403);return
        app=self.server.app;parts=urlsplit(self.path);path=parts.path;q=parse_qs(parts.query)
        try:
            if path=='/api/health':self.json(dict(status='ok',application='AeroPlan Local',version=VERSION));return
            if path=='/api/state':
                from .optimization import DEFAULTS
                from .runner import POLICY_MODES
                self.json(dict(version=VERSION,token=app.token,defaults=DEFAULTS,policy_modes=POLICY_MODES,models=MODELS,source_url=SOURCE_URL,active_dataset=app.store.get_setting('active_dataset'),datasets=app.store.datasets(),active_run=app.active_run));return
            if path=='/api/overview':self.json(app.overview());return
            if path=='/api/runs':self.json(app.store.runs());return
            if path=='/api/progress':self.json(dict(active=app.active_run,runs=app.progress));return
            if path=='/api/methodology':self.json(dict(text=(app.root/'docs'/'METHODOLOGY.md').read_text(encoding='utf-8')));return
            if path=='/api/table':
                table=q.get('table',['history'])[0];page=max(0,int(q.get('page',['0'])[0]));limit=50
                meta,ps,gs,os,qs=app.data()
                if table=='parts':rows=list(ps.values())
                elif table=='history':rows=[r for group in gs.values() for r in group]
                elif table=='orders':rows=os
                elif table=='quality':rows=qs
                else:raise ValueError('Unknown table.')
                self.json(dict(rows=rows[page*limit:(page+1)*limit],total=len(rows),page=page,limit=limit));return
            m=re.fullmatch(r'/api/runs/([a-f0-9]{12})',path)
            if m:self.json(app.run(m.group(1)));return
            m=re.fullmatch(r'/api/results/([a-f0-9]{12})',path)
            if m:self.json(result_view(app.run(m.group(1)),q));return
            m=re.fullmatch(r'/api/export/([a-f0-9]{12})/(zip|pdf|html|json|csv|cohorts)',path)
            if m:
                run=app.run(m.group(1));kind=m.group(2)
                if run['status']!='complete':raise ValueError('Only completed runs can be exported.')
                if 'inference' in run['result']:
                    if kind in ('pdf','html'):raise ValueError('Choose CSV, JSON or the complete ZIP export.')
                    blob,ct=export_run(run,app.store,q,kind)
                    ext='csv' if kind=='cohorts' else kind
                    self.send_blob(blob,ct,filename=f'AeroPlan_{run["id"]}_{kind}.{ext}');return
                notes=app.store.get_setting('author_notes');prefix='DEMO_' if run['result']['dataset']['source_kind']=='demo' else ''
                if kind=='pdf':blob=pdf_report(run,notes);ct='application/pdf'
                elif kind=='html':blob=html_report(run,notes);ct='text/html; charset=utf-8'
                elif kind=='csv':blob=csv_bytes(series_rows(run['result']));ct='text/csv; charset=utf-8'
                elif kind=='json':blob=json.dumps(run,indent=2,allow_nan=False).encode();ct='application/json'
                else:blob=export_zip(run,app.data(run['dataset']),notes,(app.root/'docs'/'METHODOLOGY.md').read_text(encoding='utf-8'));ct='application/zip'
                self.send_blob(blob,ct,filename=f'{prefix}AeroPlan_{run["id"]}.{kind}');return
            allowed={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css','/favicon.svg':'favicon.svg'}
            if path in allowed:
                fp=app.root/'web'/allowed[path];self.send_blob(fp.read_bytes(),mimetypes.guess_type(fp.name)[0] or 'application/octet-stream');return
            self.bad('Not found.',404)
        except (ValueError,KeyError,TypeError) as e:self.bad(e)
        except Exception:
            logging.exception('Request failed');self.bad('Local request failed. See workspace/aeroplan.log for details.',500)
    def do_POST(self):
        if not self.trusted():self.bad('Host is not allowed.',403);return
        app=self.server.app;port=self.server.server_address[1]
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
            self.bad('Cross-origin writes are not allowed.',403);return
        if not secrets.compare_digest(self.headers.get('X-AeroPlan-Token',self.headers.get('X-Local-Token','')),app.token):self.bad('Session expired. Refresh the page.',403);return
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.bad('JSON content is required.',415);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100*1024*1024:self.bad('Request body exceeds the 100 MB limit.',413);return
            body=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
            if not isinstance(body,dict):raise ValueError('Request must be a JSON object.')
            if path=='/api/import/preview':self.json(stage_files(app.store,body.get('files',[])));return
            if path=='/api/import/commit':
                m=commit_import(app.store,body['stage_id'],body['mapping'],body.get('title',''),body.get('source_kind','local'),body.get('lead_unit','days'),body.get('date_format','iso'))
                self.json(m);return
            if path=='/api/activate':
                did=body.get('id',body.get('dataset_id'));app.store.metadata(did);app.store.set_setting('active_dataset',did);self.json(dict(ok=True));return
            if path=='/api/run':self.json(dict(id=app.start_run(body)),202);return
            if path=='/api/cancel':
                with app.lock:
                    if app.cancel_event:app.cancel_event.set()
                self.json(dict(ok=True));return
            if path=='/api/notes':
                notes={k:str(body.get(k,''))[:12000] for k in ('author','question','notes')};app.store.set_setting('author_notes',notes);self.json(notes);return
            self.bad('Not found.',404)
        except (ValueError,KeyError,TypeError) as e:self.bad(e)
        except Exception:
            logging.exception('Local write failed');self.bad('Local operation failed. Existing records were not intentionally removed. See the log.',500)
