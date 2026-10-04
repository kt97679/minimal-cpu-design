#!/usr/bin/env python3
"""
Phase 13: the clock period, which eleven phases assumed was constant.

Fmax was measured once, in phase 1, for two designs, and found a 28% spread
(103 MHz against 74 MHz). Every phase since has compared machines by cycle
count, which is only a proxy for time if the clock period is the same -- and
there is a specific reason to doubt that here. The index register, which is the
central finding of the whole project, puts an adder in the *address* path, and
address-path adders are exactly what costs Fmax.

This measures it. Each machine is wrapped with a memory, synthesised for an
iCE40 HX8K and placed and routed with nextpnr across several seeds; the figure
reported is the best of those seeds, which is what the tool's own documentation
recommends treating as the achievable frequency.

What matters is not the absolute numbers -- an FPGA is not the gate-built model
the rest of the project uses -- but the *ratios* between machines, and whether
cycle count has been a safe proxy for wall-clock time.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ROOT, BUILD

SEEDS = (1, 2, 3)

TOP = """
module top(input wire clk, input wire rst, output wire [15:0] probe);
    wire [7:0] a; wire we; wire [15:0] wd, rd; wire ifq;
    reg [15:0] mem [0:255];
    reg [15:0] dout;
    always @(posedge clk) begin
        if (we) mem[a] <= wd;
        dout <= mem[a];
    end
    assign rd = dout;
    gcpu #(.AW(8)) u (.clk(clk), .rst(rst), .maddr(a), .mwe(we), .mdout(wd),
                      .mdin(rd), .ifetch(ifq));
    assign probe = rd;
endmodule
"""


def fmax(name, verilog):
    """Synthesise, place and route; return the best Fmax over the seeds."""
    src = f'{BUILD}/t_{name}.v'
    open(src, 'w').write(verilog + TOP)
    js = f'{BUILD}/t_{name}.json'
    y = subprocess.run(['yosys', '-p',
                        f'read_verilog {src}; synth_ice40 -top top -json {js}'],
                       capture_output=True, text=True)
    if y.returncode:
        return None, None, y.stderr.strip().splitlines()[-1][:90]
    best, lut = 0.0, None
    for s in SEEDS:
        p = subprocess.run(['nextpnr-ice40', '--hx8k', '--package', 'ct256',
                            '--json', js, '--freq', '150', '--seed', str(s)],
                           capture_output=True, text=True)
        f = re.findall(r'Max frequency for clock\s+\S+:\s+([\d.]+)\s*MHz', p.stderr)
        if f:
            best = max(best, float(f[-1]))
        m = re.search(r'ICESTORM_LC:\s+(\d+)/', p.stderr)
        if m:
            lut = int(m.group(1))
    return (best or None), lut, None


def machines():
    """Every family, built through its own generator."""
    import autosearch as A
    import stackmachine as S
    import gp

    out = []

    acc = {
        'a7 no index': ['LD_D', 'ST_D', 'ADD_D', 'SUB_D', 'JZ', 'JN', 'JMP'],
        'a10 phase-4 winner': ['LD_D', 'ST_D', 'ADD_D', 'SUB_D', 'JZ', 'JN',
                               'JMP', 'LDX_D', 'LD_X', 'ST_X'],
        'RSB machine': ['JN', 'JZ', 'LDX_D', 'LD_D', 'LD_X', 'RSB_D', 'RSB_X',
                        'ST_D', 'ST_X', 'XOR_D', 'XOR_X'],
    }
    for n, s in acc.items():
        out.append((n, A.gen_rtl(set(s))))

    st = {'LIT', 'LOAD', 'STORE', 'FETCH', 'STOREI', 'ADD', 'SUB', 'JZ', 'JN', 'JMP'}
    out.append(('stack depth 3', S.gen_rtl(st, 3)))

    ev = gp.Genome([(('^', ('k0',), ('m',)), 'D'),
                    (('|', ('+', ('k0',), ('m',)), ('&', ('kn',), ('k0',))), 'D'),
                    (('+', ('^', ('m',), ('m',)), ('-', ('kn',), ('m',))), 'D'),
                    (('+', ('m',), ('a',)), 'D')])
    gp.core_gates(ev)                       # writes the Verilog as a side effect
    out.append(('evolved, no subtractor', open(f'{BUILD}/gp_tmp.v').read()))
    return out


CYCLES = {'a7 no index': 11013, 'a10 phase-4 winner': 10333,
          'RSB machine': 11669, 'stack depth 3': 11121,
          'evolved, no subtractor': 10515}

if __name__ == '__main__':
    rows = []
    for name, v in machines():
        f, lut, err = fmax(re.sub(r'\W+', '_', name), v)
        rows.append(dict(name=name, fmax=f, lut=lut, err=err,
                         cycles=CYCLES.get(name)))
        print('%-24s %s' % (name, ('%6.1f MHz, %4s LCs' % (f, lut)) if f else
                            'FAILED: %s' % err), flush=True)
    base = next(r for r in rows if r['name'] == 'a10 phase-4 winner')
    print()
    print('%-24s %-9s %-8s %-11s %s' %
          ('machine', 'Fmax', 'cycles', 'wall-clock', 'vs phase-4 winner'))
    for r in rows:
        if not r['fmax'] or not r['cycles']:
            continue
        t = r['cycles'] / (r['fmax'] * 1e6) * 1e6
        tb = base['cycles'] / (base['fmax'] * 1e6) * 1e6
        print('%-24s %7.1f   %7d   %7.2f us   %+6.1f%%  (cycles alone: %+.1f%%)' %
              (r['name'], r['fmax'], r['cycles'], t, 100 * (t / tb - 1),
               100 * (r['cycles'] / base['cycles'] - 1)))
    json.dump(rows, open(f'{BUILD}/timing.json', 'w'), indent=1)
