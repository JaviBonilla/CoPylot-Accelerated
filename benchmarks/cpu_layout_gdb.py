"""GDB Python observer: read registers only; raw addresses stay in ignored output."""
import gdb
import json
import os
import hashlib

config=json.load(open(os.environ['PHASE4S_GDB_CONFIG']))
with open(os.path.join(os.environ['COPILOT_LIB_DIR'],'solarpilot.so'),'rb') as file:
    if hashlib.sha256(file.read()).hexdigest()!=config['library_sha256']:
        raise RuntimeError('Debugger offsets do not match the selected binary')
output=os.environ['PHASE4S_GDB_OUTPUT'];records=[];current=None;breakpoints=[]


def save():
    with open(output,'w') as file:json.dump({'library_sha256':config['library_sha256'],'records':records},file,indent=2)


class ReadBreakpoint(gdb.Breakpoint):
    def __init__(self,address,kind):
        super().__init__('*'+hex(address),internal=True);self.kind=kind
    def stop(self):
        global current
        if self.kind=='parameters':
            current['flat_frame_rsp']=int(gdb.parse_and_eval('$rsp'))
            current['parameters_address']=int(gdb.parse_and_eval(config['parameters_expression']))
        elif self.kind=='worker':
            current['worker_parameters_address']=int(gdb.parse_and_eval(config['worker_parameters_expression']))
        else:
            current['sincos_output_addresses']=[int(gdb.parse_and_eval('$rsi')),int(gdb.parse_and_eval('$rdi'))]
        self.enabled=False;save();return False


class ApiBreakpoint(gdb.Breakpoint):
    def stop(self):
        global current,breakpoints
        current={'c_api_callsite_mod64':(int(gdb.parse_and_eval('$rsp'))+8)%64}
        records.append(current)
        if not breakpoints:
            base=int(gdb.parse_and_eval('(void*)&sp_simulate'))-config['sp_simulate_offset']
            breakpoints=[ReadBreakpoint(base+config['parameters_ready_offset'],'parameters'),
                         ReadBreakpoint(base+config['worker_parameters_ready_offset'],'worker'),
                         ReadBreakpoint(base+config['sincos_call_offset'],'scratch')]
        for bp in breakpoints:bp.enabled=True
        save();return False


gdb.execute('set breakpoint pending on')
gdb.execute('set print thread-events off')
gdb.execute('set disable-randomization off')
ApiBreakpoint('sp_simulate',internal=True)
