#!/usr/bin/env python3
"""Clone exact upstream commits and apply the reviewable local commit series."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=ROOT)
    args = parser.parse_args()
    destination = args.workspace.resolve()
    lock = json.loads((ROOT / 'repos.lock.json').read_text())
    for name, repo in lock.items():
        path = destination / name
        if path.exists():
            # Never reset or rewrite an existing user checkout.
            head = git(path, 'rev-parse', 'HEAD')
            expected = repo.get('patched_sha', repo['sha'])
            if head != expected or git(path, 'status', '--porcelain', '--untracked-files=no'):
                raise RuntimeError(f'{path}: expected clean pinned HEAD {expected}, got {head}; refusing to overwrite')
            print(f'{name}: verified {head}', flush=True)
            continue
        subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', repo['url'], str(path)], check=True)
        # Exact SHA, independent of a moving branch or tag.
        git(path, 'switch', '-c', 'feature/copilot-gpu', repo['sha'])
        patch = ROOT / 'patches' / f'{name}.patch'
        if patch.exists() and patch.stat().st_size:
            # Deterministic committer identity/dates recreate exported commit SHAs.
            identity = repo['patch_committer']
            git(path, '-c', f'user.name={identity["name"]}', '-c', f'user.email={identity["email"]}',
                'am', '--committer-date-is-author-date', str(patch))
        expected = repo.get('patched_sha', repo['sha'])
        if git(path, 'rev-parse', 'HEAD') != expected:
            raise RuntimeError(f'{name}: reconstructed HEAD differs from {expected}')
        print(f'{name}: prepared {git(path, "rev-parse", "HEAD")}', flush=True)


if __name__ == '__main__':
    main()
