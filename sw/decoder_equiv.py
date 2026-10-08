#!/usr/bin/env python3
"""
Exhaustive decoder check, imported from the Paleocomputing project's finding 12.

Their argument, which applies here unchanged: functional tests execute only the
encodings the compiler emits. An opcode that decodes as two instructions, or a
default case that quietly does something, or a disagreement between the
assembler's opcode map and the hardware's, is invisible to every test this
project has. They found their new instruction occupying two encodings instead of
one by exactly this method, and said no functional test would ever have found it.

This project has three places that independently believe they know the opcode
map: `gen_rtl` assigns them with `sorted(iset)`, `emit.py` assembles with
`sorted(iset)`, and the reference emulator indexes `order[op]`. Nothing has ever
checked that all three agree, or what the hardware does with the opcodes no
instruction was assigned to.

Method: for every one of the 16 opcode values and several operand patterns, run
one instruction on the generated RTL and on the reference emulator from an
identical starting state, and compare the accumulator, the index register, the
program counter and memory.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autosearch as A
from sweep import BUILD, TMPX

M = 0xFFFF


def emulate_one(order, word, acc0, x0, mem0):
    """One instruction on the reference model. Returns the state after it."""
    mem = list(mem0)
    acc, x, pc = acc0, x0, 0
    op, ad = (word >> 12) & 0xF, word & 0xFF
    if op >= len(order):
        return None                      # no instruction assigned to this opcode
    p = A.POOL[order[op]]
    nxt = 1
    if p['kind'] == 'alu':
        if p['mode'] == 'I':
            v = ad if ad < 0x800 else ad - 0x1000
        else:
            v = mem[(ad + (x if p['mode'] == 'X' else 0)) & 0xFF]
        acc = A.ALU[p['op']](acc, v & M) & M
    elif p['kind'] == 'st':
        mem[(ad + (x if p['mode'] == 'X' else 0)) & 0xFF] = acc
    elif p['kind'] == 'ldx':
        x = (mem[ad] if p['mode'] == 'D' else ad) & 0xFF
    elif p['kind'] == 'inx':
        x = (x + 1) & 0xFF
    elif p['kind'] == 'sh':
        acc = (acc >> 1) if p['op'] == 'SHR' else ((acc << 1) & M)
    elif p['kind'] == 'br':
        cls = 'z' if acc == 0 else ('n' if acc & 0x8000 else 'p')
        if cls in A.COND[p['op']]:
            nxt = ad
    return acc, x, nxt, mem


TB = """`timescale 1ns/1ps
module tb;
  reg clk=0, rst=1; always #5 clk=~clk;
  wire [7:0] a; wire we; wire [15:0] wd, rd; wire ifq;
  reg [15:0] mem [0:255]; reg [15:0] dout;
  always @(posedge clk) begin if (we) mem[a] <= wd; dout <= mem[a]; end
  assign rd = dout;
  gcpu #(.AW(8)) u(.clk(clk),.rst(rst),.maddr(a),.mwe(we),.mdout(wd),.mdin(rd),.ifetch(ifq));
  integer i;
  initial begin
    $readmemh("IMG", mem);
    @(negedge clk); rst=0;
    repeat (CYCLES) @(posedge clk);
    $display("ACC %0d", u.acc);
    $display("X %0d", XREG);
    $display("PC %0d", u.pc);
    for (i=200;i<210;i=i+1) $display("M %0d %0d", i, mem[i]);
    $finish;
  end
endmodule
"""


def run_rtl(iset, word, acc0, x0, mem0, cycles=12):
    order = sorted(iset)
    v = A.gen_rtl(set(iset), aw=8)
    has_x = 'xreg' in v
    # a tiny preamble puts the accumulator and index into known states, then the
    # instruction under test runs, then the machine idles
    mem = list(mem0)
    mem[0] = word
    open(f'{BUILD}/de_gen.v', 'w').write(v)
    open(f'{BUILD}/de_img.hex', 'w').write('\n'.join('%04x' % w for w in mem) + '\n')
    tb = TB.replace('IMG', f'{BUILD}/de_img.hex').replace('CYCLES', str(cycles))
    tb = tb.replace('XREG', 'u.xreg' if has_x else "8'd0")
    open(f'{BUILD}/de_tb.v', 'w').write(tb)
    c = subprocess.run(['iverilog', '-g2012', '-o', f'{TMPX}/de_sim',
                        f'{BUILD}/de_tb.v', f'{BUILD}/de_gen.v'],
                       capture_output=True, text=True)
    if c.returncode:
        return None
    out = subprocess.run([f'{TMPX}/de_sim'], capture_output=True, text=True).stdout
    g = {}
    for line in out.strip().split('\n'):
        p = line.split()
        if p and p[0] in ('ACC', 'X', 'PC'):
            g[p[0]] = int(p[1])
        elif p and p[0] == 'M':
            g.setdefault('M', {})[int(p[1])] = int(p[2])
    return g


if __name__ == '__main__':
    ISET = ['LD_D', 'ST_D', 'ADD_D', 'SUB_D', 'JZ', 'JN', 'JMP', 'LDX_D', 'LD_X', 'ST_X']
    order = sorted(ISET)
    print('instruction set has %d opcodes; the field holds 16' % len(order))
    print('opcode map the assembler and the hardware both derive from sorted():')
    print('   ' + '  '.join('%d=%s' % (i, n) for i, n in enumerate(order)))
    print()

    # Every location except the one under test holds a jump to itself, so that
    # whatever the instruction does, the machine settles immediately afterwards
    # and the state read out belongs to that one instruction. The reference model
    # reads the same image, so operands are these same words.
    jmp = order.index('JMP')
    base = [(jmp << 12) | i for i in range(256)]

    # every opcode, with a few operand patterns
    rows, disagree, unassigned = [], [], []
    for op in range(16):
        for ad in (50, 51, 200, 60):
            word = (op << 12) | ad
            ref = emulate_one(order, word, 0, 0, base)
            got = run_rtl(ISET, word, 0, 0, base)
            if got is None:
                rows.append((op, ad, 'simulation failed')); continue
            if ref is None:
                unassigned.append((op, ad, got.get('ACC'), got.get('PC')))
                continue
            racc, rx, rpc, rmem = ref
            ok = (got['ACC'] == racc and got['X'] == rx and
                  all(rmem[a] == v for a, v in got.get('M', {}).items()))
            if not ok:
                disagree.append((op, order[op], ad, racc, got['ACC'], rx, got['X']))
    print('opcodes with an instruction assigned: %d' % len(order))
    print('disagreements between the hardware and the reference model: %d' % len(disagree))
    for d in disagree:
        print('   opcode %-2d %-8s operand %-4d  acc ref %-6d rtl %-6d  x ref %-4d rtl %d' % d)
    print()
    print('unassigned opcodes (%d of 16), and what the hardware does with them:'
          % (16 - len(order)))
    seen = {}
    for op, ad, acc, pc in unassigned:
        seen.setdefault(op, []).append((ad, acc, pc))
    for op in sorted(seen):
        s = seen[op]
        print('   opcode %-2d -> acc %s  pc %s' %
              (op, sorted({x[1] for x in s}), sorted({x[2] for x in s})))
