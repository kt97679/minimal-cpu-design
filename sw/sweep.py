#!/usr/bin/env python3
"""
Design-space sweep: how does total gate count vary with instruction set size,
for the same task (emit F0..F99 mod 2^16 through an output port)?

For each design point this assembles the program, checks it on an emulator,
runs the RTL, and synthesises the core to NAND gates. Total gates are then
  core + N * (cost of one 16-bit word of gate-built RAM)
with the per-word cost measured, not assumed.
"""
import json
import math
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build')
os.makedirs(BUILD, exist_ok=True)
MASK = 0xFFFF
N_OUT = 100
N_ITER = 50

REF = [0, 1]
while len(REF) < N_OUT:
    REF.append((REF[-1] + REF[-2]) & MASK)

# ----------------------------------------------------------- accumulator ISA
OPC = dict(LDA=0, STA=1, JZ=2, SUB=3, ADD=4, JMP=5, LDC=6, DJNZ=7,
           AND=8, OR=9, XOR=10, SHR=11)
CYC = dict(LDA=2, STA=2, SUB=2, ADD=2, AND=2, OR=2, XOR=2, SHR=2,
           JZ=1, JMP=1, LDC=1, DJNZ=1)

# ---- V1: the original four instructions. No ADD, so a+b is a double negate;
#          no JMP, so an unconditional jump is LDA zero + JZ.
V1 = [
    ('loop', 'LDA', 'a'), (None, 'STA', 'port'),
    (None, 'LDA', 'b'), (None, 'STA', 'port'),
    (None, 'LDA', 'zero'), (None, 'SUB', 'b'), (None, 'STA', 't'),
    (None, 'LDA', 'a'), (None, 'SUB', 't'), (None, 'STA', 'a'),
    (None, 'LDA', 'zero'), (None, 'SUB', 'a'), (None, 'STA', 't'),
    (None, 'LDA', 'b'), (None, 'SUB', 't'), (None, 'STA', 'b'),
    (None, 'LDA', 'cnt'), (None, 'SUB', 'one'), (None, 'STA', 'cnt'),
    (None, 'JZ', 'done'), (None, 'LDA', 'zero'), (None, 'JZ', 'loop'),
    ('done', 'JZ', 'done'),
]
V1D = [('zero', 0), ('one', 1), ('cnt', N_ITER), ('a', 0), ('b', 1), ('t', 0)]

# ---- V2: + ADD and JMP. ADD lets the accumulator carry a+b straight into the
#          next update, which removes the temporary entirely.
V2 = [
    ('loop', 'LDA', 'a'), (None, 'STA', 'port'),
    (None, 'LDA', 'b'), (None, 'STA', 'port'),
    (None, 'ADD', 'a'), (None, 'STA', 'a'),
    (None, 'ADD', 'b'), (None, 'STA', 'b'),
    (None, 'LDA', 'cnt'), (None, 'SUB', 'one'), (None, 'STA', 'cnt'),
    (None, 'JZ', 'done'), (None, 'JMP', 'loop'),
    ('done', 'JMP', 'done'),
]
V2D = [('one', 1), ('cnt', N_ITER), ('a', 0), ('b', 1)]

# ---- V3: + a counter register with LDC/DJNZ, collapsing four loop-control
#          instructions and two data words into one instruction.
V3 = [
    (None, 'LDC', N_ITER),
    ('loop', 'LDA', 'a'), (None, 'STA', 'port'),
    (None, 'LDA', 'b'), (None, 'STA', 'port'),
    (None, 'ADD', 'a'), (None, 'STA', 'a'),
    (None, 'ADD', 'b'), (None, 'STA', 'b'),
    (None, 'DJNZ', 'loop'),
    ('done', 'JMP', 'done'),
]
V3D = [('a', 0), ('b', 1)]


def asm_acc(code, data):
    sym, pc = {}, 0
    for lbl, _, _ in code:
        if lbl:
            sym[lbl] = pc
        pc += 1
    ncode = pc
    for name, _ in data:
        sym[name] = pc
        pc += 1
    n = pc
    sym['port'] = n                      # port sits one past the last RAM word
    mem = [0] * n
    for i, (_, op, arg) in enumerate(code):
        a = arg if isinstance(arg, int) else sym[arg]
        mem[i] = (OPC[op] << 12) | (a & 0xFF)
    for name, v in data:
        mem[sym[name]] = v & MASK
    return mem, n, len(code), sym


def emu_acc(mem, n, limit=10 ** 6):
    mem = mem[:] + [0]
    pc, acc, ctr, cyc, out, ic = 0, 0, 0, 0, [], 0
    inv = {v: k for k, v in OPC.items()}
    while len(out) < N_OUT and ic < limit:
        w = mem[pc]
        op, ad = inv[(w >> 12) & 0xF], w & 0xFF
        pc += 1
        ic += 1
        cyc += CYC[op]
        if op == 'LDA':
            acc = mem[ad]
        elif op == 'STA':
            if ad == n:
                out.append(acc)
            else:
                mem[ad] = acc
        elif op == 'JZ':
            if acc == 0:
                pc = ad
        elif op == 'SUB':
            acc = (acc - mem[ad]) & MASK
        elif op == 'ADD':
            acc = (acc + mem[ad]) & MASK
        elif op == 'JMP':
            pc = ad
        elif op == 'LDC':
            ctr = ad
        elif op == 'DJNZ':
            ctr = (ctr - 1) & 0xFF
            if ctr:
                pc = ad
    return out, cyc, ic


# ----------------------------------------------------------- specialised ISA
F2 = dict(LDIA=0, LDIB=1, LDC=2, OUTA=3, OUTB=4, ADDBA=5, ADDAB=6, DJNZ=7, JMP=8)
FIB2 = [
    (None, 'LDIA', 0), (None, 'LDIB', 1), (None, 'LDC', N_ITER),
    ('loop', 'OUTA', 0), (None, 'OUTB', 0),
    (None, 'ADDBA', 0), (None, 'ADDAB', 0),
    (None, 'DJNZ', 'loop'),
    ('done', 'JMP', 'done'),
]


def asm_fib2():
    sym, pc = {}, 0
    for lbl, _, _ in FIB2:
        if lbl:
            sym[lbl] = pc
        pc += 1
    mem = []
    for _, op, arg in FIB2:
        a = arg if isinstance(arg, int) else sym[arg]
        mem.append((F2[op] << 12) | (a & 0xFF))
    return mem, pc, pc


def emu_fib2(mem, limit=10 ** 5):
    pc, ra, rb, rc, cyc, out, ic = 0, 0, 0, 0, 0, [], 0
    inv = {v: k for k, v in F2.items()}
    while len(out) < N_OUT and ic < limit:
        w = mem[pc]
        op, ad = inv[(w >> 12) & 0xF], w & 0xFF
        pc += 1
        ic += 1
        cyc += 1
        if op == 'LDIA':
            ra = ad
        elif op == 'LDIB':
            rb = ad
        elif op == 'LDC':
            rc = ad
        elif op == 'OUTA':
            out.append(ra)
        elif op == 'OUTB':
            out.append(rb)
        elif op == 'ADDBA':
            ra = (ra + rb) & MASK
        elif op == 'ADDAB':
            rb = (rb + ra) & MASK
        elif op == 'DJNZ':
            rc = (rc - 1) & 0xFF
            if rc:
                pc = ad
        elif op == 'JMP':
            pc = ad
    return out, cyc, ic


# ----------------------------------------------------------------- SUBLEQ
SQ = [
    ('loop', 'a', 'Z', None), (None, 'Z', 'port', None), (None, 'Z', 'Z', None),
    (None, 'b', 'Z', None), (None, 'Z', 'port', None), (None, 'Z', 'Z', None),
    (None, 'b', 'Z', None), (None, 'Z', 'a', None), (None, 'Z', 'Z', None),
    (None, 'a', 'Z', None), (None, 'Z', 'b', None), (None, 'Z', 'Z', None),
    (None, 'one', 'cnt', 'done'), (None, 'Z', 'Z', 'loop'),
    ('done', 'Z', 'Z', 'done'),
]
SQD = [('Z', 0), ('one', 1), ('cnt', N_ITER), ('a', 0), ('b', 1)]


def asm_subleq():
    sym, pc = {}, 0
    for lbl, _, _, _ in SQ:
        if lbl:
            sym[lbl] = pc
        pc += 3
    for name, _ in SQD:
        sym[name] = pc
        pc += 1
    n = pc
    sym['port'] = n
    mem, p = [0] * n, 0
    for _, A, B, C in SQ:
        mem[p] = sym[A]
        mem[p + 1] = sym[B]
        mem[p + 2] = (p + 3) if C is None else sym[C]
        p += 3
    for name, v in SQD:
        mem[sym[name]] = v & MASK
    return mem, n, 3 * len(SQ)


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def emu_subleq(mem, n, limit=10 ** 6):
    mem = mem[:] + [0]
    pc, cyc, out, ic = 0, 0, [], 0
    while len(out) < N_OUT and ic < limit:
        A, B, C = mem[pc], mem[pc + 1], mem[pc + 2]
        va = 0 if A == n else mem[A]
        vb = 0 if B == n else mem[B]
        r = (vb - va) & MASK
        if B == n:
            out.append(r)
        else:
            mem[B] = r
        pc = C if s16(r) <= 0 else pc + 3
        cyc += 6
        ic += 1
    return out, cyc, ic


# ----------------------------------------------------------------- helpers
def hexfile(mem, path):
    with open(path, 'w') as f:
        for w in mem:
            f.write('%04x\n' % (w & MASK))


def aw(n):
    return max(1, math.ceil(math.log2(n + 1)))


def yosys_nand(read_cmds, top):
    """Map a design to 2-input NANDs + plain DFFs and return (nand, dff)."""
    script = (read_cmds + f"""
        hierarchy -top {top}
        proc; opt; fsm; opt; memory; opt
        techmap; opt -full
        dfflegalize -cell $_DFF_P_ 0
        abc -g NAND
        opt_clean
        stat""")
    out = subprocess.run(['yosys', '-p', script], capture_output=True, text=True).stdout
    tail = out[out.rfind('Printing statistics'):]
    g = lambda c: int(re.search(rf'\$_{c}_\s+(\d+)', tail).group(1)) if re.search(rf'\$_{c}_\s+(\d+)', tail) else 0
    return g('NAND') + g('NOT'), g('DFF_P')


def write_rom(key, words, awidth):
    path = f'{BUILD}/rom_{key}.v'
    with open(path, 'w') as f:
        f.write(f'module rom(input clk, input [{awidth-1}:0] addr,'
                ' output reg [15:0] q);\n  always @(posedge clk) case (addr)\n')
        for i, w in enumerate(words):
            f.write(f"    {awidth}'d{i}: q <= 16'h{w & MASK:04x};\n")
        f.write("    default: q <= 16'h0000;\n  endcase\nendmodule\n")
    return path


def harvard_cost(key, ncode, ndata, awidth):
    """Gate cost of code-in-ROM + data-in-RAM, measured as one block."""
    rom = f'{BUILD}/rom_{key}.v'
    nand, dff = yosys_nand(
        f'read_verilog {rom} {ROOT}/rtl/memsys.v {ROOT}/rtl/ramg.v\n'
        f' chparam -set NCODE {ncode} -set NDATA {ndata} -set AW {awidth} memsys\n',
        'memsys')
    return nand + 6 * dff


def ram_cost(n):
    """NAND-equivalent cost of an n x 16 gate-built RAM (measured, not modelled)."""
    nand, dff = yosys_nand(
        f"read_verilog {ROOT}/rtl/ramg.v\n chparam -set N {n} -set AW {aw(n)} ramg\n", 'ramg')
    return nand + 6 * dff


DESIGNS = [
    dict(key='subleq', label='SUBLEQ', nops=1),
    dict(key='v1', label='LDA STA JZ SUB', nops=4, defs=[]),
    dict(key='v2', label='+ ADD JMP', nops=6, defs=['HAS_ADD', 'HAS_JMP']),
    dict(key='v3', label='+ LDC DJNZ', nops=8, defs=['HAS_ADD', 'HAS_JMP', 'HAS_CTR']),
    dict(key='v5', label='+ AND OR XOR SHR', nops=12,
         defs=['HAS_ADD', 'HAS_JMP', 'HAS_CTR', 'HAS_LOGIC']),
    dict(key='fib2', label='2-register machine', nops=9),
    dict(key='fsm', label='hardwired FSM', nops=0),
]


DUTFLAG = dict(subleq='DUT_SUBLEQ', fib2='DUT_FIB2', fsm='DUT_FSM',
               v1='DUT_ACC', v2='DUT_ACC', v3='DUT_ACC', v5='DUT_ACC')
SRC = dict(subleq=['subleq_cpu.v', 'comp_subleq.v'], fib2=['cpu_min.v'],
           fsm=['cpu_min.v'], v1=['cpu_acc.v'])
SRC['v2'] = SRC['v3'] = SRC['v5'] = SRC['v1']


def run_rtl(key, n, defs=()):
    """Simulate the real RTL; returns (cycles to 100th output, mismatches)."""
    exe = f'/tmp/sim_{key}'
    cmd = (['iverilog', '-g2012', '-o', exe, f'-D{DUTFLAG[key]}',
            f'-DNWORDS={max(n, 1)}', f'-DAWIDTH={aw(max(n, 1))}',
            f'-DHEXFILE="{BUILD}/{key}.hex"'] + ['-D' + d for d in defs] +
           [f'{ROOT}/rtl/tb_sweep.v', f'{ROOT}/rtl/ramg.v'] +
           [f'{ROOT}/rtl/{f}' for f in SRC[key]])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    out = subprocess.run([exe], capture_output=True, text=True, cwd=ROOT).stdout
    m = re.search(r'RESULT cycles=(\d+) outputs=\d+ errors=(\d+)', out)
    if not m:
        raise RuntimeError(f'{key}: {out.strip()}')
    return int(m.group(1)), int(m.group(2))


def main():
    progs = {
        'subleq': asm_subleq(),
        'v1': asm_acc(V1, V1D)[:3],
        'v2': asm_acc(V2, V2D)[:3],
        'v3': asm_acc(V3, V3D)[:3],
    }
    progs['v5'] = progs['v3']
    fmem, fn, fc = asm_fib2()
    progs['fib2'] = (fmem, fn, fc)
    progs['fsm'] = ([], 0, 0)

    # emulate everything first: a design that does not produce F0..F99 is not
    # a design point, it is a bug.
    emu = {}
    emu['subleq'] = emu_subleq(*progs['subleq'][:2])
    for k in ('v1', 'v2', 'v3'):
        emu[k] = emu_acc(*progs[k][:2])
    emu['v5'] = emu['v3']
    emu['fib2'] = emu_fib2(fmem)
    emu['fsm'] = (REF, 3 * N_ITER, 0)
    for k, (out, cyc, ic) in emu.items():
        assert out == REF, f'{k} produced wrong output'

    with open(f'{BUILD}/expected.txt', 'w') as f:
        for v in REF:
            f.write('%04x\n' % v)

    rows = []
    per_word = {}
    for d in DESIGNS:
        k = d['key']
        mem, n, ncode = progs[k]
        if n:
            hexfile(mem, f'{BUILD}/{k}.hex')
        # core gate count
        if k == 'fsm':
            rd = f'read_verilog {ROOT}/rtl/cpu_min.v\n'
            top = 'fib_fsm'
        elif k == 'fib2':
            rd = f'read_verilog {ROOT}/rtl/cpu_min.v\n chparam -set AW {aw(n)} comp_fib2\n'
            top = 'comp_fib2'
        elif k == 'subleq':
            rd = (f'read_verilog {ROOT}/rtl/subleq_cpu.v {ROOT}/rtl/comp_subleq.v\n'
                  f' chparam -set N {n} -set AW {aw(n)} comp_subleq\n')
            top = 'comp_subleq'
        else:
            defs = ' '.join('-D' + x for x in d['defs'])
            rd = (f'read_verilog {defs} {ROOT}/rtl/cpu_acc.v {ROOT}/rtl/cpu_min.v\n'
                  f' chparam -set N {n} -set AW {aw(n)} comp_acc\n')
            top = 'comp_acc'
        rtl_cyc, rtl_err = run_rtl(k, n, d.get('defs', ()))
        nand, dff = yosys_nand(rd, top)
        core = nand + 6 * dff
        if n not in per_word:
            per_word[n] = ram_cost(n) if n else 0
        mem_gates = per_word[n]
        harv = 0
        if n:
            write_rom(k, mem[:ncode], aw(n))
            harv = harvard_cost(k, ncode, n - ncode, aw(n))
        rows.append(dict(key=k, label=d['label'], nops=d['nops'], words=n,
                         core=core, dff=dff, mem=mem_gates,
                         total=core + mem_gates, rom=harv,
                         harvard=core + harv, ncode=ncode,
                         cycles=rtl_cyc, emu_cycles=emu[k][1], errors=rtl_err))

    json.dump(rows, open(f'{BUILD}/sweep.json', 'w'), indent=1)
    print('%-22s %4s %6s %6s %8s %8s %8s %8s %7s' %
          ('design', 'ops', 'words', 'core', 'all-RAM', 'TOTAL',
           'ROM+RAM', 'TOTAL', 'cycles'))
    for r in rows:
        print('%-22s %4d %6d %6d %8d %8d %8d %8d %7d' %
              (r['label'], r['nops'], r['words'], r['core'], r['mem'],
               r['total'], r['rom'], r['harvard'], r['cycles']))
        assert r['errors'] == 0, r['key']
        assert abs(r['cycles'] - r['emu_cycles']) <= 2, r['key']


if __name__ == '__main__':
    main()
