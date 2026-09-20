"""End-to-end check that the SEARCH WINNER's generated hardware really works:
assemble a program exercising all eight opcodes plus both branch outcomes, run
it in a reference emulator and in Icarus Verilog on the generated Verilog, and
compare the resulting memory."""
import sys, subprocess; sys.path.insert(0, 'sw')
import autosearch as A

ISET = ['JN', 'JZ', 'LDX_D', 'LD_D', 'LD_X', 'ST_D', 'ST_X', 'SUB_D']
order = sorted(ISET); OPC = {n: i for i, n in enumerate(order)}
M = 0xFFFF
I = lambda n, a: (OPC[n] << 12) | a
A_, B_, T_, KZ, IDX, ARR, R1, R2, R3 = 40, 41, 42, 43, 44, 45, 50, 51, 52

code = [
    I('LD_D', A_), I('SUB_D', B_), I('ST_D', R1),          # R1 = A - B
    I('LD_D', KZ), I('SUB_D', A_), I('ST_D', T_),          # T = -A
    I('LD_D', B_), I('SUB_D', T_), I('ST_D', R2),          # R2 = B + A
    I('LDX_D', IDX), I('LD_X', ARR), I('ST_D', R3),        # R3 = ARR[X]
    I('LD_D', KZ), I('ST_X', ARR),                         # ARR[X] = 0
    I('LD_D', T_), I('JN', 18),                            # taken (T < 0)
    I('LD_D', A_), I('ST_D', R3),                          # must be skipped
    I('LD_D', KZ), I('JZ', 22),                            # taken (acc == 0)
    I('LD_D', A_), I('ST_D', R2),                          # must be skipped
    I('LD_D', KZ), I('JZ', 23),                            # halt: jump to self
]
mem = [0] * 64
for i, w in enumerate(code): mem[i] = w
for a, v in {A_: 20, B_: 7, KZ: 0, IDX: 2}.items(): mem[a] = v
for i, v in enumerate([100, 101, 102, 103, 104]): mem[ARR + i] = v

def emu(mem, steps=500):
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

ref = emu(mem)
open('/tmp/gen.v', 'w').write(A.gen_rtl(set(ISET), aw=8))
open('/tmp/img.hex', 'w').write('\n'.join('%04x' % w for w in mem) + '\n')
tb = """
`timescale 1ns/1ps
module tb;
  reg clk=0, rst=1; always #5 clk=~clk;
  wire [7:0] a; wire we; wire [15:0] wd, rd; wire ifq;
  reg [15:0] mem [0:255]; reg [15:0] dout;
  always @(posedge clk) begin if (we) mem[a] <= wd; dout <= mem[a]; end
  assign rd = dout;
  gcpu #(.AW(8)) u(.clk(clk),.rst(rst),.maddr(a),.mwe(we),.mdout(wd),
                   .mdin(rd),.ifetch(ifq));
  integer i;
  initial begin
    $readmemh("/tmp/img.hex", mem);
    @(negedge clk); rst=0;
    repeat (400) @(posedge clk);
    for (i=40; i<53; i=i+1) $display("%0d %0d", i, mem[i]);
    $finish;
  end
endmodule
"""
open('/tmp/tb.v', 'w').write(tb)
subprocess.run(['iverilog', '-g2012', '-o', '/tmp/sim', '/tmp/tb.v', '/tmp/gen.v'], check=True)
out = subprocess.run(['/tmp/sim'], capture_output=True, text=True).stdout
rtl = {int(l.split()[0]): int(l.split()[1]) for l in out.strip().split('\n')
       if l and l[0].isdigit()}
print('%-6s %-10s %-10s %s' % ('addr', 'emulator', 'RTL', ''))
ok = True
for a in sorted(rtl):
    e = ref[a]
    same = (e == rtl[a])
    ok &= same
    print('%-6d %-10d %-10d %s' % (a, e, rtl[a], '' if same else '  <-- MISMATCH'))
print()
print('expected: R1=13, R2=27, R3=102, ARR[2]=0, skipped stores did not fire')
print('emulator and generated RTL agree:', ok)
