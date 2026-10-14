#!/usr/bin/env python3
import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path
from cases import ROOT, SIZES, run_case


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=[*SIZES, 'all'], default='all')
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--skip-generation', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT / 'artifacts/cpu-times.json')
    args = p.parse_args()
    report = {'platform': platform.platform(), 'python': platform.python_version(),
              'cpu': Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].strip(': \t'),
              'threads': 1, 'repos': {}, 'dirty_tracked_sources': {}, 'source_sha256': {}, 'cases': {}}
    for name in ['SolarPILOT', 'ssc', 'SolTrace']:
        report['repos'][name] = subprocess.check_output(['git', '-C', str(ROOT / name), 'rev-parse', 'HEAD'], text=True).strip()
        report['dirty_tracked_sources'][name] = bool(subprocess.check_output(
            ['git', '-C', str(ROOT / name), 'status', '--porcelain', '--untracked-files=no'], text=True).strip())
    files = [ROOT / 'CMakeLists.txt', ROOT / 'benchmarks/cases.py', ROOT / 'SolarPILOT/deploy/api/copylot.py']
    for directory in ['ssc/solarpilot', 'SolTrace/coretrace']:
        files += sorted(p for p in (ROOT / directory).iterdir() if p.suffix in {'.h', '.hpp', '.cpp', '.cu'} or p.name == 'CMakeLists.txt')
    report['source_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}

    for size in SIZES if args.case == 'all' else [args.case]:
        result, timings = run_case(size, args.repeats, not args.skip_generation)
        report['cases'][size] = {'heliostats': result['heliostats'], 'metrics': result['metrics'], 'parameters': result['parameters'],
            'layout_sha256': result['layout_sha256'], 'weather_sha256': result['weather_sha256'], **timings}
        print(size, json.dumps(report['cases'][size]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
