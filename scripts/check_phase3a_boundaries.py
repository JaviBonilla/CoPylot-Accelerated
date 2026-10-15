#!/usr/bin/env python3
"""Prove Phase 3A leaves numerical sources, pins and Phase 2D-C evidence unchanged."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/'benchmarks/results/phase3a-initial-state.json').read_text())
for name,expected in state['protected_sha256'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Historical evidence changed: '+name)
for name in ['ssc','SolarPILOT','SolTrace']:
    run=lambda *args:subprocess.check_output(['git','-C',str(ROOT/name),*args],text=True).strip()
    if run('rev-parse','HEAD')!=state['repositories'][name]['sha']:raise RuntimeError('Nested pin changed: '+name)
    if run('status','--porcelain'):raise RuntimeError('Nested repository is not clean: '+name)
if subprocess.check_output(['git','-C',str(ROOT),'ls-files','local-cases'],text=True).strip():
    raise RuntimeError('Local research assets must remain untracked')
print(json.dumps({'historical_files_unchanged':len(state['protected_sha256']),'nested_heads_and_sources_unchanged':True,
    'patches_and_pins_unchanged':True,'local_research_assets_untracked':True,'no_core_changes':True},indent=2))
