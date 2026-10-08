#!/usr/bin/env python3
"""
Mutation audit of the verification, after the Paleocomputing article.

That project injected thirty plausible bugs into its processor and found its
tests caught ten. Two thirds of broken processors passed every check as
healthy. This project has verified that one check can fail -- the baseline, in
phase 19 -- but has never asked the same question of the RTL verification.

Each mutation below is a plausible slip, not a random character change: a
swapped operator, a wrong flag, a wrong field, an off-by-one. A verification
worth having should go red on all of them.
"""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autosearch as A
from sweep import BUILD, TMPX

ISET = ['JN','JZ','LDX_D','LD_D','LD_X','ST_D','ST_X','SUB_D']
ORDER = sorted(ISET); OPC = {n:i for i,n in enumerate(ORDER)}
M = 0xFFFF

MUTATIONS = {
 'none (control)':            lambda v: v,
 'subtract becomes add':      lambda v: v.replace('acc - mdin', 'acc + mdin'),
 'branch on zero, fetch only': lambda v: v.replace("4'd1: begin maddr = zf ? iad", "4'd1: begin maddr = nf ? iad"),
 'branch on zero, both sites': lambda v: v.replace("zf ? iad", "nf ? iad"),
 'branch on sign inverted':   lambda v: v.replace('wire nf = acc[15];', 'wire nf = ~acc[15];'),
 'zero flag off by one':      lambda v: v.replace("acc == 16'd0", "acc == 16'd1"),
 'index add becomes or':      lambda v: v.replace('iad + xreg', 'iad | xreg'),
 'index register ignored':    lambda v: v.replace('wire [AW-1:0] xad = iad + xreg;', 'wire [AW-1:0] xad = iad;'),
 'LDX takes the high byte':   lambda v: v.replace('xreg <= mdin[7:0]', 'xreg <= mdin[15:8]'),
 'store writes the wrong reg':lambda v: v.replace('mdout = acc;', "mdout = 16'd0;"),
 'pc fails to advance':       lambda v: v.replace("pc <= pc + 1'b1; state <= S_D; end\n        default", "pc <= pc; state <= S_D; end\n        default"),
 'load reads the wrong port': lambda v: v.replace("4'd3: acc <= mdin;", "4'd3: acc <= 16'd0;"),
 'write enable stuck off':    lambda v: v.replace("mwe = 1'b1;", "mwe = 1'b0;"),
}


def emu(mem, order, steps=500):
    mem = mem[:]; pc = acc = x = 0
    for _ in range(steps):
        w = mem[pc]; op = (w >> 12) & 0xF; ad = w & 0xFF; nxt = (pc + 1) & 0xFF
        p = A.POOL[order[op]]
        if p['kind'] == 'alu':
            acc = A.ALU[p['op']](acc, mem[ad + (x if p['mode'] == 'X' else 0)]) & M
        elif p['kind'] == 'st':
            mem[ad + (x if p['mode'] == 'X' else 0)] = acc
        elif p['kind'] == 'ldx':
            x = mem[ad] & 0xFF
        elif p['kind'] == 'br':
            cls = 'z' if acc == 0 else ('n' if acc & 0x8000 else 'p')
            if cls in A.COND[p['op']]:
                if ad == pc: return mem
                nxt = ad
        pc = nxt
    return mem


def image():
    I = lambda n,a: (OPC[n] << 12) | a
    A_,B_,T_,KZ,IDX,ARR,R1,R2,R3 = 40,41,42,43,44,45,50,51,52
    code = [I('LD_D',A_), I('SUB_D',B_), I('ST_D',R1),
            I('LD_D',KZ), I('SUB_D',A_), I('ST_D',T_),
            I('LD_D',B_), I('SUB_D',T_), I('ST_D',R2),
            I('LDX_D',IDX), I('LD_X',ARR), I('ST_D',R3),
            I('LD_D',KZ), I('ST_X',ARR),
            I('LD_D',T_), I('JN',18), I('LD_D',A_), I('ST_D',R3),
            I('LD_D',KZ), I('JZ',22), I('LD_D',A_), I('ST_D',R2),
            I('LD_D',KZ), I('JZ',23)]
    mem = [0]*64
    for i,w in enumerate(code): mem[i] = w
    for a,v in {A_:20, B_:7, KZ:0, IDX:3}.items(): mem[a] = v   # 3, not 2: 45|2 == 45+2
    for i,v in enumerate([100,101,102,103,104,105]): mem[ARR+i] = v
    return mem


def check(mutate):
    """Run the project's RTL verification against a mutated processor."""
    v = mutate(A.gen_rtl(set(ISET), aw=8))
    mem = image(); ref = emu(mem, ORDER)
    open(f'{BUILD}/mu_gen.v','w').write(v)
    open(f'{BUILD}/mu_img.hex','w').write('\n'.join('%04x'%w for w in mem)+'\n')
    tb = """`timescale 1ns/1ps
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
    repeat (400) @(posedge clk);
    for (i=40;i<53;i=i+1) $display("%0d %0d", i, mem[i]);
    $finish;
  end
endmodule
"""
    open(f'{BUILD}/mu_tb.v','w').write(tb.replace('IMG', f'{BUILD}/mu_img.hex'))
    c = subprocess.run(['iverilog','-g2012','-o',f'{TMPX}/mu_sim',
                        f'{BUILD}/mu_tb.v', f'{BUILD}/mu_gen.v'],
                       capture_output=True, text=True)
    if c.returncode:
        return 'caught (does not compile)'
    out = subprocess.run([f'{TMPX}/mu_sim'], capture_output=True, text=True).stdout
    got = {int(l.split()[0]): int(l.split()[1]) for l in out.strip().split('\n')
           if l and l[0].isdigit()}
    if not got:
        return 'caught (no output)'
    bad = [a for a in got if got[a] != ref[a]]
    return 'caught (%d words differ)' % len(bad) if bad else 'no difference'


if __name__ == '__main__':
    results = {}
    for name, fn in MUTATIONS.items():
        v = fn(A.gen_rtl(set(ISET), aw=8))
        if name != 'none (control)' and v == A.gen_rtl(set(ISET), aw=8):
            results[name] = 'NOT APPLIED -- pattern did not match'
            continue
        results[name] = check(fn)
    print('%-30s %s' % ('mutation', 'verification says'))
    for n, r in results.items():
        print('%-30s %s' % (n, r))
    real = [r for n, r in results.items() if n != 'none (control)'
            and not r.startswith('NOT APPLIED')]
    caught = sum(1 for r in real if r.startswith('caught'))
    print()
    print('caught %d of %d mutations' % (caught, len(real)))
    if results['none (control)'] != 'no difference':
        print('CONTROL FAILED: the unmutated processor does not pass')
