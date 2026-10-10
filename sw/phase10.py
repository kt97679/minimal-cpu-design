#!/usr/bin/env python3
"""
Phase 10, as a script instead of arithmetic.

The firmware figures were computed during that session without a committed
script, so when the project moved to latch memory in phase 25 they could not be
recomputed -- they were rescaled by hand, exactly, but by hand. This measures
them the way every other number here is measured: compile, verify against the
reference interpreter, synthesise, count.

Three machines on the same firmware workload:

  * twelve instructions with CALL and RETURN;
  * the same set without them, so every subroutine body is spliced in at each
    call site -- the cost CALL exists to save;
  * the stack machine of phase 9, which also gets CALL and RETURN.

Run: python3 sw/phase10.py      (also `make phase10`)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autosearch as A
import emit
import firmware as F
from sweep import BUILD

# the practical set of phase 10: indexing, a checksum instruction, subroutines
CALLSET = ['LD_D', 'ST_D', 'LDX_D', 'LD_X', 'ST_X', 'RSB_D', 'XOR_D',
           'JZ', 'JN', 'JMP', 'CALL', 'RET']
INLINESET = [i for i in CALLSET if i not in ('CALL', 'RET')]


def run(label, iset, prog, gold, key):
    try:
        r = emit.measure(iset, prog=prog, gold=gold, key=key)
    except Exception as e:
        return dict(label=label, error='%s: %s' % (type(e).__name__, e))
    r['label'] = label
    r['nops'] = len(iset)
    return r


def main():
    prog = F.suite2()
    gold = F.golden2()
    inlined = F.inline_calls(prog)
    nv = lambda p: len([o for o in p if o[0] != 'label'])
    print('firmware workload: %d virtual ops with CALL, %d with the bodies '
          'spliced in, %d outputs' % (nv(prog), nv(inlined), len(gold)))
    print()

    rows = [run('with CALL and RETURN', CALLSET, prog, gold, 'p10call'),
            run('calls inlined', INLINESET, inlined, gold, 'p10inline')]

    print('%-24s %4s %6s %6s %8s %8s %8s' %
          ('machine', 'ops', 'words', 'code', 'core', 'memory', 'total'))
    for r in rows:
        if 'error' in r:
            print('%-24s %s' % (r['label'], r['error'])); continue
        assert r['ok'], '%s: outputs do not match the reference' % r['label']
        print('%-24s %4d %6d %6d %8d %8d %8d' %
              (r['label'], r['nops'], r['words'], r['code'], r['core'],
               r['memory'], r['total']))

    good = [r for r in rows if 'error' not in r]
    if len(good) == 2:
        c = next(r for r in good if 'CALL' in r['label'])
        i = next(r for r in good if 'inlined' in r['label'])
        print()
        print('CALL and RETURN remove %d words of program and add %d gates of '
              'core,' % (i['code'] - c['code'], c['core'] - i['core']))
        print('for a net %d gates.' % (i['total'] - c['total']))

    json.dump(good, open(f'{BUILD}/phase10.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
