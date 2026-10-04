#!/usr/bin/env python3
"""
Phase 12: evolve the instructions themselves, not a choice among mine.

Every search so far picked from a pool of operations I named. Reverse subtract
is the standing argument that this is not good enough: it beat the hand design,
and it only entered the pool because I deliberately added a primitive no
accumulator machine uses. No curated pool contains the operations nobody has
named.

So here the arithmetic is grown rather than chosen. Each ALU instruction is an
expression tree over the accumulator and the operand, built from
{+ - & | ^ ~ <<1 >>1} and the constants {0, 1, -1}. Crossover swaps subtrees
between machines; mutation rewrites one.

Addressing and control stay structural -- store, indexed load and store, the
index register, and branches on zero, sign and always. That is deliberate: it
is what makes every genome feasible by construction, which is the fix for the
sparse-feasibility problem that made a plain genetic algorithm over instruction
subsets useless in phase 11. The evolution happens where the unnamed operations
would be.
"""
import json
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import BUILD

M = 0xFFFF
NTEST = 6
BIN = ['+', '-', '&', '|', '^']
UN = ['~', '<', '>']                      # ~x, x<<1, x>>1
TERM = ['a', 'm', 'k0', 'k1', 'kn']


# ----------------------------------------------------------- expression trees
def rnd_tree(rng, depth=2):
    if depth == 0 or (depth < 2 and rng.random() < 0.45):
        return (rng.choice(TERM),)
    if rng.random() < 0.25:
        return (rng.choice(UN), rnd_tree(rng, depth - 1))
    return (rng.choice(BIN), rnd_tree(rng, depth - 1), rnd_tree(rng, depth - 1))


def ev(t, a, m):
    h = t[0]
    if h == 'a': return a
    if h == 'm': return m
    if h == 'k0': return 0
    if h == 'k1': return 1
    if h == 'kn': return M
    if h == '~': return (~ev(t[1], a, m)) & M
    if h == '<': return (ev(t[1], a, m) << 1) & M
    if h == '>': return (ev(t[1], a, m) >> 1) & M
    x, y = ev(t[1], a, m), ev(t[2], a, m)
    if h == '+': return (x + y) & M
    if h == '-': return (x - y) & M
    if h == '&': return x & y
    if h == '|': return x | y
    return x ^ y


def vlog(t, src):
    h = t[0]
    if h == 'a': return 'acc'
    if h == 'm': return src
    if h == 'k0': return "16'd0"
    if h == 'k1': return "16'd1"
    if h == 'kn': return "16'hFFFF"
    if h == '~': return '(~%s)' % vlog(t[1], src)
    if h == '<': return '(%s << 1)' % vlog(t[1], src)
    if h == '>': return '(%s >> 1)' % vlog(t[1], src)
    return '(%s %s %s)' % (vlog(t[1], src), h, vlog(t[2], src))


def show(t):
    h = t[0]
    if h in ('a', 'm'): return h
    if h == 'k0': return '0'
    if h == 'k1': return '1'
    if h == 'kn': return '-1'
    if h == '~': return '~%s' % show(t[1])
    if h == '<': return '(%s<<1)' % show(t[1])
    if h == '>': return '(%s>>1)' % show(t[1])
    return '(%s%s%s)' % (show(t[1]), h, show(t[2]))


def nodes(t):
    out = [t]
    for c in t[1:]:
        if isinstance(c, tuple): out += nodes(c)
    return out


def replace(t, old, new):
    if t is old: return new
    if len(t) == 1: return t
    return (t[0],) + tuple(replace(c, old, new) for c in t[1:])


def depends_on_m(t):
    return any(n[0] == 'm' for n in nodes(t))


# -------------------------------------------------------------- the machine
# structural instructions, present in every genome
FIXED = ['ST_D', 'ST_X', 'LDX_D', 'LDAX', 'JZ', 'JN', 'JMP']
CYC = dict(ST_D=2, ST_X=2, LDX_D=2, LDAX=2, JZ=1, JN=1, JMP=1)


class Genome:
    def __init__(self, alus):
        self.alus = alus              # list of (tree, mode) with mode in 'DI'

    def key(self):
        return tuple((show(t), m) for t, m in self.alus)


def rnd_genome(rng, k):
    alus = []
    for _ in range(k):
        t = rnd_tree(rng, 2)
        while not depends_on_m(t):
            t = rnd_tree(rng, 2)
        alus.append((t, rng.choice('DDDI')))
    return Genome(alus)


# ------------------------------------------------------------- the compiler
class St:
    __slots__ = ('acc', 'mem')
    def __init__(self, acc, mem): self.acc, self.mem = acc, mem
    def key(self): return (self.acc, tuple(sorted(self.mem.items())))


def start(rng_seed, imm):
    r = random.Random(rng_seed)
    rv = lambda: tuple(r.randrange(65536) for _ in range(NTEST))
    consts = {'Kz': 0, 'K1': 1, 'Kimm': imm & M, 'Kni': (-imm) & M}
    d0, s0 = rv(), rv()
    mem = {'d': d0, 's': s0, 't0': rv()}
    for c, v in consts.items(): mem[c] = (v,) * NTEST
    return St(rv(), mem), consts, d0, s0


def seq_for(g, consts, st0, goal, maxdepth=4, beam=12000):
    """Shortest sequence of evolved instructions leaving `goal` in the accumulator."""
    operands = ['d', 's', 't0'] + list(consts)
    frontier = {st0.key(): (st0, ())}
    for _ in range(maxdepth):
        nxt = {}
        for _, (s, seq) in frontier.items():
            for i, (t, mode) in enumerate(g.alus):
                for o in operands:
                    if mode == 'I':
                        if o not in consts: continue
                        vals = (consts[o],) * NTEST
                    else:
                        if o not in s.mem: continue
                        vals = s.mem[o]
                    acc = tuple(ev(t, a, mv) for a, mv in zip(s.acc, vals))
                    ns = St(acc, s.mem)
                    if acc == goal and ns.mem['s'] == st0.mem['s']:
                        return seq + (('A%d' % i, o),)
                    kk = ns.key()
                    if kk not in nxt and kk not in frontier:
                        nxt[kk] = (ns, seq + (('A%d' % i, o),))
            # a store to scratch is also a move
            for i, (t, mode) in enumerate(g.alus):
                pass
            s2 = St(s.acc, dict(s.mem, t0=s.acc))
            kk = s2.key()
            if kk not in nxt and kk not in frontier:
                nxt[kk] = (s2, seq + (('ST_D', 't0'),))
            if len(nxt) > beam: break
        if not nxt: return None
        frontier = nxt
    return None


def compile_all(g):
    T = {}
    st0, c0, d0, s0 = start(7, 0)
    def want(goal, imm=0, depth=4):
        s, c, dd, ss = start(7, imm)
        return seq_for(g, c, s, goal, maxdepth=depth)
    for k, goal in (('mov', s0),
                    ('add', tuple((a + b) & M for a, b in zip(d0, s0))),
                    ('sub', tuple((a - b) & M for a, b in zip(d0, s0)))):
        q = want(goal, depth=4 if k == 'mov' else 5)
        if q is None: return None
        T[k] = q + (('ST_D', 'd'),)
    for tag, probe in (('small', 7), ('big', 40000)):
        s, c, dd, ss = start(7, probe)
        for k, goal in ((f'movi_{tag}', (probe & M,) * NTEST),
                        (f'addi_{tag}', tuple((a + probe) & M for a in dd)),
                        (f'subi_{tag}', tuple((a - probe) & M for a in dd))):
            q = seq_for(g, c, s, goal, maxdepth=4)
            T[k] = q + (('ST_D', 'd'),) if q else None
    for k in ('movi_big', 'addi_small', 'subi_small'):
        if T.get(k) is None: return None
    q = want(s0)
    if q is None: return None
    T['out'] = q + (('ST_D', 'port'),)
    for k in ('jz', 'jn'):
        T[k] = (want(s0), [(k.upper(), 'L')])
        if T[k][0] is None: return None
    T['jmp'] = ((), [('JMP', 'L')])
    return T


# ------------------------------------------------------------------- cost
STATIC = dict(movi=16, out=6, add=8, subi=10, jz=5, jmp=10, ldx=3, mov=10,
              jn=8, sub=4, addi=6, stx=2, halt=1)
DYN = dict(movi=28, out=123, add=379, subi=351, jz=160, jmp=283, ldx=99,
           mov=284, jn=354, sub=85, addi=145, stx=71, halt=1)
G_RAM, G_ROM, NK, NDATA = 200.0, 4.3, 13, 23
_cache = {}


def core_gates(g):
    k = g.key()
    if k in _cache: return _cache[k]
    names = ['A%d' % i for i in range(len(g.alus))] + FIXED
    if len(names) > 16: return None
    opc = {n: i for i, n in enumerate(names)}
    d, sq, ex = [], [], []
    for i, (t, mode) in enumerate(g.alus):
        o = opc['A%d' % i]
        if mode == 'I':
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin acc <= {vlog(t,'imm')}; pc <= pc + 1'b1;"
                      f" state <= S_D; end")
        else:
            d.append(f"4'd{o}: maddr = iad;")
            sq.append(f"4'd{o}: state <= S_E;")
            ex.append(f"4'd{o}: acc <= {vlog(t,'mdin')};")
    o = opc['ST_D']; d.append(f"4'd{o}: begin maddr = iad; mwe = 1'b1; end"); sq.append(f"4'd{o}: state <= S_W;")
    o = opc['ST_X']; d.append(f"4'd{o}: begin maddr = xad; mwe = 1'b1; end"); sq.append(f"4'd{o}: state <= S_W;")
    o = opc['LDX_D']; d.append(f"4'd{o}: maddr = iad;"); sq.append(f"4'd{o}: state <= S_E;"); ex.append(f"4'd{o}: xreg <= mdin[7:0];")
    o = opc['LDAX']; d.append(f"4'd{o}: maddr = xad;"); sq.append(f"4'd{o}: state <= S_E;"); ex.append(f"4'd{o}: acc <= mdin;")
    for nm, c in (('JZ', 'zf'), ('JN', 'nf'), ('JMP', "1'b1")):
        o = opc[nm]
        d.append(f"4'd{o}: begin maddr = {c} ? iad : pc; ifetch = 1'b1; end")
        sq.append(f"4'd{o}: begin pc <= ({c} ? iad : pc) + 1'b1; state <= S_D; end")
    nl = '\n                '
    v = f"""module gcpu #(parameter AW = 8) (
    input wire clk, input wire rst, output reg [AW-1:0] maddr, output reg mwe,
    output reg [15:0] mdout, input wire [15:0] mdin, output reg ifetch);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;
    reg [AW-1:0] pc; reg [15:0] acc; reg [3:0] op; reg [1:0] state; reg [7:0] xreg;
    wire [3:0] iop = mdin[15:12];
    wire [AW-1:0] iad = mdin[AW-1:0];
    wire [15:0] imm = {{{{4{{mdin[11]}}}}, mdin[11:0]}};
    wire zf = (acc == 16'd0); wire nf = acc[15];
    wire [AW-1:0] xad = iad + xreg;
    always @* begin
        maddr = pc; mwe = 1'b0; mdout = acc; ifetch = 1'b0;
        case (state)
            S_D: case (iop)
                {nl.join(d)}
                default: maddr = iad;
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin pc <= 0; acc <= 0; state <= S_F; op <= 0; xreg <= 0;
        end else case (state)
            S_D: begin op <= iop; case (iop)
                {nl.join(sq)}
                default: state <= S_E;
            endcase end
            S_E: begin case (op)
                {nl.join(ex)}
                default: ;
            endcase pc <= pc + 1'b1; state <= S_D; end
            default: begin pc <= pc + 1'b1; state <= S_D; end
        endcase
    end
endmodule
"""
    p = f'{BUILD}/gp_tmp.v'
    open(p, 'w').write(v)
    out = subprocess.run(['yosys', '-p',
        f'read_verilog {p}\n hierarchy -top gcpu\n flatten\n proc; opt; fsm; opt;'
        ' memory; opt\n techmap; opt -full\n dfflegalize -cell $_DFF_P_ 0\n'
        ' abc -g NAND\n opt_clean\n stat'], capture_output=True, text=True).stdout
    tail = out[out.rfind('Printing statistics'):]
    gg = lambda c: (int(re.search(rf'\$_{c}_\s+(\d+)', tail).group(1))
                    if re.search(rf'\$_{c}_\s+(\d+)', tail) else 0)
    r = gg('NAND') + gg('NOT') + 6 * gg('DFF_P')
    _cache[k] = r
    return r


def cyc_of(g, nm):
    if nm.startswith('A'):
        return 1 if g.alus[int(nm[1:])][1] == 'I' else 2
    return CYC[nm]


def fitness(g):
    T = compile_all(g)
    if T is None: return None
    L = lambda k: (len(T[k][0]) + len(T[k][1])) if k in ('jz','jn','jmp') else \
        len(T.get(k+'_small') or T.get(k+'_big')) if k in ('movi','addi','subi') else len(T[k])
    C = lambda k: (sum(cyc_of(g,n) for n,_ in T[k][0]) + len(T[k][1])) if k in ('jz','jn','jmp') else \
        sum(cyc_of(g,n) for n,_ in (T.get(k+'_small') or T.get(k+'_big')
            if k in ('movi','addi','subi') else T[k]))
    words = sum(STATIC[k]*L(k) for k in STATIC if k not in ('ldx','stx','halt'))
    words += STATIC['ldx']*3 + STATIC['stx']*3 + 1
    cycles = sum(DYN[k]*C(k) for k in DYN if k not in ('ldx','stx','halt'))
    cycles += DYN['ldx']*6 + DYN['stx']*6
    core = core_gates(g)
    if core is None: return None
    return dict(total=round(core + G_ROM*(words+NK) + G_RAM*NDATA),
                core=core, words=words, cycles=cycles)


# ---------------------------------------------------------------- evolution
def mutate(g, rng):
    alus = list(g.alus)
    i = rng.randrange(len(alus))
    t, mode = alus[i]
    r = rng.random()
    if r < 0.15:
        alus[i] = (t, 'I' if mode == 'D' else 'D')
    elif r < 0.55:
        ns = nodes(t); old = rng.choice(ns)
        alus[i] = (replace(t, old, rnd_tree(rng, 1)), mode)
    else:
        nt = rnd_tree(rng, 2)
        while not depends_on_m(nt): nt = rnd_tree(rng, 2)
        alus[i] = (nt, mode)
    return Genome(alus)


def cross(a, b, rng):
    k = len(a.alus)
    alus = [a.alus[i] if rng.random() < 0.5 else b.alus[i] for i in range(k)]
    if rng.random() < 0.5:                       # subtree crossover
        i = rng.randrange(k)
        t1, m1 = alus[i]; t2, _ = b.alus[rng.randrange(k)]
        alus[i] = (replace(t1, rng.choice(nodes(t1)), rng.choice(nodes(t2))), m1)
    return Genome(alus)
