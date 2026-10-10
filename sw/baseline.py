#!/usr/bin/env python3
"""
Recompute the figures the articles publish, and compare them against a recorded
baseline.

Added after prompt 09 asked the question the project had no answer to: about
forty numbers are published across two articles and nothing checked that they
still come out. A change to the benchmark, the assembler or the synthesis script
would move them silently, and the articles would keep the old ones.

Two classes of figure, kept apart because they fail differently:

  STRICT   gate counts, cycle counts, word counts. These depend on the code and
           on the synthesis tool. Compared exactly; any change is a finding
           until a sentence says otherwise.
  REPORTED Fmax, wall-clock. These depend on the place-and-route tool, the seed
           and the machine's load. Recorded with the tool version, printed for
           comparison by eye, never failed on.

Usage:  python3 sw/baseline.py            compare against BASELINE.txt
        python3 sw/baseline.py --record   rewrite BASELINE.txt
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
BASE = os.path.join(ROOT, 'BASELINE.txt')


def tool_versions():
    out = {}
    for name, cmd in (('yosys', ['yosys', '-V']),
                      ('iverilog', ['iverilog', '-V']),
                      ('nextpnr', ['nextpnr-ice40', '--version'])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out[name] = (r.stdout + r.stderr).strip().split('\n')[0][:60]
        except Exception as e:
            out[name] = 'absent (%s)' % type(e).__name__
    out['python'] = sys.version.split()[0]
    return out


def strict():
    """Figures that must reproduce exactly."""
    import suite, sweep, autosearch as A, firmware as F
    v = {}

    g = suite.golden()
    v['suite.outputs'] = len(g)
    v['suite.checksum'] = sum(g) & 0xFFFF
    v['suite.virtual_ops'] = len([o for o in suite.suite() if o[0] != 'label'])

    fg = F.golden2()
    v['firmware.outputs'] = len(fg)
    v['firmware.checksum'] = sum(fg) & 0xFFFF
    v['firmware.virtual_ops'] = len([o for o in F.suite2() if o[0] != 'label'])
    v['firmware.inlined_ops'] = len([o for o in F.inline_calls(F.suite2())
                                     if o[0] != 'label'])

    v['ram.136_words'] = sweep.ram_cost(136)
    v['ram.gates_per_word'] = round(sweep.ram_cost(136) / 136)

    sets = {
        'core.a10': ['LD_D','ST_D','ADD_D','SUB_D','JZ','JN','JMP','LDX_D','LD_X','ST_X'],
        'core.a7':  ['LD_D','ST_D','ADD_D','SUB_D','JZ','JN','JMP'],
        'core.rsb': ['JN','JZ','LDX_D','LD_D','LD_X','RSB_D','RSB_X','ST_D','ST_X',
                     'XOR_D','XOR_X'],
    }
    for k, s in sets.items():
        v[k] = A.core_gates(set(s))

    # the cheapest storage element, phase 16: a register file does not need
    # edge-triggered cells
    import subprocess as sp, re as re2
    lv = """module m (input wire [4:0] addr, input wire we, input wire [15:0] din,
        output wire [15:0] dout);
        reg [15:0] mem [0:22];
        integer i;
        always @* begin
          for (i=0;i<23;i=i+1) if (we && addr==i[4:0]) mem[i] = din;
        end
        assign dout = mem[addr];
    endmodule
"""
    from sweep import BUILD as _B
    open(f'{_B}/bl_latch.v','w').write(lv)
    o = sp.run(['yosys','-p', f'read_verilog {_B}/bl_latch.v\n hierarchy -top m\n'
                ' flatten\n proc; opt; memory; opt\n techmap; opt -full\n'
                ' dfflegalize -cell $_DLATCH_P_ 0\n abc -g NAND\n opt_clean\n stat'],
               capture_output=True, text=True).stdout
    tl = o[o.rfind('Printing statistics'):]
    gg = lambda c: (int(re2.search(rf'\$_{c}_\s+(\d+)', tl).group(1))
                    if re2.search(rf'\$_{c}_\s+(\d+)', tl) else 0)
    v['latch.23_words'] = gg('NAND') + gg('NOT') + 4 * gg('DLATCH_P')
    v['latch.gates_per_word'] = round(v['latch.23_words'] / 23)

    # фаза 10: прошивочная нагрузка, две машины
    import emit as _e, firmware as _f
    _p, _g = _f.suite2(), _f.golden2()
    _cs = ['LD_D','ST_D','LDX_D','LD_X','ST_X','RSB_D','XOR_D','JZ','JN','JMP','CALL','RET']
    for _nm, _is, _pr in (('call', _cs, _p),
                          ('inline', [i for i in _cs if i not in ('CALL','RET')],
                           _f.inline_calls(_p))):
        _r = _e.measure(_is, prog=_pr, gold=_g, key='bl_%s' % _nm)
        assert _r['ok'], 'firmware %s does not match the reference' % _nm
        v['firmware.%s' % _nm] = _r['total']
        v['firmware.%s_words' % _nm] = _r['code']

    import hybrid
    image = [(i * 2654435761) & 0xFFFF for i in range(247)]
    for n in (0, 5):
        v['hybrid.overlay_%d' % n] = hybrid.measure(n, 247, 23, image, 'bl%d' % n)
    return v


def reported():
    """Figures that depend on the machine, recorded but never failed on."""
    out = {}
    tj = os.path.join(ROOT, 'build', 'timing.json')
    if os.path.exists(tj):
        for k, r in json.load(open(tj)).items():
            out['fmax.' + k] = '%.1f MHz (sd %.1f, n=%d)' % (r['mean'], r['sd'], r['n'])
    return out


def render(s, r, tv):
    L = ['# Recorded baseline. STRICT figures are compared exactly; a change is a',
         '# finding until a sentence here explains it. REPORTED figures depend on',
         '# the machine and are printed for comparison by eye, never failed on.',
         '',
         '[tools]']
    for k in sorted(tv):
        L.append('%-28s %s' % (k, tv[k]))
    L += ['', '[strict]']
    for k in sorted(s):
        L.append('%-28s %s' % (k, s[k]))
    if r:
        L += ['', '[reported]']
        for k in sorted(r):
            L.append('%-28s %s' % (k, r[k]))
    return '\n'.join(L) + '\n'


def parse(path):
    sec, out = None, {}
    for line in open(path):
        line = line.split('#')[0].rstrip()
        if not line.strip():
            continue
        if line.startswith('['):
            sec = line.strip('[]'); continue
        k, _, val = line.partition(' ')
        out.setdefault(sec, {})[k] = val.strip()
    return out


if __name__ == '__main__':
    tv = tool_versions()
    s, r = strict(), reported()
    if '--record' in sys.argv or not os.path.exists(BASE):
        open(BASE, 'w').write(render(s, r, tv))
        print('recorded %d strict and %d reported figures to BASELINE.txt'
              % (len(s), len(r)))
        sys.exit(0)
    old = parse(BASE)
    bad = []
    for k in sorted(set(s) | set(old.get('strict', {}))):
        was, now = old.get('strict', {}).get(k), s.get(k)
        if was is None:
            print('NEW     %-28s %s' % (k, now)); continue
        if now is None:
            bad.append((k, was, 'MISSING')); continue
        if str(now) != str(was):
            bad.append((k, was, now))
    for k in sorted(r):
        was = old.get('reported', {}).get(k, '-')
        print('report  %-28s was %-28s now %s' % (k, was, r[k]))
    if old.get('tools') != {k: tv[k] for k in tv if k in old.get('tools', {})}:
        print()
        for k in sorted(tv):
            if old.get('tools', {}).get(k) != tv[k]:
                print('tool    %-28s was %-28s now %s'
                      % (k, old.get('tools', {}).get(k, '-'), tv[k]))
    print()
    if bad:
        print('%d STRICT FIGURE(S) CHANGED -- each needs a sentence before '
              'the baseline is updated:' % len(bad))
        for k, was, now in bad:
            print('  %-28s was %-12s now %s' % (k, was, now))
        sys.exit(1)
    print('all %d strict figures reproduce' % len(s))
