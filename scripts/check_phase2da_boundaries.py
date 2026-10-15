#!/usr/bin/env python3
"""Verify protected Phase 2C bytes and the preserved optical oracle."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/'benchmarks/results/phase2da-initial-state.json').read_text())
for name,expected in state['protected_sha256'].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
old=subprocess.check_output(['git','-C',str(ROOT/'ssc'),'show',state['repositories']['ssc']['sha']+':solarpilot/Flux.cpp'],text=True)
new=(ROOT/'ssc/solarpilot/Flux.cpp').read_text()
def oracle(text,name):
    start=text.index('double Flux::'+name+'(')
    end=text.index('\nvoid Flux::fluxDensity(',start)
    body=text[start:end].replace('imagePlaneInterceptLegacy','imagePlaneIntercept')
    body=re.sub(r'SP_PROFILE_(?:SCOPE|NEXT)\([^\n]*\);','',body)
    return re.sub(r'\s+','',body)
a,b=oracle(old,'imagePlaneIntercept'),oracle(new,'imagePlaneInterceptLegacy')
assert a==b,'Legacy intercept or its Hermite callees changed beyond profiling/whitespace'
assert subprocess.check_output(['git','check-ignore','local-cases/example/example-private-project.spt'],cwd=ROOT,text=True).strip()
assert not list((ROOT/'ssc/solarpilot').glob('*ImagePlane*.cu'))
print(json.dumps({'phase2c_protected_files':len(state['protected_sha256']),'oracle_token_sha256':hashlib.sha256(a.encode()).hexdigest(),'oracle_preserved':True,'private_case_ignored':True,'image_plane_cuda_absent':True}))
