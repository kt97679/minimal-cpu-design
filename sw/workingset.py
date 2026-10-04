#!/usr/bin/env python3
"""
Phase 11: aim the search at the working set, where the money actually is.

Phases 7-10 searched instruction sets. The budget says that was the small end:
at the optimum the core is 21% of the machine, the program in ROM is 13%, and
the data RAM is 65%. A perfect core buys at most 21%; a plausible one buys 9%.

The data RAM is 23 words: 16 of array that the benchmark fixes, and 7 program
scalars. Those seven are the only part an architecture can touch, and it can
touch them in one way -- by holding them in registers instead of memory. A
16-bit register costs about 130 gates where a RAM word costs about 200, so each
one moved saves 70 gates directly. The larger effect is on code: an operation
whose operands are *both* in registers collapses from three words to one.

That makes the choice of which variables to pin a subset-selection problem with
real epistasis -- pinning `v0` is worth much more if `v1` is pinned too, because
`add v0,v1` only collapses when both are. Classic genetic-algorithm territory.

Except there are seven scalars, so the space is 2^7 = 128 and can be enumerated
exactly. The honest answer to "would a GA help here" is that for this axis it
would be solving a problem that fits in a loop. The GA earns its place only once
the instruction semantics are evolved too, which is the second half of this file.
"""
import itertools
import json
import os
import re
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite import suite, ARRN
from sweep import ROOT, BUILD
import archsearch as A

G_RAM, G_ROM = 200.0, 4.3
NCONST = 13


def profile():
    """Static and dynamic counts, keeping track of which operands are scalars."""
    prog = suite()
    lab = {o[1]: i for i, o in enumerate(prog) if o[0] == 'label'}
    static, dyn = Counter(), Counter()
    import suite as S
    m, pc, steps = {'ARR': list(S.ARR0)}, 0, 0
    g = lambda n: m.get(n, 0)
    while pc < len(prog) and steps < 10 ** 7:
        o = prog[pc]; pc += 1; steps += 1
        if o[0] == 'label':
            continue
        key = (o[0],) + tuple(x if isinstance(x, str) and x.startswith('v') else None
                              for x in o[1:])
        dyn[key] += 1
        k = o[0]
        if k == 'halt': break
        elif k == 'movi': m[o[1]] = o[2] & 0xFFFF
        elif k == 'mov': m[o[1]] = g(o[2])
        elif k == 'add': m[o[1]] = (g(o[1]) + g(o[2])) & 0xFFFF
        elif k == 'sub': m[o[1]] = (g(o[1]) - g(o[2])) & 0xFFFF
        elif k == 'addi': m[o[1]] = (g(o[1]) + o[2]) & 0xFFFF
        elif k == 'subi': m[o[1]] = (g(o[1]) - o[2]) & 0xFFFF
        elif k == 'jmp': pc = lab[o[1]]
        elif k == 'jz': pc = lab[o[2]] if g(o[1]) == 0 else pc
        elif k == 'jn': pc = lab[o[2]] if S.s16(g(o[1])) < 0 else pc
        elif k == 'ldx': m[o[1]] = m[o[2]][g(o[3])]
        elif k == 'stx': m[o[1]][g(o[2])] = g(o[3])
    for o in prog:
        if o[0] == 'label':
            continue
        static[(o[0],) + tuple(x if isinstance(x, str) and x.startswith('v') else None
                               for x in o[1:])] += 1
    return static, dyn


# words and cycles for one virtual operation, given which operands are pinned.
# A register destination removes the load and the store; a register source
# removes the operand fetch as well.
def shape(op, pin):
    k = op[0]
    d = op[1] if len(op) > 1 and isinstance(op[1], str) else None
    s = op[2] if len(op) > 2 and isinstance(op[2], str) else None
    D, S = (d in pin), (s in pin)
    if k in ('add', 'sub'):
        if D and S: return 1, 1          # OP rD, rS
        if D:       return 1, 2          # OP rD, mem
        if S:       return 3, 5          # LD r0,d ; OP r0,rS ; ST r0,d
        return 3, 6
    if k == 'mov':
        if D and S: return 1, 1
        if D:       return 1, 2
        if S:       return 1, 2
        return 2, 4
    if k in ('movi', 'addi', 'subi'):
        return (2, 3) if D else (3, 6)
    if k == 'out':
        return (1, 2) if D else (2, 4)
    if k in ('jz', 'jn'):
        return (1, 1) if D else (2, 3)
    if k == 'jmp':   return 1, 1
    if k == 'ldx':   return 3, 6
    if k == 'stx':   return 3, 6
    return 1, 1


_core = {}


def core_gates(R):
    """Synthesise a machine with R registers and an index register."""
    if R in _core:
        return _core[R]
    pool = A.build_pool(R, 1)
    names = {f'LD{r}_D' for r in range(R)} | {f'ST{r}_D' for r in range(R)} | \
            {f'ADD{r}_D' for r in range(R)} | {f'SUB{r}_D' for r in range(R)} | \
            {'JZ0', 'JN0', 'JMP0', 'LDX0_D', 'LD0_X0', 'ST0_X0'}
    if R > 1:
        names |= {f'MOV{a}{b}' for a in range(R) for b in range(R) if a != b}
    names = set(sorted(names)[:16])
    g = A.core_gates(pool, names, R, 1)
    _core[R] = g
    return g


def evaluate(pin, static, dyn):
    pin = frozenset(pin)
    words = sum(n * shape(op, pin)[0] for op, n in static.items())
    cycles = sum(n * shape(op, pin)[1] for op, n in dyn.items())
    data = (7 - len(pin)) + ARRN
    R = len(pin) + 1
    core = core_gates(R)
    total = core + G_ROM * (words + NCONST) + G_RAM * data
    return dict(pin=sorted(pin), R=R, words=words, cycles=cycles, data=data,
                core=core, total=round(total))


if __name__ == '__main__':
    static, dyn = profile()
    scal = sorted({x for op in static for x in op[1:] if x})
    rows = []
    for k in range(len(scal) + 1):
        for c in itertools.combinations(scal, k):
            if len(c) + 1 > 8:
                continue
            rows.append(evaluate(c, static, dyn))
    rows.sort(key=lambda r: r['total'])
    print('%-26s %-3s %-7s %-7s %-6s %-7s %s' %
          ('pinned to registers', 'R', 'gates', 'words', 'data', 'core', 'cycles'))
    for r in rows[:8]:
        print('%-26s %-3d %-7d %-7d %-6d %-7d %d' %
              (' '.join(r['pin']) or '(none)', r['R'], r['total'], r['words'],
               r['data'], r['core'], r['cycles']))
    print('...')
    base = [r for r in rows if not r['pin']][0]
    best = rows[0]
    print('%-26s %-3d %-7d %-7d %-6d %-7d %d' %
          ('(none, the phase 4 shape)', base['R'], base['total'], base['words'],
           base['data'], base['core'], base['cycles']))
    print()
    print('best %d against %d: %+.1f%% gates, %+.1f%% cycles' %
          (best['total'], base['total'], 100 * (best['total'] / base['total'] - 1),
           100 * (best['cycles'] / base['cycles'] - 1)))
    json.dump(rows[:20], open(f'{BUILD}/workingset.json', 'w'), indent=1)
