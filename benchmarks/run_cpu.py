#!/usr/bin/env python3
import argparse
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
              'threads': 1, 'repos': {}, 'cases': {}}
    for name in ['SolarPILOT', 'ssc', 'SolTrace']:
        report['repos'][name] = subprocess.check_output(['git', '-C', str(ROOT / name), 'rev-parse', 'HEAD'], text=True).strip()
    for size in SIZES if args.case == 'all' else [args.case]:
        result, timings = run_case(size, args.repeats, not args.skip_generation)
        report['cases'][size] = {'heliostats': result['heliostats'], 'metrics': result['metrics'], **timings}
        print(size, json.dumps(report['cases'][size]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
