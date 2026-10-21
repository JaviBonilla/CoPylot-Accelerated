#!/usr/bin/env python3
"""Audit retained Legacy bodies against the pinned upstream source, without editing it."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE='e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec'
FOURS='0fd069b30343a08787f76247c4b1bb637e83bbe0'

def body(source,name):
    # Blank comments and literals for brace location; preserve original body text.
    pattern=r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    masked=re.sub(pattern,lambda m:' '*len(m.group()),source)
    start=masked.index(name+'(');begin=masked.index('{',start);depth=0
    for end in range(begin,len(masked)):
        depth+=(masked[end]=='{')-(masked[end]=='}')
        if depth==0:return source[begin:end+1]
    raise ValueError('Unbalanced function')

def normalized(value):
    value=re.sub(r'//[^\n]*|/\*[\s\S]*?\*/','',value)
    value=re.sub(r'SP_PROFILE_(?:SCOPE|NEXT)\([^;]*\);','',value)
    return re.sub(r'\s+','',value)

def audit():
    git=lambda repo,*args:subprocess.check_output(['git','-C',str(ROOT/repo),*args],text=True).strip()
    current=(ROOT/'ssc/solarpilot/Flux.cpp').read_text();up=git('ssc','show',BASE+':solarpilot/Flux.cpp');checks=[]
    for original,retained in [('imagePlaneIntercept','imagePlaneInterceptLegacy'),('fluxDensity','fluxDensityLegacy'),('hermiteIntEval','hermiteIntEval'),('hermiteIntegralSetup','hermiteIntegralSetup'),('hermiteIntegral','hermiteIntegral')]:
        a=normalized(body(up,'Flux::'+original));b=normalized(body(current,'Flux::'+retained));assert a==b,retained
        checks.append({'upstream_function':original,'retained_function':retained,'normalized_body_sha256':hashlib.sha256(a.encode()).hexdigest(),'body_identical_after_removing_comments_whitespace_profile_macros':True})
    shared=['Flux.cpp','ImagePlaneInterceptAdapter.cpp','SolarField.cpp','interop.cpp','Toolbox.cpp','OpticalMesh.h']
    for file in shared:assert (ROOT/'ssc/solarpilot'/file).read_bytes()==subprocess.check_output(['git','-C',str(ROOT/'ssc'),'show',FOURS+':solarpilot/'+file]),file
    return {'upstream_ssc_base':BASE,'phase4s_ssc':FOURS,'current_root':git('.','rev-parse','HEAD'),
        'current_nested':{n:git(n,'rev-parse','HEAD') for n in ['ssc','SolarPILOT','SolTrace']},'legacy_body_checks':checks,
        'current_and_phase4s_shared_source_files_byte_identical':shared,
        'recommended_label':'retained original/legacy SolarPILOT Hermite execution path (with documented safety and project-restoration fixes)',
        'untouched_historical_upstream_binary_equivalence_demonstrated':False,
        'safety_caveat':'factorial_d formerly converted an overflowing int factorial at 13!; the retained fix computes double factorials. This is not asserted universally numerically neutral to undefined upstream behavior. OpticalMesh pointers/terminal are initialized; SPT/XML error handling and explicit geometry restoration are retained.'}

if __name__=='__main__':print(json.dumps(audit(),indent=2))
