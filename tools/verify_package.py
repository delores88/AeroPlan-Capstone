"""Check shipped file hashes; local workspaces and new files are not deleted or changed."""
from pathlib import Path
import hashlib,sys
root=Path(__file__).resolve().parents[1]
manifest=root/'SHA256SUMS.txt'
if not manifest.exists():
    print('No release manifest found.');sys.exit(1)
failures=[];count=0
for line in manifest.read_text().splitlines():
    digest,name=line.split('  ',1);p=(root/name).resolve()
    if root not in p.parents:failures.append(f'Unsafe manifest path: {name}');continue
    if not p.is_file():failures.append(f'Missing: {name}');continue
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:failures.append(f'Changed: {name}')
    count+=1
if failures:
    print('\n'.join(failures));sys.exit(1)
print(f'PASS: {count} shipped files match the release manifest.')
