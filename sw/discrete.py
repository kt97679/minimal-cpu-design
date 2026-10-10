#!/usr/bin/env python3
"""
What the machine costs built from discrete parts, in components and in money.

Phases 19 to 22 computed this during a session without a committed script, the
same way phase 10 did, so the figures in part 2 could not be rechecked. This
makes them reproducible.

The structures are textbook and the prices are bulk hobbyist figures: nothing
here is measured, unlike everything else in this project, and part 2 says so.
What the model does give is the comparison between families and between memory
cells, which is what the chapter argues about.

Run: python3 sw/discrete.py      (also `make discrete`)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import BUILD

PRICE = dict(T=0.018, D=0.006, R=0.003, C=0.010, NM=0.030, PM=0.050,
             IC_NAND=0.20, IC_FF=0.22, IC_SRAM=1.50, IC_ROM=2.80)

# a 2-input gate, per family
GATE = {'RTL':  dict(T=2, R=3),          # NOR: one transistor and one base
        'DTL':  dict(D=3, T=1, R=3),     # resistor per input, one pull-up
        'CMOS': dict(NM=2, PM=2)}

# one stored bit, static
LATCH = {'RTL':  dict(T=8, R=12),
         'DTL':  dict(D=12, T=4, R=12),
         'CMOS': dict(NM=3, PM=3)}

# one stored bit, dynamic, plus what the array needs around it
DRAM = {
 'static latch':  dict(cell=None,                fixed=0,       fixedcost=0.0),
 '4T DRAM':       dict(cell=dict(NM=4),          fixed=60,      fixedcost=6.0),
 '3T DRAM + cap': dict(cell=dict(NM=3, C=1),     fixed=60,      fixedcost=6.0),
 '1T1C DRAM':     dict(cell=dict(NM=1, C=1),     fixed=60 + 16*8, fixedcost=6.0 + 16*0.20),
}

# the two cores this project measured, split into combinational gates and
# flip-flops, from the synthesised netlists
CORES = {'ten-instruction (chapter 4)':      dict(comb=1281, ff=38),
         'evolved, no subtractor (ch. 6)':   dict(comb=1001, ff=34)}

BITS = 368                      # 23 words of 16 bits
ROM = dict(D=3392, R=228)       # diode matrix: a diode where the bit is one,
                                # plus the word-line decoder

cost = lambda d: sum(PRICE[k] * v for k, v in d.items())
count = lambda d: sum(d.values())


def add(a, b):
    o = dict(a)
    for k, v in b.items():
        o[k] = o.get(k, 0) + v
    return o


def build(core_name, family, mem_name):
    c, g, l = CORES[core_name], GATE[family], LATCH[family]
    m = DRAM[mem_name]
    parts = {k: v * c['comb'] for k, v in g.items()}
    for k, v in l.items():                     # a flip-flop is two latches
        parts[k] = parts.get(k, 0) + 2 * v * c['ff']
    cell = l if m['cell'] is None else m['cell']
    parts = add(parts, {k: v * BITS for k, v in cell.items()})
    parts = add(parts, ROM)
    parts = add(parts, dict(D=BITS, R=39))     # read matrix and decode
    return (count(parts) + m['fixed'],
            cost(parts) + m['fixedcost'],
            parts)


def main():
    print('ONE 2-INPUT GATE')
    for f, d in GATE.items():
        print('   %-5s %-18s %2d parts  $%.3f' %
              (f, ' '.join('%d%s' % (v, k) for k, v in d.items()), count(d), cost(d)))
    print()
    print('ONE STORED BIT')
    for n, m in DRAM.items():
        if m['cell'] is None:
            for f, d in LATCH.items():
                print('   %-16s %-5s %2d parts  $%.3f' % (n, f, count(d), cost(d)))
        else:
            d = m['cell']
            print('   %-16s %-5s %2d parts  $%.3f' % (n, 'any', count(d), cost(d)))
    print('   %-16s %-5s %4.1f parts $%.4f  (a diode where the bit is one)'
          % ('ROM bit', '', 0.5, 0.5 * PRICE['D']))
    print()

    rows = []
    for cn in CORES:
        for f in GATE:
            for mn in DRAM:
                p, c, _ = build(cn, f, mn)
                rows.append((cn, f, mn, p, round(c, 2)))

    print('ALL %d DISCRETE COMBINATIONS, BEST FOUR EACH WAY' % len(rows))
    for title, key in (('fewest parts', 3), ('lowest cost', 4)):
        print(' %s' % title)
        for r in sorted(rows, key=lambda x: x[key])[:3]:
            print('   %-32s %-5s %-15s %6d parts  $%6.2f' % r)
    print()

    nand = -(-CORES['evolved, no subtractor (ch. 6)']['comb'] // 4)
    ff = -(-CORES['evolved, no subtractor (ch. 6)']['ff'] // 2)
    ic_cost = nand * PRICE['IC_NAND'] + ff * PRICE['IC_FF'] \
        + 2 * PRICE['IC_SRAM'] + PRICE['IC_ROM']
    print('SAME MACHINE IN 74HC LOGIC')
    print('   %d quad NANDs + %d dual flip-flops + 2 SRAM + 1 EEPROM = %d ICs, $%.2f'
          % (nand, ff, nand + ff + 3, ic_cost))
    ram_ic = -(-(BITS * 4 + 1191) // 4)
    rom_ic = -(-3392 // 4)
    print('   memory from gate ICs instead: %d ICs, $%.2f -- six times the processor'
          % (ram_ic + rom_ic, (ram_ic + rom_ic) * PRICE['IC_NAND']))

    json.dump([dict(core=a, family=b, memory=c, parts=d, cost=e)
               for a, b, c, d, e in rows], open(f'{BUILD}/discrete.json', 'w'),
              indent=1)


if __name__ == '__main__':
    main()
