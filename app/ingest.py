"""Preview, explicit mapping, strict validation, and atomic local import."""
from __future__ import annotations
import base64, csv, hashlib, io, json, math, re, uuid, zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from .schema import TABLES, SOURCE_URL, SOURCE_TITLE
from .store import now

MAX_EXPANDED=250*1024*1024
MAX_ROWS=1000000

def normal(x):return re.sub(r'[^a-z0-9]','',str(x).lower())
def read_csv(raw):
    try: text=raw.decode('utf-8-sig')
    except UnicodeDecodeError: text=raw.decode('cp1252')
    if '\x00' in text:raise ValueError('A CSV contains null bytes; export it as UTF-8 CSV.')
    try:dialect=csv.Sniffer().sniff(text[:10000],delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    reader=csv.DictReader(io.StringIO(text,newline=''),dialect=dialect)
    if not reader.fieldnames:raise ValueError('A CSV has no header.')
    headers=[str(h).strip() for h in reader.fieldnames]
    if len(set(headers))!=len(headers):raise ValueError('Duplicate column names in a CSV.')
    reader.fieldnames=headers
    rows=[]
    for row in reader:
        if None in row:raise ValueError('CSV row contains more fields than its header.')
        if not any(v is not None and str(v).strip() for v in row.values()):continue
        rows.append(row)
        if len(rows)>MAX_ROWS:raise ValueError('CSV exceeds the 1,000,000-row safety limit.')
    return headers,rows

def stage_files(store,uploads):
    if not uploads or len(uploads)>10:raise ValueError('Choose one ZIP or up to 10 CSV files.')
    sid=uuid.uuid4().hex;folder=store.root/'staging'/sid;folder.mkdir(parents=True)
    files={};total=0;hashes={};is_demo=False
    for upload in uploads:
        name=Path(upload.get('name','')).name
        try:raw=base64.b64decode(upload['content'],validate=True)
        except Exception as e:raise ValueError('Invalid upload encoding.') from e
        hashes[name]=hashlib.sha256(raw).hexdigest()
        if name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    entries=z.infolist()
                    if len(entries)>200:raise ValueError('ZIP has too many entries; upload only the four dataset tables.')
                    if sum(x.file_size for x in entries)>MAX_EXPANDED:raise ValueError('ZIP expands beyond 250 MB.')
                    is_demo |= any(Path(x.filename).name=='DEMONSTRATION_NOTICE.txt' for x in entries)
                    for x in entries:
                        if x.is_dir() or not x.filename.lower().endswith('.csv'):continue
                        n=Path(x.filename).name
                        if n in files:raise ValueError(f'Duplicate CSV filename: {n}')
                        files[n]=z.read(x)
            except zipfile.BadZipFile as e:raise ValueError('This file is not a valid ZIP archive.') from e
        elif name.lower().endswith('.csv'):
            if name in files:raise ValueError(f'Duplicate filename: {name}')
            files[name]=raw
        else:raise ValueError('Only CSV and ZIP files are accepted.')
    if not files:raise ValueError('No CSV files found in the upload.')
    total=sum(len(v) for v in files.values())
    if total>MAX_EXPANDED:raise ValueError('CSV files exceed 250 MB total.')
    previews={}
    for n,raw in files.items():
        headers,rows=read_csv(raw)
        if not rows:raise ValueError(f'{n} is empty.')
        (folder/n).write_bytes(raw)
        previews[n]=dict(columns=headers,rows=len(rows),sample=rows[:3],sha256=hashlib.sha256(raw).hexdigest())
    mappings={}
    for table,spec in TABLES.items():
        name=next((n for n in files if normal(n)==normal(spec['filename'])),None)
        if not name:
            # Only suggest a file when enough required fields match; user still confirms.
            for n,p in previews.items():
                norms={normal(x) for x in p['columns']}
                if spec['required'] and all(any(normal(a) in norms for a in spec['fields'][f]) for f in spec['required']):name=n;break
        columns=previews[name]['columns'] if name else []
        mappings[table]={'file':name,'fields':{f:next((c for a in aliases for c in columns if normal(c)==normal(a)),None) for f,aliases in spec['fields'].items()}}
    manifest=dict(id=sid,files=previews,original_hashes=hashes,is_demo=is_demo,created=now())
    (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return {**manifest,'suggested_mapping':mappings,'contract':TABLES}

def num(v,required=False):
    if v is None or str(v).strip().lower() in ('','nan','null','none','n/a','na'):
        if required:raise ValueError('required number is blank')
        return None
    # Currency symbols and thousands separators are deliberately not guessed.
    try:x=float(str(v).strip())
    except ValueError as e:raise ValueError(f'not a plain numeric value: {str(v)[:40]}') from e
    if not math.isfinite(x) or x<0:raise ValueError('numbers must be finite and nonnegative')
    return x

def parsedate(v,fmt='iso',required=False):
    if v is None or not str(v).strip() or str(v).strip().lower() in ('nan','nat','null','none','n/a'):
        if required:raise ValueError('required date is blank')
        return None
    s=str(v).strip()
    try:
        if re.fullmatch(r'\d{4}-W\d{2}',s):return date.fromisocalendar(int(s[:4]),int(s[-2:]),1).isoformat()
        if re.match(r'^\d{4}-\d{2}-\d{2}',s):return date.fromisoformat(s[:10]).isoformat()
        formats={'iso':'%Y/%m/%d','mdy':'%m/%d/%Y','dmy':'%d/%m/%Y'}
        return datetime.strptime(s,formats[fmt]).date().isoformat()
    except (ValueError,KeyError) as e:raise ValueError(f'cannot parse date {s[:40]}; check the date-format selection') from e

def commit_import(store,stage_id,mapping,title,source_kind='local',lead_unit='days',date_format='iso'):
    if not re.fullmatch('[a-f0-9]{32}',stage_id):raise ValueError('Invalid import ID.')
    folder=store.root/'staging'/stage_id
    if not (folder/'manifest.json').exists():raise ValueError('Import preview expired. Select your files again.')
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['is_demo']:source_kind='demo'
    if source_kind not in ('demo','kaggle','local'):raise ValueError('Unknown source type.')
    if lead_unit not in ('days','weeks') or date_format not in ('iso','mdy','dmy'):raise ValueError('Invalid units/date format.')
    loaded={};errors=[]
    for table,spec in TABLES.items():
        m=mapping.get(table,{})
        fn=m.get('file')
        if not fn:
            if table in ('parts','history'):errors.append(f'{table}: select a CSV file')
            loaded[table]=[];continue
        if fn not in manifest['files']:raise ValueError('Selected file is not in the import preview.')
        raw=(folder/fn).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest['files'][fn]['sha256']:
            raise ValueError('Import source changed after preview. Select the files again.')
        headers,rows=read_csv(raw)
        fm=m.get('fields',{})
        for field in spec['required']:
            if fm.get(field) not in headers:errors.append(f'{table}: map required field {field}')
        if table=='quality':loaded[table]=rows;continue
        unknown=[v for v in fm.values() if v and v not in headers]
        if unknown:errors.append(f'{table}: unknown source columns {unknown}')
        loaded[table]=[{f:r.get(fm.get(f)) if fm.get(f) else None for f in spec['fields']} for r in rows]
    if errors:raise ValueError('\n'.join(errors))
    parts=[];history=[];orders=[];pids=set();keys=set();duplicate_count=0
    def err(table,i,e):
        if len(errors)<40:errors.append(f'{table}, data row {i+1}: {e}')
    def ident(v,name):
        s=str(v or '').strip()
        if not s:raise ValueError(f'{name} is blank')
        if len(s)>120:raise ValueError(f'{name} exceeds 120 characters')
        return s
    for i,r in enumerate(loaded['parts']):
        try:
            pid=ident(r['part_id'],'part_id')
            if pid in pids:raise ValueError(f'duplicate part_id {pid}')
            cost=num(r['unit_cost'],True);lt=num(r['lead_time_days'],True)*(7 if lead_unit=='weeks' else 1)
            if cost<=0 or not 0<lt<=730:raise ValueError('unit cost must be >0; lead time must be 1–730 days')
            pids.add(pid);parts.append({**r,'part_id':pid,'unit_cost':cost,'lead_time_days':lt,
              'description':str(r.get('description') or pid),'family':str(r.get('family') or 'Unspecified'),
              'criticality':str(r.get('criticality') or 'Unspecified'),'supplier_id':str(r.get('supplier_id') or 'Unspecified')})
        except ValueError as e:err('parts',i,e)
    for i,r in enumerate(loaded['history']):
        try:
            r['part_id']=ident(r['part_id'],'part_id');r['site_id']=ident(r['site_id'],'site_id')
            if r['part_id'] not in pids:raise ValueError('part_id is missing from parts master')
            r['week']=parsedate(r['week'],date_format,True)
            key=(r['site_id'],r['part_id'],r['week'])
            if key in keys:duplicate_count+=1;raise ValueError(f'duplicate site–part–week {key}')
            keys.add(key)
            for f in ('demand','on_hand','backorders','blocked_stock','baseline_forecast','adjusted_forecast'):r[f]=num(r[f],f=='demand')
            history.append(r)
        except ValueError as e:err('history',i,e)
    for i,r in enumerate(loaded['orders']):
        try:
            r['part_id']=ident(r['part_id'],'part_id')
            if r['part_id'] not in pids:raise ValueError('part_id is missing from parts master')
            for f in ('order_date','promised_date','receipt_date'):r[f]=parsedate(r[f],date_format,f=='order_date')
            if r['receipt_date'] and r['receipt_date']<r['order_date']:raise ValueError('receipt precedes order date')
            for f in ('quantity','received_quantity'):r[f]=num(r[f])
            for f in ('site_id','supplier_id','po_id'):r[f]=str(r.get(f) or '').strip()
            orders.append(r)
        except ValueError as e:err('orders',i,e)
    if not parts or not history:errors.append('Nonempty parts and history tables are required.')
    if errors:raise ValueError('Import rejected; existing data was not changed.\n'+'\n'.join(errors))
    groups=defaultdict(list)
    for r in history:groups[(r['site_id'],r['part_id'])].append(r['week'])
    gaps=0;irregular=0;short=0
    for k,dates in groups.items():
        dates.sort();ds=[date.fromisoformat(x) for x in dates];diff=[(b-a).days for a,b in zip(ds,ds[1:])]
        if any(x%7 for x in diff):irregular+=1
        if any(x>7 for x in diff):gaps+=1
        if len(dates)<94:short+=1
    absent={f:sum(r[f] is None for r in history) for f in ('on_hand','backorders','blocked_stock','baseline_forecast','adjusted_forecast')}
    warnings=[]
    if gaps or irregular:warnings.append(f'{gaps} series have missing weeks; {irregular} have irregular dates. Evaluation requires a common uninterrupted weekly history.')
    if short:warnings.append(f'{short} series have fewer than 94 weeks. The evaluation protocol requires 156 weekly observations per series.')
    if not orders:warnings.append('No purchase orders imported. Policies use nominal part lead times and an empty initial pipeline assumption.')
    if absent['on_hand']:warnings.append('Some on-hand snapshots are missing. Evaluation requires a starting inventory snapshot for every series.')
    blocked=sum(1 for r in history if r['on_hand'] is not None and (r['blocked_stock'] or 0)>r['on_hand'])
    if blocked:warnings.append(f'{blocked} rows have blocked stock above on-hand. Usable on-hand is floored at zero under the declared blocked-stock assumption.')
    if source_kind=='demo':warnings.insert(0,'Independent demonstration data. This is NOT the Kaggle publisher dataset and is not empirical evidence from it.')
    else:warnings.insert(0,'Source provenance is user-declared. File hashes establish the imported bytes, not independent publisher authentication.')
    did=uuid.uuid4().hex[:12]
    meta=dict(id=did,title=(title or SOURCE_TITLE)[:180],source_kind=source_kind,synthetic=True if source_kind in ('demo','kaggle') else None,
      source_url=SOURCE_URL if source_kind=='kaggle' else None,source_author='Roberto Carlos TIENTCHEU' if source_kind=='kaggle' else 'AeroPlan demonstration generator' if source_kind=='demo' else 'User supplied',
      license='MIT (publisher data card)' if source_kind=='kaggle' else 'MIT' if source_kind=='demo' else 'Not specified; user must verify',
      imported_at=now(),parts=len(parts),history_rows=len(history),series=len(groups),sites=len({x[0] for x in groups}),
      purchase_orders=len(orders),quality_incidents=len(loaded['quality']),start=min(r['week'] for r in history),end=max(r['week'] for r in history),
      missing_week_series=gaps,irregular_week_series=irregular,missing_fields=absent,warnings=warnings,
      file_hashes={n:v['sha256'] for n,v in manifest['files'].items()},original_hashes=manifest['original_hashes'],mapping=mapping,lead_time_unit=lead_unit,date_format=date_format)
    dest=store.root/'datasets'/did;dest.mkdir(parents=True)
    with zipfile.ZipFile(dest/'source_csvs.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in manifest['files']:z.write(folder/n,arcname=n)
        z.writestr('provenance.json',json.dumps(meta,indent=2))
    store.save_dataset(meta,parts,history,orders,loaded['quality'])
    return meta
