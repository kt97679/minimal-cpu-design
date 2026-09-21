#!/usr/bin/env python3
"""
Phase 8: put the architecture in the search, not just the instruction set.

Phase 7 searched instruction sets inside a skeleton I had chosen: one
accumulator, memory operands, one optional index register. That skeleton was
the last unexamined assumption, and it is the same class of assumption the bias
objection was about -- one accumulator plus memory operands is what almost every
small machine has ever had.

Here the skeleton is generated too. Two structural axes:

    R = number of general data registers      (1, 2, 3)
    X = number of index registers             (0, 1, 2)

The instruction pool is regenerated for each (R, X): every arithmetic operation
in every addressing mode targeting every register, a store from every register,
every branch condition testing every register, an index load per index register,
and register-to-register moves for R > 1. Nothing is included because a real
machine had it.

What is still fixed, and why:
  * 16-bit data words. Phase 4 measured that storage cost is set by bits stored
    rather than words, so a narrower word cannot help; the benchmark needs
    16-bit values.
  * One memory port, one word per instruction, and the three-state fetch/
    execute/writeback skeleton. These are shared by every design measured in
    phases 1-8, so they are a constant rather than a variable.
  * The benchmark and the gate-built memory model.
"""
import itertools
import random
import re
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autosearch import ALU, COND, NEG, ZERO, POS, MASK, BUILD, ROOT

NTEST = 4
SCRATCH = ('t0', 't1')


# ----------------------------------------------------------- pool generation
def build_pool(R, X):
    """Every (operation, mode, register) combination the skeleton allows."""
    pool = {}
    def add(**kw):
        pool[kw['name']] = kw
    for op in ALU:
        for r in range(R):
            add(name=f'{op}{r}_D', kind='alu', op=op, mode='D', dst=r, idx=None, cycles=2)
            add(name=f'{op}{r}_I', kind='alu', op=op, mode='I', dst=r, idx=None, cycles=1)
            for i in range(X):
                add(name=f'{op}{r}_X{i}', kind='alu', op=op, mode='X', dst=r,
                    idx=i, cycles=2)
    for r in range(R):
        add(name=f'ST{r}_D', kind='st', op='ST', mode='D', dst=r, idx=None, cycles=2)
        for i in range(X):
            add(name=f'ST{r}_X{i}', kind='st', op='ST', mode='X', dst=r, idx=i,
                cycles=2)
        for c in COND:
            add(name=f'{c}{r}', kind='br', op=c, mode='D', dst=r, idx=None, cycles=1)
        add(name=f'SHR{r}', kind='sh', op='SHR', mode='-', dst=r, idx=None, cycles=1)
        add(name=f'SHL{r}', kind='sh', op='SHL', mode='-', dst=r, idx=None, cycles=1)
    for i in range(X):
        add(name=f'LDX{i}_D', kind='ldx', op='LDX', mode='D', dst=None, idx=i, cycles=2)
        add(name=f'LDX{i}_I', kind='ldx', op='LDX', mode='I', dst=None, idx=i, cycles=1)
        add(name=f'INX{i}', kind='inx', op='INX', mode='-', dst=None, idx=i, cycles=1)
    for a in range(R):
        for b in range(R):
            if a != b:
                add(name=f'MOV{a}{b}', kind='mov', op='MOV', mode='-', dst=a,
                    src=b, idx=None, cycles=1)
    return pool


# ------------------------------------------------------- abstract evaluation
class St:
    __slots__ = ('r', 'mem')

    def __init__(self, r, mem):
        self.r, self.mem = r, mem

    def key(self):
        return (self.r, tuple(sorted(self.mem.items())))


def step(st, ins, operand, consts):
    r, mem = list(st.r), dict(st.mem)
    k = ins['kind']
    if k == 'mov':
        r[ins['dst']] = r[ins['src']]
        return St(tuple(r), mem)
    if k == 'sh':
        f = (lambda v: v >> 1) if ins['op'] == 'SHR' else (lambda v: (v << 1) & MASK)
        r[ins['dst']] = tuple(f(v) for v in r[ins['dst']])
        return St(tuple(r), mem)
    if k in ('alu', 'st'):
        if ins['mode'] == 'X':
            return None                # indexed forms are for array access only
        if ins['mode'] == 'I':
            if operand not in consts:
                return None
            vals = (consts[operand],) * NTEST
        else:
            if operand not in mem:
                return None
            vals = mem[operand]
        if k == 'st':
            if operand not in SCRATCH:
                return None            # d and s may only be written at the end
            mem[operand] = r[ins['dst']]
            return St(tuple(r), mem)
        f = ALU[ins['op']]
        r[ins['dst']] = tuple(f(a, m) & MASK for a, m in zip(r[ins['dst']], vals))
        return St(tuple(r), mem)
    return None


def start_state(R, imm, seed=12345):
    rnd = random.Random(seed)
    rv = lambda: tuple(rnd.randrange(65536) for _ in range(NTEST))
    consts = {'Kz': 0, 'K1': 1, 'Kimm': imm & MASK, 'Kni': (-imm) & MASK}
    d0, s0 = rv(), rv()
    mem = {'d': d0, 's': s0, 't0': rv(), 't1': rv()}
    for c, v in consts.items():
        mem[c] = (v,) * NTEST
    return St(tuple(rv() for _ in range(R)), mem), consts, d0, s0


def find_seq(pool, iset, consts, start, goal_reg, goal, maxdepth=4, beam=20000):
    """Shortest sequence leaving `goal` in some register, with `s` preserved."""
    usable = [pool[n] for n in iset
              if pool[n]['kind'] in ('alu', 'st', 'sh', 'mov')
              and pool[n]['mode'] != 'X']
    operands = ['d', 's', 't0', 't1'] + list(consts)
    frontier = {start.key(): (start, ())}
    for _ in range(maxdepth):
        nxt = {}
        for _, (st, seq) in frontier.items():
            for ins in usable:
                ops = operands if ins['mode'] not in ('-',) else ['-']
                for opd in ops:
                    ns = step(st, ins, opd, consts)
                    if ns is None:
                        continue
                    if ns.mem['s'] == start.mem['s']:
                        for ri, rv in enumerate(ns.r):
                            if rv == goal:
                                return seq + ((ins['name'], opd),), ri
                    kk = ns.key()
                    if kk not in nxt and kk not in frontier:
                        nxt[kk] = (ns, seq + ((ins['name'], opd),))
            if len(nxt) > beam:
                break
        if not nxt:
            return None, None
        frontier = nxt
    return None, None


def branch_plan(pool, iset, want, reg):
    # An unconditional branch does not depend on the register it nominally
    # tests, so it is available to every register's plan.
    have = {n: COND[pool[n]['op']] for n in iset
            if pool[n]['kind'] == 'br'
            and (pool[n]['dst'] == reg
                 or COND[pool[n]['op']] == frozenset({NEG, ZERO, POS}))}
    if not have:
        return None
    subs = [n for n, c in have.items() if c <= want]
    if subs and frozenset().union(*[have[n] for n in subs]) == want:
        return [(n, 'L') for n in subs]
    comp = frozenset({NEG, ZERO, POS}) - want
    subs = [n for n, c in have.items() if c <= comp]
    cov = frozenset().union(*[have[n] for n in subs]) if subs else frozenset()
    jmps = [n for n, c in have.items() if c == frozenset({NEG, ZERO, POS})]
    if cov == comp and jmps:
        return [(n, 'SKIP') for n in subs] + [(jmps[0], 'L')]
    return None


def compile_all(pool, iset, R):
    """Templates for every virtual operation, or None if the machine cannot."""
    T = {}
    if not any(pool[n]['kind'] == 'st' and pool[n]['mode'] == 'D' for n in iset):
        return None
    st0, c0, d0, s0 = start_state(R, 0)

    def acc(goal, imm=0, depth=4):
        s2, c2, dd, ss = start_state(R, imm)
        return find_seq(pool, iset, c2, s2, None, goal, maxdepth=depth)

    def store(seq, reg):
        nm = f'ST{reg}_D'
        return None if nm not in iset else seq + ((nm, 'd'),)

    for key, goal in (('mov', s0),
                      ('add', tuple((a + b) & MASK for a, b in zip(d0, s0))),
                      ('sub', tuple((a - b) & MASK for a, b in zip(d0, s0)))):
        seq, reg = acc(goal, depth=5 if key != 'mov' else 4)
        if seq is None:
            return None
        t = store(seq, reg)
        if t is None:
            return None
        T[key] = t

    for tag, probe in (('small', 7), ('big', 40000)):
        s2, c2, dd, ss = start_state(R, probe)
        for key, goal in ((f'movi_{tag}', (probe & MASK,) * NTEST),
                          (f'addi_{tag}', tuple((a + probe) & MASK for a in dd)),
                          (f'subi_{tag}', tuple((a - probe) & MASK for a in dd))):
            seq, reg = find_seq(pool, iset, c2, s2, None, goal, maxdepth=4)
            T[key] = store(seq, reg) if seq is not None else None
    for k in ('movi_small', 'movi_big', 'addi_small', 'subi_small'):
        if T.get(k) is None and k != 'movi_small':
            return None
    if T.get('movi_small') is None and T.get('movi_big') is None:
        return None

    seq, reg = acc(s0)
    if seq is None:
        return None
    nm = f'ST{reg}_D'
    if nm not in iset:
        return None
    T['out'] = seq + ((nm, 'port'),)

    for vop, want in (('jz', frozenset({ZERO})), ('jn', frozenset({NEG}))):
        best = None
        for r in range(R):
            sq, rr = find_seq(pool, iset, c0, st0, None, s0, maxdepth=4)
            if sq is None:
                continue
            # the value must land in the register the branch tests
            sq2, rr2 = (sq, rr) if rr == r else (None, None)
            if sq2 is None:
                mv = f'MOV{r}{rr}'
                if mv in iset:
                    sq2 = sq + ((mv, '-'),)
                else:
                    continue
            plan = branch_plan(pool, iset, want, r)
            if plan and (best is None or len(sq2) + len(plan) < len(best[0]) + len(best[1])):
                best = (sq2, plan)
        if best is None:
            return None
        T[vop] = best
    # unconditional jump
    jm = None
    for r in range(R):
        plan = branch_plan(pool, iset, frozenset({NEG, ZERO, POS}), r)
        if plan:
            jm = ((), plan); break
    if jm is None:
        for r in range(R):
            for cname in [n for n in iset if pool[n]['kind'] == 'br'
                          and pool[n]['dst'] == r]:
                for cslot, cls in (('Kz', ZERO), ('K1', POS)):
                    if cls in COND[pool[cname]['op']]:
                        sq, rr = find_seq(pool, iset, c0, st0, None,
                                          (c0[cslot],) * NTEST, maxdepth=3)
                        if sq is not None and rr == r:
                            jm = (sq, [(cname, 'L')]); break
                if jm: break
            if jm: break
    if jm is None:
        return None
    T['jmp'] = jm
    return T


def index_schemes(pool, iset, T, X):
    out = {}
    for i in range(X):
        ldx = [n for n in iset if pool[n]['kind'] == 'ldx' and pool[n]['idx'] == i
               and pool[n]['mode'] == 'D']
        for r in range(R_of(pool)):
            ld = f'LD{r}_X{i}'
            st = f'ST{r}_X{i}'
            sd = f'ST{r}_D'
            if ldx and ld in iset and st in iset and sd in iset:
                out['reg'] = dict(ldx=3, stx=3, cycles_ldx=6, cycles_stx=6,
                                  selfmod=False)
    if T.get('add') is not None:
        n = len(T['add'])
        out['patch'] = dict(ldx=n + 2, stx=n + 2, cycles_ldx=2 * (n + 2),
                            cycles_stx=2 * (n + 2), selfmod=True)
    return out


def R_of(pool):
    return 1 + max((p['dst'] for p in pool.values() if p.get('dst') is not None),
                   default=0)


# ------------------------------------------------------- hardware generation
RA = {'LD': '%s', 'ADD': 'r%d + %s', 'SUB': 'r%d - %s', 'AND': 'r%d & %s',
      'OR': 'r%d | %s', 'XOR': 'r%d ^ %s', 'RSB': '%s - r%d',
      'NAND': '~(r%d & %s)'}
RC = {'JZ': 'z%d', 'JN': 'n%d', 'JP': '(~n%d & ~z%d)', 'JNZ': '~z%d',
      'JNN': '~n%d', 'JLE': '(n%d | z%d)', 'JMP': "1'b1"}


def alu_expr(op, r, src):
    if op == 'LD':
        return src
    if op == 'RSB':
        return f'{src} - r{r}'
    if op == 'NAND':
        return f'~(r{r} & {src})'
    sym = {'ADD': '+', 'SUB': '-', 'AND': '&', 'OR': '|', 'XOR': '^'}[op]
    return f'r{r} {sym} {src}'


def cond_expr(op, r):
    if op == 'JMP':
        return "1'b1"
    return {'JZ': f'z{r}', 'JN': f'n{r}', 'JP': f'(~n{r} & ~z{r})',
            'JNZ': f'~z{r}', 'JNN': f'~n{r}', 'JLE': f'(n{r} | z{r})'}[op]


def gen_rtl(pool, iset, R, X, aw=8):
    order = sorted(iset)
    if len(order) > 16:
        return None
    opc = {n: i for i, n in enumerate(order)}
    d, e = [], []
    for n in order:
        p, o = pool[n], opc[n]
        k, r = p['kind'], p.get('dst')
        if k == 'alu':
            if p['mode'] == 'I':
                d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
                e.append(('D', f"4'd{o}: begin r{r} <= {alu_expr(p['op'], r, 'imm')};"
                               f" pc <= pc + 1'b1; state <= S_D; end"))
            else:
                a = f"xad{p['idx']}" if p['mode'] == 'X' else 'iad'
                d.append(f"4'd{o}: maddr = {a};")
                e.append(('D', f"4'd{o}: state <= S_E;"))
                e.append(('E', f"4'd{o}: r{r} <= {alu_expr(p['op'], r, 'mdin')};"))
        elif k == 'st':
            a = f"xad{p['idx']}" if p['mode'] == 'X' else 'iad'
            d.append(f"4'd{o}: begin maddr = {a}; mwe = 1'b1; mdout = r{r}; end")
            e.append(('D', f"4'd{o}: state <= S_W;"))
        elif k == 'br':
            c = cond_expr(p['op'], r)
            d.append(f"4'd{o}: begin maddr = {c} ? iad : pc; ifetch = 1'b1; end")
            e.append(('D', f"4'd{o}: begin pc <= ({c} ? iad : pc) + 1'b1;"
                           f" state <= S_D; end"))
        elif k == 'ldx':
            if p['mode'] == 'I':
                d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
                e.append(('D', f"4'd{o}: begin x{p['idx']} <= mdin[7:0];"
                               f" pc <= pc + 1'b1; state <= S_D; end"))
            else:
                d.append(f"4'd{o}: maddr = iad;")
                e.append(('D', f"4'd{o}: state <= S_E;"))
                e.append(('E', f"4'd{o}: x{p['idx']} <= mdin[7:0];"))
        elif k == 'inx':
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            e.append(('D', f"4'd{o}: begin x{p['idx']} <= x{p['idx']} + 8'd1;"
                           f" pc <= pc + 1'b1; state <= S_D; end"))
        elif k == 'mov':
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            e.append(('D', f"4'd{o}: begin r{p['dst']} <= r{p['src']};"
                           f" pc <= pc + 1'b1; state <= S_D; end"))
        else:                                       # shifts
            ex = f"{{1'b0, r{r}[15:1]}}" if p['op'] == 'SHR' else f"{{r{r}[14:0], 1'b0}}"
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            e.append(('D', f"4'd{o}: begin r{r} <= {ex};"
                           f" pc <= pc + 1'b1; state <= S_D; end"))
    dcase = '\n                '.join(d)
    scase = '\n                '.join(x for t, x in e if t == 'D')
    ecase = '\n                '.join(x for t, x in e if t == 'E') or "default: ;"
    regs = ' '.join(f'reg [15:0] r{i};' for i in range(R))
    xregs = ' '.join(f'reg [7:0] x{i};' for i in range(X))
    flags = ' '.join(f'wire z{i} = (r{i} == 16\'d0); wire n{i} = r{i}[15];'
                     for i in range(R))
    xads = ' '.join(f'wire [AW-1:0] xad{i} = iad + x{i};' for i in range(X))
    rrst = ' '.join(f'r{i} <= 16\'d0;' for i in range(R))
    xrst = ' '.join(f'x{i} <= 8\'d0;' for i in range(X))
    return f"""// generated: R={R} X={X} set={' '.join(order)}
module gcpu #(parameter AW = {aw}) (
    input wire clk, input wire rst,
    output reg [AW-1:0] maddr, output reg mwe, output reg [15:0] mdout,
    input wire [15:0] mdin, output reg ifetch);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;
    reg [AW-1:0] pc; reg [3:0] op; reg [1:0] state;
    {regs} {xregs}
    wire [3:0] iop = mdin[15:12];
    wire [AW-1:0] iad = mdin[AW-1:0];
    wire [15:0] imm = {{{{4{{mdin[11]}}}}, mdin[11:0]}};
    {flags}
    {xads}
    always @* begin
        maddr = pc; mwe = 1'b0; mdout = r0; ifetch = 1'b0;
        case (state)
            S_D: case (iop)
                {dcase}
                default: maddr = iad;
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin
            pc <= {{AW{{1'b0}}}}; state <= S_F; op <= 4'd0; {rrst} {xrst}
        end else case (state)
            S_D: begin op <= iop; case (iop)
                {scase}
                default: state <= S_E;
            endcase end
            S_E: begin case (op)
                {ecase}
                default: ;
            endcase pc <= pc + 1'b1; state <= S_D; end
            default: begin pc <= pc + 1'b1; state <= S_D; end
        endcase
    end
endmodule
"""


_cache = {}


def core_gates(pool, iset, R, X):
    key = (R, X, tuple(sorted(iset)))
    if key in _cache:
        return _cache[key]
    v = gen_rtl(pool, iset, R, X)
    if v is None:
        return None
    path = f'{BUILD}/arch_tmp.v'
    open(path, 'w').write(v)
    out = subprocess.run(['yosys', '-p',
        f'read_verilog {path}\n hierarchy -top gcpu\n flatten\n proc; opt; fsm;'
        ' opt; memory; opt\n techmap; opt -full\n dfflegalize -cell $_DFF_P_ 0\n'
        ' abc -g NAND\n opt_clean\n stat'], capture_output=True, text=True).stdout
    tail = out[out.rfind('Printing statistics'):]
    g = lambda c: (int(re.search(rf'\$_{c}_\s+(\d+)', tail).group(1))
                   if re.search(rf'\$_{c}_\s+(\d+)', tail) else 0)
    r = g('NAND') + g('NOT') + 6 * g('DFF_P')
    _cache[key] = r
    return r


# --------------------------------------------------------------- the sweep
STATIC = dict(movi=16, out=6, add=8, subi=10, jz=5, jmp=10, ldx=3, mov=10,
              jn=8, sub=4, addi=6, stx=2, halt=1)
NSCALAR, NARRAY, NCONST = 7, 16, 13
G_RAM, G_ROM = 200.0, 4.3


def tlen(T, k):
    if k in ('jz', 'jn', 'jmp'):
        return len(T[k][0]) + len(T[k][1])
    v = T.get(k + '_small') or T.get(k + '_big') if k in ('movi','addi','subi') else T[k]
    return len(v)


def tcyc(pool, T, k):
    if k in ('jz', 'jn', 'jmp'):
        return sum(pool[n]['cycles'] for n, _ in T[k][0]) + len(T[k][1])
    v = T.get(k + '_small') or T.get(k + '_big') if k in ('movi','addi','subi') else T[k]
    return sum(pool[n]['cycles'] for n, _ in v)


def evaluate(pool, iset, R, X, dyn):
    iset = set(iset)
    if len(iset) > 16:
        return None
    T = compile_all(pool, iset, R)
    if T is None:
        return None
    sch = index_schemes(pool, iset, T, X)
    if not sch:
        return None
    core = core_gates(pool, iset, R, X)
    if core is None:
        return None
    best = None
    for how, s in sch.items():
        w = sum(STATIC[k] * tlen(T, k) for k in STATIC
                if k not in ('ldx', 'stx', 'halt'))
        w += STATIC['ldx'] * s['ldx'] + STATIC['stx'] * s['stx'] + 1
        cyc = sum(dyn.get(k, 0) * tcyc(pool, T, k) for k in STATIC
                  if k not in ('ldx', 'stx', 'halt'))
        cyc += dyn.get('ldx', 0) * s['cycles_ldx'] + dyn.get('stx', 0) * s['cycles_stx']
        tot = (core + G_RAM * (w + NCONST + NSCALAR + NARRAY) if s['selfmod']
               else core + G_ROM * (w + NCONST) + G_RAM * (NSCALAR + NARRAY))
        c = dict(total=round(tot), core=core, words=w, cycles=cyc, scheme=how)
        if best is None or c['total'] < best['total']:
            best = c
    return best


ROLES = [
    ('store',   lambda p: p['kind'] == 'st' and p['mode'] == 'D'),
    ('load',    lambda p: p['kind'] == 'alu' and p['op'] == 'LD' and p['mode'] == 'D'),
    ('arith1',  lambda p: p['kind'] == 'alu' and p['op'] in ('SUB', 'RSB') and p['mode'] == 'D'),
    ('arith2',  lambda p: p['kind'] == 'alu' and p['op'] in ('ADD', 'SUB', 'RSB', 'XOR') and p['mode'] == 'D'),
    ('brz',     lambda p: p['kind'] == 'br'),
    ('brn',     lambda p: p['kind'] == 'br'),
    ('brany',   lambda p: p['kind'] == 'br'),
    ('ldx',     lambda p: p['kind'] == 'ldx' and p['mode'] == 'D'),
    ('ldix',    lambda p: p['kind'] == 'alu' and p['op'] == 'LD' and p['mode'] == 'X'),
    ('stix',    lambda p: p['kind'] == 'st' and p['mode'] == 'X'),
]


def seed(pool, rng, size=12, R=1):
    """Random start: one instruction drawn uniformly per structural role.

    Uniform sampling over subsets is hopeless at these pool sizes -- the
    feasible fraction is well under one in a thousand -- so starts are drawn
    uniformly *within* each role a working machine needs. The roles are
    structural, the choices inside them are random, and the local search that
    follows is free to drop or replace anything.
    """
    # With more than one register the roles must agree on which register they
    # use, or nothing composes. Draw the working register uniformly, fill the
    # roles from instructions that target it, and let the climb add the rest.
    home = rng.randrange(R)
    s = set()
    for _, pred in ROLES:
        cands = [n for n, p in pool.items()
                 if pred(p) and p.get('dst') in (home, None)]
        if not cands:
            cands = [n for n, p in pool.items() if pred(p)]
        if cands:
            s.add(rng.choice(cands))
    names = list(pool)
    while len(s) < size and len(s) < 16:
        s.add(rng.choice(names))
    return s


def climb(pool, iset, R, X, dyn, budget=70):
    cur, best, used = set(iset), evaluate(pool, iset, R, X, dyn), 1
    while used < budget:
        moves = [cur | {n} for n in pool if n not in cur and len(cur) < 16] + \
                [cur - {n} for n in cur]
        random.shuffle(moves)
        improved = False
        for m in moves:
            if used >= budget:
                break
            r = evaluate(pool, m, R, X, dyn)
            used += 1
            if r and (best is None or r['total'] < best['total']):
                cur, best, improved = m, r, True
                break
        if not improved:
            break
    return cur, best
