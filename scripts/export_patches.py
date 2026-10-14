#!/usr/bin/env python3
"""Export local repository commits, preserving separate history for review."""
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
lock_path = ROOT / 'repos.lock.json'
lock = json.loads(lock_path.read_text())
(ROOT / 'patches').mkdir(exist_ok=True)
for name, repo in lock.items():
    data = subprocess.check_output(['git', '-C', str(ROOT / name), 'format-patch', '--stdout', f'{repo["sha"]}..HEAD'])
    (ROOT / 'patches' / f'{name}.patch').write_bytes(data)
    repo['patched_sha'] = subprocess.check_output(['git', '-C', str(ROOT / name), 'rev-parse', 'HEAD'], text=True).strip()
    committers = subprocess.check_output(['git', '-C', str(ROOT / name), 'log',
        '--format=%cn%x09%ce', f'{repo["sha"]}..HEAD'], text=True).splitlines()
    if len(set(committers)) != 1:
        raise RuntimeError('Export needs a single committer identity per repository')
    committer_name, committer_email = committers[0].split('\t')
    repo['patch_committer'] = {'name': committer_name, 'email': committer_email}
lock_path.write_text(json.dumps(lock, indent=2) + '\n')
