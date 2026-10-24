"""Read-only result views and complete, reproducible exports."""
from __future__ import annotations
import hashlib
import io
import json
import zipfile
from .reports import csv_bytes


def forecast_with_intervals(forecast):
    """Add display bands to old point-only runs without altering saved evidence."""
    if forecast.get('intervals') or not forecast.get('future'):
        return forecast
    from .intervals import prediction_intervals
    history = [row.get('actual') for row in forecast.get('history', [])]
    if not history or any(value is None for value in history):
        return forecast
    bands = prediction_intervals(history, forecast['model'], len(forecast['future']))
    return {**forecast,
            'future': [{**row, **band} for row, band in zip(forecast['future'], bands['future'])],
            'intervals': {**bands['metadata'], 'display_only': True,
                          'source': 'Computed from the saved history; original run bytes are unchanged.'},
            'future_note': 'Point forecasts with nominal empirical prediction intervals for future demand.'}


def filtered(rows, query):
    text = str(query.get('q', [''])[0]).strip().casefold()
    result = []
    for row in rows:
        if any(query.get(field, [''])[0] and row.get(field if field != 'site' else 'site_id') != query[field][0]
               for field in ('site', 'family', 'criticality')):
            continue
        if text and text not in ' '.join(str(v) for v in row.values() if not isinstance(v, (dict, list))).casefold():
            continue
        result.append(row)
    return result


def inventory_rows(result):
    rows = []
    for source in result['series']:
        row = dict(source)
        row.setdefault('key', row['site_id'] + '|' + row['part_id'])
        row.setdefault('buffer_z', row.get('z'))
        row.setdefault('validation_feasible', row.get('feasible'))
        for name in ('baseline', 'selected'):
            metrics = row.get(name, {})
            row.setdefault(name + '_cost', metrics.get('carrying_cost'))
            row.setdefault(name + '_fill', metrics.get('fill_rate'))
        rows.append(row)
    return rows


def result_view(run, query):
    if run['status'] != 'complete':
        raise ValueError('This run has no completed results.')
    r = run['result']
    view = query.get('view', ['summary'])[0]
    if view == 'summary':
        inference = r['inference']
        return dict(run_id=run['id'], summary=r['summary'], inference=inference,
                    absolute_target_met=inference.get('absolute_target_met'),
                    joint_claim=inference.get('joint_improvement_met'),
                    config=run['config'], dataset=r.get('dataset', r['provenance'].get('dataset')),
                    selection=r.get('selection', r.get('diagnostics', {})), provenance=r['provenance'],
                    optimization=r.get('optimization'))
    if view == 'cohorts':
        group = query.get('group', ['site'])[0]
        if group=='site' and 'site_id' in r['cohorts']:group='site_id'
        if group not in r['cohorts']:
            raise ValueError('Unknown cohort grouping.')
        return dict(rows=r['cohorts'][group], group=group, run_id=run['id'])
    if view == 'weekly':
        rows=[]
        for source in r['weekly']:
            row={**source,'week':source.get('date',source.get('week'))}
            for name in ('baseline','selected'):
                row[name+'_fill']=source.get(name,{}).get('fill_rate')
                row[name+'_cost']=source.get(name,{}).get('carrying_cost')
            rows.append(row)
        return dict(rows=rows, run_id=run['id'])
    if view not in ('inventory', 'forecasts'):
        raise ValueError('Unknown results view.')
    if view == 'forecasts' and query.get('key', [''])[0]:
        key = query['key'][0]
        if key not in r['forecasts']:
            raise ValueError('Series not found in this run.')
        detail=next((row for row in r['series'] if row['site_id']+'|'+row['part_id']==key),{})
        return dict(detail,**forecast_with_intervals(r['forecasts'][key]), key=key, run_id=run['id'])
    rows = inventory_rows(r)
    filters = dict(sites=sorted({x['site_id'] for x in rows}),
                   families=sorted({x['family'] for x in rows}),
                   criticalities=sorted({x['criticality'] for x in rows}))
    rows = filtered(rows, query)
    page = max(0, int(query.get('page', ['0'])[0]))
    limit = 50
    return dict(rows=rows[page*limit:(page+1)*limit], total=len(rows), page=page,
                limit=limit, filters=filters, run_id=run['id'])


def source_identity(root):
    paths = [root/'launch.py', root/'requirements.txt']
    paths += sorted((root/'app').glob('*.py'))
    hashes = {str(p.relative_to(root)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths if p.exists()}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return dict(sha256=digest, files=hashes)


def capture_source(root, folder):
    identity = source_identity(root)
    with zipfile.ZipFile(folder/'source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in identity['files']:
            archive.write(root/name, name)
        for path in sorted((root/'tools').glob('*.py')):
            archive.write(path, str(path.relative_to(root)).replace('\\', '/'))
    return identity


def export_run(run, store, query, kind):
    r = run['result']
    if run['status'] != 'complete' or not r:
        raise ValueError('Only completed runs can be exported.')
    if kind == 'json':
        return json.dumps(run, indent=2, allow_nan=False).encode(), 'application/json'
    if kind == 'csv':
        return csv_bytes(filtered(inventory_rows(r), query)), 'text/csv; charset=utf-8'
    if kind == 'cohorts':
        rows = result_view(run, {**query, 'view': ['cohorts']})['rows']
        return csv_bytes(rows), 'text/csv; charset=utf-8'
    files = {'result.json': json.dumps(run, indent=2, allow_nan=False).encode(),
             'inventory.csv': csv_bytes(inventory_rows(r)),
             'policies.csv': csv_bytes(r['policies']),
             'replications.csv': csv_bytes(r['replications']),
             'weekly.csv': csv_bytes(r['weekly'])}
    for name, rows in r['cohorts'].items():
        files[f'cohorts/{name}.csv'] = csv_bytes(rows)
    run_folder = store.root/'runs'/run['id']
    for name in ('frozen.json', 'source.json', 'source.zip'):
        path = run_folder/name
        if path.exists():
            files[name] = path.read_bytes()
    inputs = store.root/'datasets'/run['dataset']/'source_csvs.zip'
    files['inputs.zip'] = inputs.read_bytes()
    files['README.txt'] = (
        'AeroPlan run export\n\nRun ID: ' + run['id'] + '\n'
        'Results and all 1,800 series (when the full dataset is used) belong to this run only.\n'
        'Cost values use source cost units; currency is unspecified.\n'
        'Immediate fill counts only current demand filled on arrival.\n'
        'Selected policies and configuration were saved before evaluation in frozen.json.\n'
        'source.zip contains the executable Python source captured at run start.\n'
        'inputs.zip contains the raw CSV bytes and import mappings in provenance.json.\n'
        'To reproduce: extract source.zip, install requirements.txt, then run\n'
        'python tools/replay_export.py <path-to-this-export.zip> --output replay.json\n'
        'The fixed test period has previously been examined; subsequent tuning is exploratory.\n'
    ).encode()
    files['SHA256SUMS.txt'] = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n'
                                     for name, data in sorted(files.items())).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue(), 'application/zip'
