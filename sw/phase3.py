#!/usr/bin/env python3
"""
Phase 3 driver: for every design point, simulate the RTL running the five
program suite, synthesise the core to NAND gates, price the program store, and
score on gates x time.

Program store is priced two ways:
  all-RAM   every word in writable gate-built RAM (~196 gates/word)
  ROM+RAM   code in a synthesised ROM, data in RAM -- only legal for machines
            that do not need self-modifying code, i.e. those with an index
            register. That eligibility is itself an ISA property, so it is
            reported rather than assumed.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ROOT, BUILD, aw, yosys_nand, ram_cost, write_rom, harvard_cost
import suite as _suite
_suite.POOLING = False        # phase 3: one word per variable
from suite import DESIGNS, build, MASK

SRC = {'sq': ['subleq_cpu.v', 'comp_subleq.v'], 'acc': ['cpu_acc.v'],
       'move': ['cpu_move.v']}


def hexfile(mem, path):
    with open(path, 'w') as f:
        for w in mem:
            f.write('%04x\n' % (w & MASK))


def run_rtl(key, n, defs, nout):
    exe = f'/tmp/p3_{key}'
    fam = {'sq': 'sq', 'move': 'move'}.get(key, 'acc')
    flag = {'sq': '-DDUT_SUBLEQ', 'move': '-DDUT_MOVE', 'acc': '-DDUT_ACC'}[fam]
    cmd = (['iverilog', '-g2012', '-o', exe, flag,
            f'-DNWORDS={n}', f'-DAWIDTH={aw(n)}', f'-DNOUT={nout}',
            f'-DHEXFILE="{BUILD}/p3_{key}.hex"'] +
           ['-D' + d for d in defs] +
           [f'{ROOT}/rtl/tb_sweep.v', f'{ROOT}/rtl/ramg.v'] +
           [f'{ROOT}/rtl/{f}' for f in SRC[fam]])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    out = subprocess.run([exe], capture_output=True, text=True, cwd=ROOT).stdout
    m = re.search(r'RESULT cycles=(\d+) outputs=\d+ errors=(\d+)', out)
    if not m:
        raise RuntimeError(f'{key}: {out.strip()}')
    return int(m.group(1)), int(m.group(2))


def core_cost(d, n):
    key, defs = d['key'], d['defs']
    if key == 'sq':
        rd = (f'read_verilog {ROOT}/rtl/subleq_cpu.v {ROOT}/rtl/comp_subleq.v\n'
              f' chparam -set N {n} -set AW {aw(n)} comp_subleq\n')
        top = 'comp_subleq'
    elif key == 'move':
        rd = (f'read_verilog {ROOT}/rtl/cpu_move.v\n'
              f' chparam -set AW {aw(n)} comp_move\n')
        top = 'comp_move'
    else:
        flags = ' '.join('-D' + x for x in defs)
        rd = (f'read_verilog {flags} {ROOT}/rtl/cpu_acc.v\n'
              f' chparam -set N {n} -set AW {aw(n)} comp_acc\n')
        top = 'comp_acc'
    nand, dff = yosys_nand(rd, top)
    return nand + 6 * dff, dff


def main():
    res, gold = build()
    nout = len(gold)
    with open(f'{BUILD}/expected.txt', 'w') as f:
        for v in gold:
            f.write('%04x\n' % v)

    rows = []
    ramcache = {}
    for d in DESIGNS:
        k = d['key']
        r = res[k]
        n, ncode = r['n'], r['ncode']
        hexfile(r['mem'], f'{BUILD}/p3_{k}.hex')

        cyc, errs = run_rtl(k, n, d['defs'], nout)
        assert errs == 0, f'{k}: {errs} output mismatches in RTL'
        assert abs(cyc - r['cycles']) <= 2, (k, cyc, r['cycles'])

        core, dff = core_cost(d, n)
        if n not in ramcache:
            ramcache[n] = ram_cost(n)
        allram = core + ramcache[n]

        if r['selfmod']:
            harvard = None                      # code must stay writable
        else:
            write_rom(f'p3_{k}', r['mem'][:ncode], aw(n))
            harvard = core + harvard_cost(f'p3_{k}', ncode, n - ncode, aw(n))

        best = allram if harvard is None else harvard
        rows.append(dict(key=k, label=r['label'], nops=r['nops'], words=n,
                         code=ncode, core=core, dff=dff, ram=ramcache[n],
                         allram=allram, harvard=harvard, best=best,
                         cycles=cyc, instrs=r['instrs'], selfmod=r['selfmod'],
                         at=best * cyc / 1e6))

    json.dump(rows, open(f'{BUILD}/phase3.json', 'w'), indent=1)
    print(f'suite verified in RTL on all {len(rows)} designs, '
          f'{nout} outputs each\n')
    print('%-24s %4s %6s %7s %8s %8s %8s %8s %8s' %
          ('design', 'ops', 'words', 'core', 'all-RAM', 'ROM+RAM',
           'best', 'cycles', 'gate-Mcy'))
    for r in rows:
        h = '%8d' % r['harvard'] if r['harvard'] is not None else '     n/a'
        print('%-24s %4d %6d %7d %8d %s %8d %8d %8.1f' %
              (r['label'], r['nops'], r['words'], r['core'], r['allram'], h,
               r['best'], r['cycles'], r['at']))
    print('\nn/a = needs self-modifying code, so its program cannot live in ROM')


if __name__ == '__main__':
    main()
