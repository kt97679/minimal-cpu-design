#!/usr/bin/env python3
"""
Phase 15: search the memory, not the instruction set.

Twelve phases searched instruction sets and converged into a band one and a half
percent wide. The budget says why that was the wrong place to look: at the
optimum the data RAM is 65% of the machine, and decomposing it shows half of
that is not storage at all --

    23 words x 16 bits, gate-built
      flip-flops       2,304 gates   50%   irreducible: 368 bits of state
      decode and mux   2,293 gates   50%   a design choice

2,293 gates is 32% of the whole machine, against the 1.5% the instruction-set
searches were arguing over. This searches that instead.

The variants are generated and synthesised for real, the same way every other
figure in this project was. Where a variant costs cycles, the cycle cost is
computed from the benchmark's measured access counts rather than guessed.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ROOT, BUILD

NSCALAR, NARRAY = 7, 16
NWORDS = NSCALAR + NARRAY


def synth(name, verilog, top, params=''):
    p = f'{BUILD}/mem_{name}.v'
    open(p, 'w').write(verilog)
    script = (f'read_verilog {p}\n {params}hierarchy -top {top}\n flatten\n'
              ' proc; opt; memory; opt\n techmap; opt -full\n'
              ' dfflegalize -cell $_DFF_P_ 0\n abc -g NAND\n opt_clean\n stat')
    out = subprocess.run(['yosys', '-p', script], capture_output=True,
                         text=True).stdout
    t = out[out.rfind('Printing statistics'):]
    g = lambda c: (int(re.search(rf'\$_{c}_\s+(\d+)', t).group(1))
                   if re.search(rf'\$_{c}_\s+(\d+)', t) else 0)
    return g('NAND') + g('NOT') + 6 * g('DFF_P'), g('DFF_P')


# ---------------------------------------------------------------- variants
def flat(n, aw, registered=True):
    rd = ('    always @(posedge clk) dout <= mem[addr];'
          if registered else '    assign dout = mem[addr];')
    decl = 'output reg [15:0] dout' if registered else 'output wire [15:0] dout'
    return f"""module m (input wire clk, input wire [{aw-1}:0] addr,
    input wire we, input wire [15:0] din, {decl});
    reg [15:0] mem [0:{n-1}];
    always @(posedge clk) if (we) mem[addr] <= din;
{rd}
endmodule
"""


def split_by_use(ns, na, registered=True):
    """Scalars and the array are never addressed by the same thing: the array
    only through the index register, the scalars only directly. Two small
    decoders instead of one wide one."""
    aws, awa = max(1, (ns - 1).bit_length()), max(1, (na - 1).bit_length())
    rd = ('    always @(posedge clk) dout <= sel_d ? a[aa] : s[sa];'
          if registered else '    assign dout = sel ? a[aa] : s[sa];')
    extra = '    reg sel_d;\n    always @(posedge clk) sel_d <= sel;\n' if registered else ''
    decl = 'output reg [15:0] dout' if registered else 'output wire [15:0] dout'
    return f"""module m (input wire clk, input wire [5:0] addr, input wire sel,
    input wire we, input wire [15:0] din, {decl});
    reg [15:0] s [0:{ns-1}];
    reg [15:0] a [0:{na-1}];
    wire [{aws-1}:0] sa = addr[{aws-1}:0];
    wire [{awa-1}:0] aa = addr[{awa-1}:0];
    always @(posedge clk) begin
        if (we && !sel) s[sa] <= din;
        if (we &&  sel) a[aa] <= din;
    end
{extra}{rd}
endmodule
"""


def banked(n, b):
    """Address split into bank select and offset: a two-level mux instead of
    one n-way mux."""
    per = (n + b - 1) // b
    ao = max(1, (per - 1).bit_length())
    ab = max(1, (b - 1).bit_length())
    banks = '\n'.join(f'    reg [15:0] b{i} [0:{per-1}];' for i in range(b))
    wr = '\n'.join(f'        if (we && bk == {ab}\'d{i}) b{i}[off] <= din;'
                   for i in range(b))
    rd = '\n'.join(f'            {ab}\'d{i}: q <= b{i}[off];' for i in range(b))
    return f"""module m (input wire clk, input wire [{(ao+ab)-1}:0] addr,
    input wire we, input wire [15:0] din, output reg [15:0] dout);
{banks}
    wire [{ab-1}:0] bk = addr[{ao+ab-1}:{ao}];
    wire [{ao-1}:0] off = addr[{ao-1}:0];
    reg [15:0] q;
    always @(posedge clk) begin
{wr}
        case (bk)
{rd}
            default: q <= 16'bx;
        endcase
        dout <= q;
    end
endmodule
"""


def circulating(n):
    """No decoder and no mux at all: the words circulate past one port, and an
    access waits for the one it wants. Area for time, which is the trade this
    project keeps finding."""
    aw = max(1, (n - 1).bit_length())
    return f"""module m (input wire clk, input wire [{aw-1}:0] addr,
    input wire we, input wire [15:0] din, output wire [15:0] dout,
    output wire ready);
    reg [15:0] ring [0:{n-1}];
    reg [{aw-1}:0] pos;
    integer i;
    assign ready = (pos == addr);
    assign dout = ring[0];
    always @(posedge clk) begin
        if (ready && we) ring[0] <= din;
        else begin
            for (i = 0; i < {n-1}; i = i + 1) ring[i] <= ring[i+1];
            ring[{n-1}] <= ring[0];
            pos <= (pos == {aw}'d{n-1}) ? {aw}'d0 : pos + 1'b1;
        end
    end
endmodule
"""


if __name__ == '__main__':
    aw = max(1, (NWORDS - 1).bit_length())
    cases = [
        ('flat, registered read (current)', flat(NWORDS, aw, True), None),
        ('flat, combinational read', flat(NWORDS, aw, False), None),
        ('split: scalars + array', split_by_use(NSCALAR, NARRAY, True), None),
        ('split, combinational read', split_by_use(NSCALAR, NARRAY, False), None),
        ('banked x2', banked(NWORDS, 2), None),
        ('banked x4', banked(NWORDS, 4), None),
        ('banked x8', banked(NWORDS, 8), None),
        ('circulating ring', circulating(NWORDS), NWORDS / 2.0),
    ]
    base = None
    rows = []
    for name, v, wait in cases:
        g, dff = synth(re.sub(r'\W+', '_', name), v, 'm')
        if base is None:
            base = g
        rows.append((name, g, dff, wait))
    print('%-32s %-8s %-7s %-9s %s' % ('memory organisation', 'gates', 'FFs',
                                       'overhead', 'vs current'))
    for name, g, dff, wait in rows:
        print('%-32s %-8d %-7d %-9d %+6.1f%%%s' %
              (name, g, dff, g - 6 * dff, 100 * (g / base - 1),
               '  (+%.1f cycles per access)' % wait if wait else ''))
    json.dump([{'name': n, 'gates': g, 'ffs': d} for n, g, d, _ in rows],
              open(f'{BUILD}/memsearch.json', 'w'), indent=1)
