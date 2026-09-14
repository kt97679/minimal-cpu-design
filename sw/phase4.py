#!/usr/bin/env python3
"""
Phase 4 driver. Same five-program suite as phase 3, but the program store is
priced three ways so the levers can be separated:

  all-RAM        every word in writable gate-built RAM
  ROM=code       code in ROM, everything else in RAM      (the phase 3 split)
  ROM=code+RO    code AND constants in ROM, only mutable data in RAM, with
                 the data RAM addressed by ceil(log2(NDATA)) bits instead of
                 the full address width

The last two are only available to machines that do not need self-modifying
code. Everything is RTL-verified before it is counted.
"""
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ROOT, BUILD, aw, yosys_nand, ram_cost, write_rom, harvard_cost
from suite import DESIGNS, build, MASK
from phase3 import hexfile, run_rtl, core_cost   # NB: importing phase3 turns
import suite as _suite                           # pooling off, so turn it back
_suite.POOLING = True                            # on -- phase 4 pools variables


def harvard2_cost(key, nro, ndata, awidth, daw):
    """code+constants in ROM, mutable data in a narrowly addressed RAM"""
    nand, dff = yosys_nand(
        f'read_verilog {BUILD}/rom_{key}.v {ROOT}/rtl/memsys2.v {ROOT}/rtl/ramg.v\n'
        f' chparam -set NRO {nro} -set NDATA {ndata} -set AW {awidth}'
        f' -set DAW {daw} memsys2\n', 'memsys2')
    return nand + 6 * dff


def main():
    res, gold = build()
    nout = len(gold)
    with open(f'{BUILD}/expected.txt', 'w') as f:
        for v in gold:
            f.write('%04x\n' % v)

    rows, ramcache = [], {}
    for d in DESIGNS:
        k, r = d['key'], res[d['key']]
        n, ncode, nro = r['n'], r['ncode'], r['nro']
        hexfile(r['mem'], f'{BUILD}/p3_{k}.hex')

        cyc, errs = run_rtl(k, n, d['defs'], nout)
        assert errs == 0, f'{k}: {errs} RTL output mismatches'
        assert abs(cyc - r['cycles']) <= 2, (k, cyc, r['cycles'])

        core, _ = core_cost(d, n)
        if n not in ramcache:
            ramcache[n] = ram_cost(n)
        allram = core + ramcache[n]

        romcode = romro = None
        if not r['selfmod']:
            write_rom(f'p4c_{k}', r['mem'][:ncode], aw(n))
            romcode = core + harvard_cost(f'p4c_{k}', ncode, n - ncode, aw(n))
            ndata = n - nro
            daw = max(1, math.ceil(math.log2(ndata)))
            write_rom(f'p4r_{k}', r['mem'][:nro], aw(n))
            romro = core + harvard2_cost(f'p4r_{k}', nro, ndata, aw(n), daw)

        best = min(x for x in (allram, romcode, romro) if x is not None)
        rows.append(dict(key=k, label=r['label'], nops=r['nops'], words=n,
                         code=ncode, nro=nro, core=core, allram=allram,
                         romcode=romcode, romro=romro, best=best, cycles=cyc,
                         selfmod=r['selfmod'], at=best * cyc / 1e6))

    json.dump(rows, open(f'{BUILD}/phase4.json', 'w'), indent=1)
    f = lambda v: '%9d' % v if v is not None else '      n/a'
    print(f'suite verified in RTL on all {len(rows)} designs, {nout} outputs\n')
    print('%-26s %4s %6s %6s %9s %9s %9s %8s %8s' %
          ('design', 'ops', 'words', 'core', 'all-RAM', 'ROM=code',
           'ROM=cd+RO', 'cycles', 'gate-Mcy'))
    for r in rows:
        print('%-26s %4d %6d %6d %s %s %s %8d %8.1f' %
              (r['label'], r['nops'], r['words'], r['core'], f(r['allram']),
               f(r['romcode']), f(r['romro']), r['cycles'], r['at']))
    print('\nn/a = self-modifying, so no part of the image can be read-only')


if __name__ == '__main__':
    main()
