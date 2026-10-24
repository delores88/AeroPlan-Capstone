"""Recompute a complete AeroPlan run export without relying on its live workspace."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.ingest import stage_files,commit_import
from app.store import Store
from app.runner import run_configured

def replay(path):
    with zipfile.ZipFile(path) as archive:
        for line in archive.read('SHA256SUMS.txt').decode().splitlines():
            digest,name=line.split('  ',1)
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:
                raise ValueError('Export checksum mismatch: '+name)
        original=json.loads(archive.read('result.json'))
        inputs=archive.read('inputs.zip')
    with zipfile.ZipFile(io.BytesIO(inputs)) as source:
        provenance=json.loads(source.read('provenance.json'))
    with tempfile.TemporaryDirectory(prefix='aeroplan-replay-') as folder:
        store=Store(Path(folder))
        stage=stage_files(store,[dict(name='inputs.zip',content=base64.b64encode(inputs).decode())])
        commit_import(store,stage['id'],provenance['mapping'],provenance['title'],provenance['source_kind'],provenance['lead_time_unit'],provenance['date_format'])
        result=run_configured(store.load(),original['config'])
    if result['summary']!=original['result']['summary']:
        raise ValueError('Replay differs from exported summary. Check recorded runtime versions and source.')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export',type=Path)
    parser.add_argument('--output',type=Path,default=Path('replay.json'))
    args=parser.parse_args()
    result=replay(args.export)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print('Replay matches exported summary:',args.output.resolve())
