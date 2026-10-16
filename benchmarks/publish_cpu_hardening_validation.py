#!/usr/bin/env python3
"""Publish aggregate Phase 4S correctness/build evidence without private arrays."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.input_dir
    def load(name):return json.loads((raw/name).read_text())
    initial=load('initial.json');lock=json.loads((ROOT/'repos.lock.json').read_text())
    protected={name:digest(ROOT/name)==expected for name,expected in initial['protected'].items()}
    numerics={name:digest(ROOT/'ssc/solarpilot'/name)==expected for name,expected in initial['numerical_sources'].items()}
    patches={name:digest(ROOT/'patches'/(name+'.patch'))==initial['patches']['patches/'+name+'.patch'] for name in ('SolarPILOT','SolTrace')}
    if not all([*protected.values(),*numerics.values(),*patches.values()]):raise ValueError('A protected boundary changed')
    source_changes=subprocess.check_output(['git','-C',str(ROOT/'ssc'),'diff','--name-only',initial['nested']['ssc'],lock['ssc']['patched_sha']],text=True).splitlines()
    if source_changes!=['solarpilot/Flux.cpp']:raise ValueError('SSC change exceeded the intended source scope')
    old=load('old-equivalence.json');new=load('new-equivalence.json');transitions=load('scientific-thread-transitions.json')
    for data in (old,new):
        if data['status']!='passed' or len(data['rows'])!=24:raise ValueError('Incomplete cross-binary comparison')
        if {r['threads'] for r in data['rows']}!={1,12,24}:raise ValueError('Missing numerical count')
        if not all(r['all215_bitwise'] and r['map_details_summary_bitwise'] for r in data['rows']):raise ValueError('Numerical comparison failed')
    if transitions['status']!='passed' or len(transitions['rows'])!=2:raise ValueError('Incomplete transition regression')
    logs=[('tsan-tests.log',3,'100% tests passed, 0 tests failed out of 3'),
          ('asan-tests.log',4,'100% tests passed, 0 tests failed out of 4'),
          ('asan-flat-fixtures.log',1,'100% tests passed, 0 tests failed out of 1'),
          ('native-focused.log',7,'100% tests passed, 0 tests failed out of 7'),
          ('python-thread-tests-pinned.log',7,'Ran 7 tests'),
          ('hardening-tool-tests.log',7,'Ran 7 tests')]
    tests=[]
    for name,count,signature in logs:
        path=raw/name;text=path.read_text()
        if signature not in text or ('Ran ' in signature and not text.rstrip().endswith('OK')):
            raise ValueError('Test evidence incomplete: '+name)
        tests.append({'log_id':name,'tests_passed':count,'log_sha256':digest(path)})
    reconstructed=load('reconstruction.json')
    if not (reconstructed['mailbox_exact'] and reconstructed['bootstrap_passed'] and reconstructed['runtime_sections_byte_identical']):
        raise ValueError('Reconstruction evidence failed')
    for name,entry in lock.items():
        if reconstructed['nested'][name]['head']!=entry['patched_sha'] or not reconstructed['nested'][name]['clean']:
            raise ValueError('Reconstruction pin is not exact')
    result={'phase':'4S','status':'passed','initial_root':initial['root'],
            'measured_integration_root':new['metadata']['commits']['.'],
            'pins':{name:entry['patched_sha'] for name,entry in lock.items()},
            'production_source_changes':source_changes,'protected_files_unchanged':protected,
            'numerical_sources_unchanged':numerics,'unrelated_mailboxes_unchanged':patches,
            'cross_binary':{'old':old,'new':new,'oracle':'Original binary Flat 1T; all optical/map/detail/numeric-summary bytes; private arrays remain ignored'},
            'scientific_thread_transitions':transitions,'test_logs':tests,'clean_reconstruction':reconstructed,
            'sanitizer_builds':load('sanitizer-builds.json'),
            'sanitizers':{'thread':'Clang 18 ThreadSanitizer; halt_on_error=1; three representative native regressions',
                          'memory':'GCC ASan/UBSan with leak detection and halt_on_error; five representative native regressions',
                          'timing_under_sanitizers':False},
            'cuda_code_changed':False,'phase5_started':False,'push_performed':False}
    boundary=raw/'boundary-check.json'
    if boundary.exists():result['remote_boundary_checks']=json.loads(boundary.read_text())
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
