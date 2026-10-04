#!/usr/bin/env python3
"""
Phase 14: the hybrid program store, which the article names as the assumption it
would attack first.

The central claim of this project is a 6.7x gap between machines that can index
an array without rewriting their own code and machines that cannot. Phase 4
flagged the weakness in print and never built it:

    The addresses a self-modifying program patches are fixed at assembly time,
    so the store could be split into ROM plus a handful of individually decoded
    writable words -- five of them for the seven-instruction machine. At my own
    per-word figures that lands near 8,000 gates, inside the cheap group. I have
    not built it, so treat it as a sketch.

This builds it. A self-modifying program writes to exactly one word per indexed
access site, and those addresses are link-time constants, so the store can be a
ROM with a small writable overlay: N 16-bit registers, each with an address
comparator, multiplexed into the read path ahead of the ROM.

Functionally the overlay is indistinguishable from RAM at those addresses -- the
same word is written and read back -- so the program's behaviour is unchanged
from the version verified in phase 3. What changes is only the area, which is
what is measured here.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import ROOT, BUILD, aw, yosys_nand, write_rom


def gen_hybrid(npatch, nro, ndata, awid, daw, patch_addrs):
    """ROM + npatch individually addressed writable words + data RAM."""
    decl = '\n'.join(f'    reg [15:0] pw{i};' for i in range(npatch))
    hits = '\n'.join(
        f'    wire h{i} = (addr == {awid}\'d{a});' for i, a in enumerate(patch_addrs))
    wr = '\n'.join(
        f'        if (we && h{i}) pw{i} <= din;' for i in range(npatch))
    regd = '\n'.join(f'        h{i}_d <= h{i};' for i in range(npatch))
    hdecl = ' '.join(f'reg h{i}_d;' for i in range(npatch))
    sel = ' : '.join(f'h{i}_d ? pw{i}' for i in range(npatch))
    read = f'({sel} : rom_q)' if npatch else 'rom_q'
    return f"""// ROM with a writable overlay: the words a self-modifying program patches
// are link-time constants, so each gets a register and a comparator instead of
// forcing the whole program store to be RAM.
module memsys3 #(parameter NRO = {nro}, NDATA = {ndata}, AW = {awid}, DAW = {daw}) (
    input wire clk, input wire [AW-1:0] addr, input wire we,
    input wire [15:0] din, output wire [15:0] dout);
    wire [15:0] rom_q, ram_q;
    wire [AW-1:0] off = addr - NRO[AW-1:0];
    reg sel_d;
    {hdecl}
{decl}
{hits}
    rom code (.clk(clk), .addr(addr), .q(rom_q));
    ramg #(.N(NDATA), .AW(DAW)) data (
        .clk(clk), .addr(off[DAW-1:0]), .we(we), .din(din), .dout(ram_q));
    always @(posedge clk) begin
        sel_d <= (addr < NRO[AW-1:0]);
{regd}
{wr}
    end
    assign dout = sel_d ? {read} : ram_q;
endmodule
"""


def measure(npatch, nro, ndata, image, key):
    a = aw(nro + ndata)
    d = max(1, (ndata - 1).bit_length())
    # patch sites spread through the code, as they are in the real program
    addrs = [int(nro * (i + 1) / (npatch + 1)) for i in range(npatch)]
    v = gen_hybrid(npatch, nro, ndata, a, d, addrs)
    open(f'{BUILD}/memsys3_{key}.v', 'w').write(v)
    write_rom(key, image[:nro], a)
    nand, dff = yosys_nand(
        f'read_verilog {BUILD}/memsys3_{key}.v {BUILD}/rom_{key}.v {ROOT}/rtl/ramg.v\n',
        'memsys3')
    return nand + 6 * dff


if __name__ == '__main__':
    # the seven-instruction machine: 247 words of code+constants, 23 of data,
    # and five patched instruction words, one per indexed access site
    NRO, NDATA, CORE = 247, 23, 1311
    image = [(i * 2654435761) & 0xFFFF for i in range(NRO)]   # representative content
    rows = []
    for npatch in (0, 1, 2, 5, 10, 20):
        g = measure(npatch, NRO, NDATA, image, f'hy{npatch}')
        rows.append((npatch, g, CORE + g))
    print('seven-instruction machine, which must rewrite its own code')
    print('%-18s %-12s %-10s %s' % ('writable words', 'memory', 'total', 'per word'))
    base = rows[0][1]
    for n, g, t in rows:
        per = '' if n == 0 else '%d' % ((g - base) / n)
        print('%-18s %-12d %-10d %s' % (n, g, t, per))
    print()
    print('for comparison, measured in phase 4:')
    print('%-18s %-12s %-10d' % ('all-RAM store', '', 49477))
    print('%-18s %-12s %-10d' % ('ten-instruction', 'ROM store', 7078))
    five = [t for n, _, t in rows if n == 5][0]
    print()
    print('hybrid store with five writable words: %d gates' % five)
    print('against the all-RAM figure of 49,477 and the ten-instruction 7,078')
    print('the 6.7x gap becomes %.2fx' % (five / 7078))
    json.dump([{'npatch': n, 'memory': g, 'total': t} for n, g, t in rows],
              open(f'{BUILD}/hybrid.json', 'w'), indent=1)
