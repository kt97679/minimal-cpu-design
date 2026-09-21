#!/usr/bin/env python3
"""
Phase 10: a workload shaped like real firmware, and the two instructions it
needs that nothing in phases 1-9 had.

The benchmark so far was five textbook kernels. This one is the shape a small
embedded controller actually has: scan a buffer of samples, reduce it, checksum
it, and format the results for a serial line. It differs from the old suite in
three ways that matter architecturally.

  * It has a subroutine. Decimal formatting is called four times, which is what
    CALL and RETURN are for -- and no machine in this project has them. Targets
    without CALL must inline the body at every site, which is the cost the
    instruction exists to avoid.
  * It needs XOR, because it computes a CRC. The old suite never needed a
    logic operation, which is why phase 2 concluded logic instructions were
    dead weight. That conclusion was a property of the benchmark.
  * It is code-heavy rather than data-heavy, which is the regime phase 9's
    crossover analysis said was needed before density can decide anything.

Program: 16 samples in a buffer; compute the (wrapping) sum, the minimum and
the maximum by indexed scan; compute a CRC-16 with polynomial 0x1021, most
significant bit first; then print all four as five decimal digits each, through
one subroutine called four times. 20 output values.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite import ARR0, ARRN, MASK, s16

POLY = 0x1021
NDIG = 5


def suite2():
    P, ren = [], {}

    def e(op):
        P.append(tuple(op[:1]) + tuple(ren.get(x, x) if isinstance(x, str) else x
                                       for x in op[1:]))

    def pool(**m):
        ren.clear(); ren.update(m)

    # ---- pass 1: sum, min, max over the buffer
    pool(i='v0', t='v1', u='v2', sum='v3', mn='v4', mx='v5')
    e(('movi', 'i', 0)); e(('movi', 'sum', 0))
    e(('movi', 'mn', 32767)); e(('movi', 'mx', 0))
    e(('label', 'l1'))
    e(('ldx', 't', 'ARR', 'i'))
    e(('add', 'sum', 't'))
    e(('mov', 'u', 't')); e(('sub', 'u', 'mn')); e(('jn', 'u', 'setmin'))
    e(('jmp', 'skipmin'))
    e(('label', 'setmin')); e(('mov', 'mn', 't'))
    e(('label', 'skipmin'))
    e(('mov', 'u', 'mx')); e(('sub', 'u', 't')); e(('jn', 'u', 'setmax'))
    e(('jmp', 'skipmax'))
    e(('label', 'setmax')); e(('mov', 'mx', 't'))
    e(('label', 'skipmax'))
    e(('addi', 'i', 1))
    e(('mov', 'u', 'i')); e(('subi', 'u', ARRN)); e(('jn', 'u', 'l1'))

    # ---- pass 2: CRC-16, MSB first
    pool(i='v0', t='v1', u='v2', crc='v6', bc='v7')
    e(('movi', 'crc', 0)); e(('movi', 'i', 0))
    e(('label', 'c1'))
    e(('ldx', 't', 'ARR', 'i'))
    e(('movi', 'bc', 16))
    e(('label', 'c2'))
    e(('mov', 'u', 'crc')); e(('xor', 'u', 't'))       # top bit = crc^t
    e(('add', 'crc', 'crc')); e(('add', 't', 't'))     # both <<= 1
    e(('jn', 'u', 'c3')); e(('jmp', 'c4'))
    e(('label', 'c3')); e(('xori', 'crc', POLY))
    e(('label', 'c4'))
    e(('subi', 'bc', 1)); e(('jz', 'bc', 'c5')); e(('jmp', 'c2'))
    e(('label', 'c5'))
    e(('addi', 'i', 1))
    e(('mov', 'u', 'i')); e(('subi', 'u', ARRN)); e(('jn', 'u', 'c1'))

    # ---- output: four values through one subroutine
    pool(val='v8', sum='v3', mn='v4', mx='v5', crc='v6')
    for src in ('sum', 'mn', 'mx', 'crc'):
        e(('mov', 'val', src)); e(('call', 'print'))
    e(('halt',))

    # ---- subroutine: print `val` as NDIG decimal digits, least first
    pool(val='v8', dc='v0', q='v1', rem='v2', cnt='v7', w='v9', t='v10')
    e(('label', 'print'))
    e(('movi', 'dc', NDIG))
    e(('label', 'p0'))
    e(('movi', 'q', 0)); e(('movi', 'rem', 0))
    e(('movi', 'cnt', 16)); e(('mov', 'w', 'val'))
    e(('label', 'p1'))
    e(('add', 'rem', 'rem'))
    e(('jn', 'w', 'p2')); e(('jmp', 'p3'))
    e(('label', 'p2')); e(('addi', 'rem', 1))
    e(('label', 'p3'))
    e(('add', 'w', 'w')); e(('add', 'q', 'q'))
    e(('mov', 't', 'rem')); e(('subi', 't', 10)); e(('jn', 't', 'p4'))
    e(('subi', 'rem', 10)); e(('addi', 'q', 1))
    e(('label', 'p4'))
    e(('subi', 'cnt', 1)); e(('jz', 'cnt', 'p5')); e(('jmp', 'p1'))
    e(('label', 'p5'))
    e(('out', 'rem')); e(('mov', 'val', 'q'))
    e(('subi', 'dc', 1)); e(('jz', 'dc', 'p6')); e(('jmp', 'p0'))
    e(('label', 'p6'))
    e(('ret',))
    return P


def golden2():
    out = []
    sm = 0
    for v in ARR0:
        sm = (sm + v) & MASK
    mn, mx = min(ARR0), max(ARR0)
    crc = 0
    for s in ARR0:
        t = s
        for _ in range(16):
            top = (crc ^ t) & 0x8000
            crc = (crc << 1) & MASK
            t = (t << 1) & MASK
            if top:
                crc ^= POLY
    for v in (sm, mn, mx, crc):
        x = v
        for _ in range(NDIG):
            out.append(x % 10)
            x //= 10
    return out


def interp2(prog):
    """Reference interpreter, including call/ret, for checking the program."""
    lab = {op[1]: i for i, op in enumerate(prog) if op[0] == 'label'}
    m, out, pc, lr, steps = {'ARR': list(ARR0)}, [], 0, None, 0
    g = lambda n: m.get(n, 0)
    while pc < len(prog) and steps < 10 ** 7:
        op = prog[pc]; pc += 1; steps += 1; k = op[0]
        if k == 'label':
            continue
        elif k == 'halt':
            break
        elif k == 'call':
            lr = pc; pc = lab[op[1]]
        elif k == 'ret':
            pc = lr
        elif k == 'movi':
            m[op[1]] = op[2] & MASK
        elif k == 'mov':
            m[op[1]] = g(op[2])
        elif k == 'add':
            m[op[1]] = (g(op[1]) + g(op[2])) & MASK
        elif k == 'sub':
            m[op[1]] = (g(op[1]) - g(op[2])) & MASK
        elif k == 'xor':
            m[op[1]] = g(op[1]) ^ g(op[2])
        elif k == 'xori':
            m[op[1]] = g(op[1]) ^ (op[2] & MASK)
        elif k == 'addi':
            m[op[1]] = (g(op[1]) + op[2]) & MASK
        elif k == 'subi':
            m[op[1]] = (g(op[1]) - op[2]) & MASK
        elif k == 'out':
            out.append(g(op[1]))
        elif k == 'jmp':
            pc = lab[op[1]]
        elif k == 'jz':
            pc = lab[op[2]] if g(op[1]) == 0 else pc
        elif k == 'jn':
            pc = lab[op[2]] if s16(g(op[1])) < 0 else pc
        elif k == 'ldx':
            m[op[1]] = m[op[2]][g(op[3])]
        elif k == 'stx':
            m[op[1]][g(op[2])] = g(op[3])
        else:
            raise ValueError(k)
    return out


def inline_calls(prog):
    """Splice subroutine bodies at every call site, for machines without CALL.

    This is what a machine with no subroutine instruction must do, and the code
    it costs is exactly what CALL and RETURN exist to save.
    """
    lab = {op[1]: i for i, op in enumerate(prog) if op[0] == 'label'}
    targets = {op[1] for op in prog if op[0] == 'call'}
    bodies, skip = {}, set()
    for name in targets:
        j = lab[name] + 1
        body = []
        while j < len(prog) and prog[j][0] != 'ret':
            body.append(prog[j]); j += 1
        bodies[name] = body
        for k in range(lab[name], j + 1):
            skip.add(k)
    out, n = [], 0
    for i, op in enumerate(prog):
        if i in skip:
            continue
        if op[0] == 'call':
            n += 1
            for b in bodies[op[1]]:
                if b[0] == 'label':
                    out.append(('label', f'{b[1]}__{n}'))
                elif b[0] == 'jmp':
                    out.append((b[0], f'{b[1]}__{n}'))
                elif b[0] in ('jz', 'jn'):
                    out.append((b[0], b[1], f'{b[2]}__{n}'))
                else:
                    out.append(b)
        else:
            out.append(op)
    return out


if __name__ == '__main__':
    p = suite2()
    g = golden2()
    got = interp2(p)
    print('firmware benchmark: %d virtual ops, %d outputs' %
          (len([o for o in p if o[0] != 'label']), len(g)))
    print('reference interpreter matches the model:', got == g)
    pi = inline_calls(p)
    print('with calls inlined: %d virtual ops (%.2fx)' %
          (len([o for o in pi if o[0] != 'label']),
           len([o for o in pi if o[0] != 'label']) /
           len([o for o in p if o[0] != 'label'])))
    print('outputs:', g[:10], '...')
