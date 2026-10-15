#!/usr/bin/env python3
"""Check historical evidence, unchanged numerical kernels and physical scope."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/'benchmarks/results/phase2dc-initial-state.json').read_text())
old_ssc=state['repositories']['ssc']['sha'];old_root=state['repositories']['.']['sha']
def previous(repo,sha,path):
    return subprocess.check_output(['git','-C',str(ROOT/repo),'show',sha+':'+path])
protected=[]
for name,expected in state['protected_sha256'].items():
    if name.startswith(('benchmarks/results/','docs/')):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
        protected.append(name)
unchanged=['Flux.cpp','SolarField.cpp','ImagePlaneIntercept.h','ImagePlaneIntercept.cpp',
    'ImagePlaneInterceptAdapter.cpp','ImagePlaneInterceptNumerics.h','FluxDensityNumerics.h']
for name in unchanged:
    assert previous('ssc',old_ssc,'solarpilot/'+name)==(ROOT/'ssc/solarpilot'/name).read_bytes(),name
for name in ['tests/image_plane_fixtures.h','tests/image_plane_benchmark.cpp']:
    assert previous('.',old_root,name)==(ROOT/name).read_bytes(),name
def function(text,signature):
    start=text.index(signature);brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
kernels={}
for file,signatures in {
    'FluxDensityKernels.cu':['__device__ flux_density::HeliostatData load_heliostat(',
        '__global__ void flux_density_kernel(','__global__ void contribution_kernel('],
    'ImagePlaneInterceptKernels.cu':['__global__ void image_plane_kernel(']}.items():
    old=previous('ssc',old_ssc,'solarpilot/'+file).decode();new=(ROOT/'ssc/solarpilot'/file).read_text()
    for signature in signatures:
        a,b=function(old,signature),function(new,signature);assert a==b,signature
        kernels[signature]=hashlib.sha256(a.encode()).hexdigest()
old=previous('ssc',old_ssc,'solarpilot/CoPilot_API.cpp').decode();new=(ROOT/'ssc/solarpilot/CoPilot_API.cpp').read_text()
assert function(old,'SPEXPORT bool sp_simulate(')==function(new,'SPEXPORT bool sp_simulate('),'Public CUDA physical dispatch changed'
lock=json.loads((ROOT/'repos.lock.json').read_text())
for name,initial in state['pins'].items():
    assert lock[name]['sha']==initial['sha'],name
    if name!='ssc':assert lock[name]==initial,name
assert subprocess.run(['git','check-ignore','-q','local-cases/example/example-private-project.spt'],cwd=ROOT).returncode==0
assert not subprocess.check_output(['git','ls-files','local-cases'],cwd=ROOT,text=True).strip()
print(json.dumps({'historical_files_unchanged':len(protected),'unchanged_numerical_and_scope_files':unchanged,
    'kernel_function_sha256':kernels,'public_physical_dispatch_unchanged':True,'upstream_bases_unchanged':True,
    'non_ssc_pins_unchanged':True,'private_cases_ignored_untracked':True},indent=2))
