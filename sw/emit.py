#!/usr/bin/env python3
"""Turn a searched instruction set into a real machine: emit the benchmark as an
actual memory image, check it produces the right 123 outputs, and synthesise it
the same way phases 1-6 synthesised the hand-designed machines.

Without this the search only ever produced modelled totals, which are not
comparable with the measured ones.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autosearch as A
import suite as S
from sweep import yosys_nand, ROOT, BUILD, aw, ram_cost, write_rom

M = 0xFFFF


def emit(iset, T, scheme):
    """Assemble the benchmark for this instruction set. Two passes for labels."""
    order = sorted(iset)
    OPC = {n: i for i, n in enumerate(order)}
    prog = S.suite()
    USED.clear()
    consts = []
    varnames = sorted({x for op in prog for x in op[1:]
                       if isinstance(x, str) and x.startswith('v')})

    sym, words = {}, []
    for _ in range(2):
        words, labels = [], {}
        for op in prog:
            if op[0] == 'label':
                labels[op[1]] = len(words)
                continue
            words.extend(emit_op(op, T, scheme, OPC, sym, len(words)))
        ncode = len(words)
        consts = sorted(c for c in USED if c.startswith(('K', '#')))
        addr = ncode
        for c in consts:
            sym[c] = addr; addr += 1
        nro = addr
        for v in varnames + sorted(c for c in USED if c.startswith('_')):
            sym[v] = addr; addr += 1
        sym['ARR'] = addr; addr += S.ARRN
        n = addr
        sym['port'] = n
        sym.update(labels)
    mem = [0] * n
    for i, w in enumerate(words):
        mem[i] = w & M
    for c in consts:
        mem[sym[c]] = (0 if c == 'Kz' else 1 if c == 'K1'
                       else (-int(c[2:]) if c.startswith('#-') else int(c[1:]))) & M
    for i, v in enumerate(S.ARR0):
        mem[sym['ARR'] + i] = v & M
    return mem, n, ncode, nro, sym, OPC


USED = set()


def slot(name, op, sym, here):
    """Resolve a template slot to an address (0 on the sizing pass)."""
    g = sym.get
    if name == 'd':
        return g(op[1], 0)
    if name == 's':
        return g(op[-1], 0)
    if name in ('t0', 't1'):
        USED.add('_' + name)           # only allocate scratch that is used
        return g('_' + name, 0)
    if name in ('port', 'Kz', 'K1'):
        if name != 'port':
            USED.add(name)
        return g(name, 0)
    if name == 'Kimm':
        USED.add(f'#{op[2]}'); return g(f'#{op[2]}', 0)
    if name == 'Kni':
        USED.add(f'#-{op[2]}'); return g(f'#-{op[2]}', 0)
    raise KeyError(name)


def emit_op(op, T, scheme, OPC, sym, here):
    k = op[0]
    I = lambda n, a: (OPC[n] << 12) | (a & 0xFFF)
    if k == 'halt':
        seq, plan = T['jmp']
        return [I(n, slot(o, op, sym, here)) for n, o in seq] + \
               [I(j, here) for j, _ in plan]
    if k in ('jz', 'jn', 'jmp'):
        seq, plan = T[k]
        out = [I(n, (sym.get(op[1], 0) if (o == 's' and k != 'jmp')
                     else slot(o, op, sym, here))) for n, o in seq]
        tgt = op[2] if k in ('jz', 'jn') else op[1]
        skip = here + len(out) + len(plan)
        for j, where in plan:
            out.append(I(j, sym.get(tgt, 0) if where == 'L' else skip))
        return out
    if k in ('ldx', 'stx'):
        _, *rest = op
        if scheme == 'reg':
            if k == 'ldx':
                d, base, i = rest
                return [I('LDX_D', sym.get(i, 0)), I('LD_X', sym.get(base, 0)),
                        I('ST_D', sym.get(d, 0))]
            base, i, s = rest
            return [I('LDX_D', sym.get(i, 0)), I('LD_D', sym.get(s, 0)),
                    I('ST_X', sym.get(base, 0))]
        raise NotImplementedError('only the index-register scheme is emitted')
    tpl = T[k] if k in ('mov', 'add', 'sub', 'out') else \
        (T.get(k + '_small') if (k in ('movi', 'addi', 'subi') and
                                 -2048 <= op[2] < 2048 and T.get(k + '_small'))
         else T.get(k + '_big') or T.get(k + '_small'))
    out = []
    for nm, o in tpl:
        p = A.POOL[nm]
        if p['mode'] == 'I':
            v = {'Kz': 0, 'K1': 1, 'Kimm': op[2] if len(op) > 2 else 0,
                 'Kni': -op[2] if len(op) > 2 else 0}.get(o, 0)
            out.append(I(nm, v & 0xFFF))
        else:
            out.append(I(nm, slot(o, op, sym, here)))
    return out


def emulate(mem, n, order, nout, limit=400000):
    mem = mem[:]; pc = acc = x = cyc = 0; out = []
    for _ in range(limit):
        if len(out) >= nout:
            break
        w = mem[pc]; opn = (w >> 12) & 0xF; ad = w & 0xFFF; nxt = pc + 1
        p = A.POOL[order[opn]]
        cyc += p['cycles']
        if p['kind'] == 'alu':
            v = (ad if p['mode'] == 'I' and ad < 0x800 else
                 ad - 0x1000 if p['mode'] == 'I' else
                 mem[ad + (x if p['mode'] == 'X' else 0)])
            acc = A.ALU[p['op']](acc, v & M) & M
        elif p['kind'] == 'st':
            a = ad + (x if p['mode'] == 'X' else 0)
            if a == n:
                out.append(acc)
            else:
                mem[a] = acc
        elif p['kind'] == 'ldx':
            x = (mem[ad] if p['mode'] == 'D' else ad) & 0xFF
        elif p['kind'] == 'br':
            cls = 'z' if acc == 0 else ('n' if acc & 0x8000 else 'p')
            if cls in A.COND[p['op']]:
                nxt = ad
        pc = nxt & 0xFFF
    return out, cyc


def measure(iset, scheme='reg'):
    iset = set(iset)
    T = A.compile_templates(iset)
    mem, n, ncode, nro, sym, OPC = emit(iset, T, scheme)
    order = sorted(iset)
    gold = S.golden()
    out, cyc = emulate(mem, n, order, len(gold))
    ok = (out == gold)
    core = A.core_gates(iset)
    key = 'searchwin'
    write_rom(key, mem[:nro], aw(n))
    nand, dff = yosys_nand(
        f'read_verilog {BUILD}/rom_{key}.v {ROOT}/rtl/memsys2.v {ROOT}/rtl/ramg.v\n'
        f' chparam -set NRO {nro} -set NDATA {n - nro} -set AW {aw(n)}'
        f' -set DAW {max(1, (n - nro - 1).bit_length())} memsys2\n', 'memsys2')
    mem_gates = nand + 6 * dff
    return dict(ok=ok, outputs=len(out), words=n, code=ncode, ro=nro,
                cycles=cyc, core=core, memory=mem_gates, total=core + mem_gates,
                image=mem, order=order)


if __name__ == '__main__':
    win = ['JN', 'JZ', 'LDX_D', 'LD_D', 'LD_X', 'ST_D', 'ST_X', 'SUB_D']
    r = measure(win)
    print('search winner:', ' '.join(win))
    print('  correct output : %s (%d values)' % (r['ok'], r['outputs']))
    print('  program        : %d code + %d const + %d data = %d words'
          % (r['code'], r['ro'] - r['code'], r['words'] - r['ro'], r['words']))
    print('  cycles         : %d' % r['cycles'])
    print('  core           : %d gates (synthesised)' % r['core'])
    print('  memory         : %d gates (synthesised)' % r['memory'])
    print('  TOTAL          : %d gates' % r['total'])
    json.dump({k: v for k, v in r.items() if k != 'image'},
              open(f'{BUILD}/searchwin.json', 'w'), indent=1)
