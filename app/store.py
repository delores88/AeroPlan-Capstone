"""Local immutable dataset versions and experiment records in SQLite."""
from __future__ import annotations
import json, sqlite3, threading, uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Store:
    def __init__(self, root: Path):
        self.root=root.resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/'aeroplan.sqlite3';self.lock=threading.RLock()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS parts(dataset TEXT,part_id TEXT,payload TEXT,PRIMARY KEY(dataset,part_id));
            CREATE TABLE IF NOT EXISTS history(dataset TEXT,site_id TEXT,part_id TEXT,week TEXT,payload TEXT,PRIMARY KEY(dataset,site_id,part_id,week));
            CREATE INDEX IF NOT EXISTS ix_history_scope ON history(dataset,site_id,part_id,week);
            CREATE TABLE IF NOT EXISTS orders(dataset TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS quality(dataset TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,dataset TEXT,created TEXT,status TEXT,config TEXT,result TEXT,error TEXT);
            CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT);
            ''')
            c.execute("INSERT OR IGNORE INTO settings VALUES ('schema_version','1')")
    def recover_interrupted(self):
        with self.connect() as c:
            c.execute("UPDATE runs SET status='interrupted',error='Application stopped before this run completed. Create a new run to retry.' WHERE status IN ('running','queued')")
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db_path,timeout=60);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    def get_setting(self,key,default=None):
        with self.connect() as c:
            row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else default
    def set_setting(self,key,value):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
    def datasets(self):
        with self.connect() as c:return [json.loads(x[0]) for x in c.execute('SELECT metadata FROM datasets ORDER BY rowid DESC')]
    def metadata(self,dataset=None):
        did=dataset or self.get_setting('active_dataset')
        with self.connect() as c:
            row=c.execute('SELECT metadata FROM datasets WHERE id=?',(did,)).fetchone()
            if not row: raise ValueError('Dataset not found. Import a dataset first.')
            return json.loads(row[0])
    def save_dataset(self,meta,parts,history,orders,quality):
        did=meta['id']
        with self.lock,self.connect() as c:
            c.execute('INSERT INTO datasets VALUES (?,?)',(did,json.dumps(meta)))
            c.executemany('INSERT INTO parts VALUES (?,?,?)',((did,x['part_id'],json.dumps(x)) for x in parts))
            c.executemany('INSERT INTO history VALUES (?,?,?,?,?)',((did,x['site_id'],x['part_id'],x['week'],json.dumps(x)) for x in history))
            c.executemany('INSERT INTO orders VALUES (?,?)',((did,json.dumps(x)) for x in orders))
            c.executemany('INSERT INTO quality VALUES (?,?)',((did,json.dumps(x)) for x in quality))
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('active_dataset',json.dumps(did)))
    def load(self,dataset=None):
        meta=self.metadata(dataset);did=meta['id']
        with self.connect() as c:
            parts={x[0]:json.loads(x[1]) for x in c.execute('SELECT part_id,payload FROM parts WHERE dataset=?',(did,))}
            groups={}
            for site,part,payload in c.execute('SELECT site_id,part_id,payload FROM history WHERE dataset=? ORDER BY site_id,part_id,week',(did,)):
                groups.setdefault((site,part),[]).append(json.loads(payload))
            orders=[json.loads(x[0]) for x in c.execute('SELECT payload FROM orders WHERE dataset=?',(did,))]
            quality=[json.loads(x[0]) for x in c.execute('SELECT payload FROM quality WHERE dataset=?',(did,))]
        return meta,parts,groups,orders,quality
    def new_run(self,dataset,config):
        rid=uuid.uuid4().hex[:12]
        with self.connect() as c:c.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',(rid,dataset,now(),'running',json.dumps(config),None,None))
        return rid
    def finish_run(self,rid,result=None,error=None,status=None):
        with self.connect() as c:
            changed=c.execute("UPDATE runs SET status=?,result=?,error=? WHERE id=? AND status='running'",(status or ('failed' if error else 'complete'),json.dumps(result,allow_nan=False) if result is not None else None,error,rid)).rowcount
            if not changed:raise ValueError('A finished run is immutable. Create a new run.')
    def run(self,rid):
        with self.connect() as c:row=c.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()
        if not row:raise ValueError('Run not found.')
        d=dict(row);d['config']=json.loads(d['config']);d['result']=json.loads(d['result']) if d['result'] else None;return d
    def runs(self):
        with self.connect() as c:rows=c.execute('SELECT id,dataset,created,status,config,error FROM runs ORDER BY created DESC,rowid DESC').fetchall()
        return [{**dict(x),'config':json.loads(x['config'])} for x in rows]
