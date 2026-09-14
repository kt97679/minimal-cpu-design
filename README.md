# SUBLEQ (OISC) vs. 4-instruction accumulator machine — gate count & speed

Both machines: 16-bit words, 12-bit address space, one single-port synchronous
RAM, next-instruction fetch overlapped with the last cycle of the current
instruction. Same Fibonacci program (F0..F99 mod 2^16, 2x unrolled so neither
machine needs register copies), verified against a Python reference.

    python3 asm.py                      # assemble + emulate + emit .hex images
    iverilog -g2012 -o sim tb.v acc_cpu.v subleq_cpu.v && ./sim   # cycle counts
    yosys -s n_acc.ys                   # NAND-only gate count
    yosys -p "read_verilog top.v acc_cpu.v; synth_ice40 -top top_acc -json acc.json"
    nextpnr-ice40 --hx8k --package ct256 --json acc.json --freq 200   # Fmax

## Results

|                           |  accumulator | SUBLEQ |  ratio |
|---------------------------|-------------:|-------:|-------:|
| program size (words)      |          136 |    157 |  1.15x |
| instructions executed     |         1398 |    799 |  0.57x |
| cycles                    |         2698 |   4795 |  1.78x |
| CPU core, NAND-equivalent |          806 |   1161 |  1.44x |
| flip-flops                |           31 |     67 |  2.16x |
| iCE40 LUT4                |          109 |    108 |  0.99x |
| Fmax (iCE40-hx8k)         |     ~103 MHz | ~74 MHz|  0.72x |
| run time                  |      26.2 us | 64.6 us|  2.47x |
| whole computer (CPU+RAM)  |        27406 |  31841 |  1.16x |

NAND-equivalent = 2-input NAND cells after `abc -g NAND`, counting each D
flip-flop as 6 NANDs. RAM is a gate-level register file sized to each
program (136 / 157 words x 16 bit).
