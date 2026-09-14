#!/usr/bin/env python3
"""
Assembles the same Fibonacci algorithm for two machines:
  A) 4-instruction accumulator machine (LOAD / STORE / JZ / SUB)
  B) SUBLEQ one-instruction machine
Both: 16-bit words, 12-bit address space (4096 words), results mod 2^16.

Algorithm (identical for both, 2x unrolled so no register copies are needed):
    (a,b) = (F0,F1) = (0,1)
    repeat 50 times:
        out(a); out(b); a += b; b += a
  -> writes F0..F99 into a 100-word array.
"""
import os

BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build') + os.sep
os.makedirs(BUILD, exist_ok=True)

MASK = 0xFFFF
N_ITER = 50
ARRLEN = 100

# ---------------------------------------------------------------- machine A
OPC = {'LOAD': 0, 'STORE': 1, 'JZ': 2, 'SUB': 3}

acc_code = [
    ('loop', 'LOAD', 'a'),
    ('s1',   'STORE', ('arr', 0)),        # self-modified: arr[i] = a
    (None,   'LOAD', 's1'),
    (None,   'SUB', 'm2'),                # acc = s1 - (-2) = s1 + 2
    (None,   'STORE', 's1'),
    (None,   'LOAD', 'b'),
    ('s2',   'STORE', ('arr', 1)),        # self-modified: arr[i+1] = b
    (None,   'LOAD', 's2'),
    (None,   'SUB', 'm2'),
    (None,   'STORE', 's2'),
    # a += b   (only SUB exists, so negate through a temp)
    (None,   'LOAD', 'zero'),
    (None,   'SUB', 'b'),
    (None,   'STORE', 't'),
    (None,   'LOAD', 'a'),
    (None,   'SUB', 't'),
    (None,   'STORE', 'a'),
    # b += a
    (None,   'LOAD', 'zero'),
    (None,   'SUB', 'a'),
    (None,   'STORE', 't'),
    (None,   'LOAD', 'b'),
    (None,   'SUB', 't'),
    (None,   'STORE', 'b'),
    # loop control
    (None,   'LOAD', 'cnt'),
    (None,   'SUB', 'one'),
    (None,   'STORE', 'cnt'),
    (None,   'JZ', 'done'),
    (None,   'LOAD', 'zero'),             # unconditional jump = clear acc, JZ
    (None,   'JZ', 'loop'),
    ('done', 'JZ', 'done'),
]
acc_data = [('zero', 0), ('one', 1), ('m2', 0xFFFE), ('cnt', N_ITER),
            ('a', 0), ('b', 1), ('t', 0)]


def asm_acc():
    sym, pc = {}, 0
    for lbl, _, _ in acc_code:
        if lbl:
            sym[lbl] = pc
        pc += 1
    code_words = pc
    for name, _ in acc_data:
        sym[name] = pc
        pc += 1
    sym['arr'] = pc
    pc += ARRLEN
    mem = [0] * 4096
    p = 0
    for lbl, op, arg in acc_code:
        if isinstance(arg, tuple):
            a = sym[arg[0]] + arg[1]
        else:
            a = sym[arg]
        mem[p] = (OPC[op] << 12) | a
        p += 1
    for name, v in acc_data:
        mem[sym[name]] = v & MASK
    return mem, sym, code_words, pc


def emu_acc(mem, halt, limit=10_000_000):
    mem = mem[:]
    pc, acc, cyc, ic = 0, 0, 0, 0
    while pc != halt and ic < limit:
        w = mem[pc]
        op, ad = (w >> 12) & 3, w & 0xFFF
        pc += 1
        ic += 1
        if op == 0:
            acc = mem[ad]; cyc += 2
        elif op == 1:
            mem[ad] = acc; cyc += 2
        elif op == 2:
            cyc += 1
            if acc == 0:
                pc = ad
        else:
            acc = (acc - mem[ad]) & MASK; cyc += 2
    return mem, cyc, ic

# ---------------------------------------------------------------- machine B
# subleq A B [C] :  mem[B] -= mem[A]; if mem[B] <= 0 (signed) pc = C else pc += 3
subleq_code = [
    ('loop', 'a', 'Z', None),             # Z = -a
    ('p1', 'Z', ('arr', 0), None),        # arr[i] -= Z  ->  arr[i] += a
    (None, 'Z', 'Z', None),               # Z = 0
    (None, 'm2', ('p1', 1), None),        # p1's B field += 2
    (None, 'b', 'Z', None),
    ('p2', 'Z', ('arr', 1), None),
    (None, 'Z', 'Z', None),
    (None, 'm2', ('p2', 1), None),
    (None, 'b', 'Z', None),               # Z = -b
    (None, 'Z', 'a', None),               # a -= Z  ->  a += b
    (None, 'Z', 'Z', None),
    (None, 'a', 'Z', None),
    (None, 'Z', 'b', None),               # b += a
    (None, 'Z', 'Z', None),
    (None, 'one', 'cnt', 'done'),         # cnt -= 1 ; if cnt <= 0 -> done
    (None, 'Z', 'Z', 'loop'),             # unconditional jump
    ('done', 'Z', 'Z', 'done'),
]
subleq_data = [('Z', 0), ('one', 1), ('m2', 0xFFFE), ('cnt', N_ITER),
               ('a', 0), ('b', 1)]


def asm_subleq():
    sym, pc = {}, 0
    for lbl, _, _, _ in subleq_code:
        if lbl:
            sym[lbl] = pc
        pc += 3
    code_words = pc
    for name, _ in subleq_data:
        sym[name] = pc
        pc += 1
    sym['arr'] = pc
    pc += ARRLEN
    mem = [0] * 4096
    p = 0

    def res(x):
        return sym[x[0]] + x[1] if isinstance(x, tuple) else sym[x]
    for lbl, A, B, C in subleq_code:
        mem[p] = res(A)
        mem[p + 1] = res(B)
        mem[p + 2] = (p + 3) if C is None else res(C)
        p += 3
    for name, v in subleq_data:
        mem[sym[name]] = v & MASK
    return mem, sym, code_words, pc


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def emu_subleq(mem, halt, limit=10_000_000):
    mem = mem[:]
    pc, cyc, ic = 0, 0, 0
    while pc != halt and ic < limit:
        A, B, C = mem[pc], mem[pc + 1], mem[pc + 2]
        r = (mem[B] - mem[A]) & MASK
        mem[B] = r
        pc = C if s16(r) <= 0 else pc + 3
        cyc += 6
        ic += 1
    return mem, cyc, ic

# ---------------------------------------------------------------- main
def hexfile(mem, path):
    with open(path, 'w') as f:
        for w in mem:
            f.write('%04x\n' % (w & MASK))


def main():
    ref = [0, 1]
    while len(ref) < ARRLEN:
        ref.append((ref[-1] + ref[-2]) & MASK)

    am, asym, acode, atop = asm_acc()
    ares, acyc, aic = emu_acc(am, asym['done'])
    aout = ares[asym['arr']:asym['arr'] + ARRLEN]

    sm, ssym, scode, stop = asm_subleq()
    sres, scyc, sic = emu_subleq(sm, ssym['done'])
    sout = sres[ssym['arr']:ssym['arr'] + ARRLEN]

    print('ACC    : code=%d words  data=%d  array=%d  total=%d  instr=%d  cycles=%d  ok=%s'
          % (acode, atop - acode - ARRLEN, ARRLEN, atop, aic, acyc, aout == ref))
    print('SUBLEQ : code=%d words  data=%d  array=%d  total=%d  instr=%d  cycles=%d  ok=%s'
          % (scode, stop - scode - ARRLEN, ARRLEN, stop, sic, scyc, sout == ref))
    print('first 10 fib:', aout[:10])

    hexfile(am, BUILD + 'acc.hex')
    hexfile(sm, BUILD + 'subleq.hex')
    with open(BUILD + 'params.vh', 'w') as f:
        f.write('`define ACC_HALT 12\'d%d\n`define SUB_HALT 12\'d%d\n'
                '`define ARR_ACC 12\'d%d\n`define ARR_SUB 12\'d%d\n'
                % (asym['done'], ssym['done'], asym['arr'], ssym['arr']))
    with open(BUILD + 'expected.txt', 'w') as f:
        for v in ref:
            f.write('%04x\n' % v)


if __name__ == '__main__':
    main()
