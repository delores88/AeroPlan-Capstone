"""Recompute an AeroPlan evidence ZIP in a new local folder and compare numerical results.
Usage: python tools/reproduce.py evidence.zip --output reproduced
The publisher data is not fetched. Uses only canonical CSV inputs in the evidence ZIP.
"""
from pathlib import Path
import argparse,base64,json,sys,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.store import Store
from app.ingest import stage_files,commit_import
from app.engine import run_experiment

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evidence',type=Path);p.add_argument('--output',type=Path,default=Path('reproduced'));a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):p.error('Use a new or empty output folder; existing work will not be overwritten.')
    with zipfile.ZipFile(a.evidence) as z:
        if sum(i.file_size for i in z.infolist())>300*1024*1024:p.error('Evidence expands beyond the 300 MB reproduction safety limit.')
        original=json.loads(z.read('run.json'))
        files=[{'name':Path(n).name,'content':base64.b64encode(z.read(n)).decode()} for n in z.namelist() if n.startswith('inputs/') and n.endswith('.csv') and z.getinfo(n).file_size]
    st=Store(a.output);preview=stage_files(st,files);kind='demo' if original['result']['dataset']['source_kind']=='demo' else 'local'
    commit_import(st,preview['id'],preview['suggested_mapping'],'Reproduced evidence inputs',kind)
    result=run_experiment(st.load(),original['result']['config'])
    old=original['result'];checks={
        'baseline_portfolio':result['summary']['baseline']==old['summary']['baseline'],
        'selected_policy_portfolio':result['summary']['optimized']==old['summary']['optimized'],
        'forecast_metrics':result['model_summary']==old['model_summary'],
        'selected_models_buffers':[(x['site_id'],x['part_id'],x['model'],x['buffer_z']) for x in result['series']]==[(x['site_id'],x['part_id'],x['model'],x['buffer_z']) for x in old['series']],
        'bootstrap':result['bootstrap']==old['bootstrap']}
    (a.output/'reproduced_result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    (a.output/'comparison.json').write_text(json.dumps({'original_run':original['id'],'checks':checks,'note':'IDs, timestamps, source declaration, scope/exclusion metadata are intentionally not compared; the export includes evaluated-scope inputs.'},indent=2),encoding='utf-8')
    for name,ok in checks.items():print(('PASS' if ok else 'DIFFERENT')+': '+name)
    return 0 if all(checks.values()) else 1
if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,KeyError,zipfile.BadZipFile) as e:print('Reproduction failed:',e,file=sys.stderr);sys.exit(1)
