#!/usr/bin/env python3
"""
Phase 7: search the instruction-set space instead of picking candidates.

The objection this answers: every design compared in phases 1-6 was one I chose,
and the ones I chose are the branches that historically existed -- SUBLEQ, an
accumulator machine, a PDP-8-alike, Jones's MOVE machine. A model that has read
the history of computer architecture proposing those four and then announcing
that one of them wins is not a search, it is a recollection.

So: enumerate the pool mechanically, generate the code mechanically, generate
the hardware mechanically, and let a search pick the winner.

WHAT IS MECHANICAL HERE
  * The instruction pool is the cross product {operation} x {addressing mode}
    plus the cross product {branch} x {condition}. Nothing is included because
    a real machine had it, and nothing is excluded because no real machine did.
  * Code generation is a breadth-first search over instruction sequences, per
    instruction set, checked against a reference. There are no hand-written
    macro expansions: the compiler rediscovers "a + b = a - (0 - b)" for
    machines that lack ADD, or fails to and reports the set unusable.
  * Branch sequences are found by covering the {negative, zero, positive}
    outcome classes with whatever conditional jumps the set happens to contain.
  * The Verilog is emitted from the instruction list, so the decoder matches the
    set exactly and is synthesised for real.

WHAT IS STILL MINE, AND THEREFORE STILL A BIAS
  * The skeleton: one accumulator, an optional index register, memory operands,
    a single-port synchronous memory, a 16-bit word, a 4-bit opcode field.
  * The two strategies offered for indexed access (an index register, or
    patching an instruction in place). The search chooses between them; it did
    not invent them.
  * The benchmark suite and the gate-built memory model.
These are stated rather than hidden, and the last section of the report says
what each is worth.
"""
import itertools
import random

MASK = 0xFFFF
S = lambda v: v - 0x10000 if v & 0x8000 else v


# ---------------------------------------------------------------- the pool
# Built as cross products. `mode`: D = direct, I = immediate, X = indexed.
ALU = {
    'LD':  lambda a, m: m,
    # RSB and NAND are in the pool precisely because no historical accumulator
    # machine has them: the pool should not be a list of things that existed
    'RSB': lambda a, m: (m - a) & MASK,
    'NAND': lambda a, m: (~(a & m)) & MASK,
    'ADD': lambda a, m: (a + m) & MASK,
    'SUB': lambda a, m: (a - m) & MASK,
    'AND': lambda a, m: a & m,
    'OR':  lambda a, m: a | m,
    'XOR': lambda a, m: a ^ m,
}
# outcome classes a conditional branch can test
NEG, ZERO, POS = 'n', 'z', 'p'
COND = {
    'JMP': frozenset({NEG, ZERO, POS}),
    'JLE': frozenset({NEG, ZERO}),      # SUBLEQ's own condition -- omitted from
                                        # the first pool, which claimed to be
                                        # exhaustive and was not

    'JZ':  frozenset({ZERO}),
    'JN':  frozenset({NEG}),
    'JP':  frozenset({POS}),
    'JNZ': frozenset({NEG, POS}),
    'JNN': frozenset({ZERO, POS}),
}


def build_pool():
    pool = []
    for op in ALU:
        for mode in ('D', 'I', 'X'):
            pool.append(dict(name=f'{op}_{mode}', kind='alu', op=op, mode=mode,
                             cycles=1 if mode == 'I' else 2))
    for mode in ('D', 'X'):
        pool.append(dict(name=f'ST_{mode}', kind='st', op='ST', mode=mode,
                         cycles=2))
    for c in COND:
        pool.append(dict(name=c, kind='br', op=c, mode='D', cycles=1))
    for n, k in (('LDX_D', 'D'), ('LDX_I', 'I')):
        pool.append(dict(name=n, kind='ldx', op='LDX', mode=k,
                         cycles=2 if k == 'D' else 1))
    pool.append(dict(name='INX', kind='inx', op='INX', mode='-', cycles=1))
    for n in ('SHR', 'SHL'):
        pool.append(dict(name=n, kind='sh', op=n, mode='-', cycles=1))
    # subroutine support: a link register, one level deep
    pool.append(dict(name='CALL', kind='call', op='CALL', mode='D', cycles=1))
    pool.append(dict(name='RET', kind='ret', op='RET', mode='-', cycles=1))
    return {p['name']: p for p in pool}


POOL = build_pool()
NEEDS_X = {'LD_X', 'ADD_X', 'SUB_X', 'AND_X', 'OR_X', 'XOR_X', 'ST_X',
           'LDX_D', 'LDX_I', 'INX'}


# ------------------------------------------------- abstract machine for search
# Slots the generated code may touch. Constants are read-only.
SLOTS = ['d', 's', 't0', 't1']
CONSTS = {'Kz': 0, 'K1': 1, 'Kimm': None, 'Kni': None}   # Kimm filled per call
NTEST = 4


class Abs:
    """Machine state over NTEST random test vectors, used to verify sequences."""
    __slots__ = ('acc', 'x', 'mem')

    def __init__(self, acc, x, mem):
        self.acc, self.x, self.mem = acc, x, mem

    def key(self):
        return (self.acc, self.x, tuple(sorted(self.mem.items())))


SCRATCH = ('t0', 't1')


def step(st, ins, operand, consts):
    """Apply one instruction; returns a new Abs or None if not applicable."""
    acc, x, mem = st.acc, st.x, dict(st.mem)
    k = ins['kind']
    if k in ('alu', 'st'):
        if ins['mode'] == 'I':
            if operand not in consts:
                return None
            vals = (consts[operand],) * NTEST
        else:
            if operand not in mem:
                return None
            vals = mem[operand]
        if k == 'st':
            # only scratch may be written mid-sequence: writing d or s early
            # would break when a call site aliases them (the suite has `add p,p`)
            if operand not in SCRATCH:
                return None
            mem[operand] = acc
            return Abs(acc, x, mem)
        f = ALU[ins['op']]
        return Abs(tuple(f(a, m) & MASK for a, m in zip(acc, vals)), x, mem)
    if k == 'ldx':
        return None          # index handling is done by the ldx/stx schemes
    if k == 'sh':
        f = (lambda v: v >> 1) if ins['op'] == 'SHR' else (lambda v: (v << 1) & MASK)
        return Abs(tuple(f(a) for a in acc), x, mem)
    return None


def search_acc(iset, consts, start, goal, maxdepth=4, beam=20000):
    """Shortest instruction sequence leaving `goal(vec_index)` in the accumulator.

    Breadth-first over (instruction, operand) pairs, de-duplicated by abstract
    state. This is what replaces hand-written macro expansion.
    """
    # indexed forms are excluded here: their address depends on X, which scalar
    # code does not control. They are used only by the array-access schemes.
    usable = [POOL[n] for n in iset
              if POOL[n]['kind'] in ('alu', 'st', 'sh') and POOL[n]['mode'] != 'X']
    operands = SLOTS + list(consts)
    frontier = {start.key(): (start, ())}
    for _ in range(maxdepth):
        nxt = {}
        for _, (st, seq) in frontier.items():
            for ins in usable:
                for opd in (operands if ins['mode'] != '-' else ['-']):
                    ns = step(st, ins, opd, consts)
                    if ns is None:
                        continue
                    if tuple(ns.acc) == goal and ns.mem['s'] == start.mem['s']:
                        return seq + ((ins['name'], opd),)
                    kk = ns.key()
                    if kk not in nxt and kk not in frontier:
                        nxt[kk] = (ns, seq + ((ins['name'], opd),))
            if len(nxt) > beam:
                break
        if not nxt:
            return None
        frontier = nxt
    return None


def branch_plan(iset, want):
    """Cover the outcome classes in `want` with the available conditional jumps.

    Returns a list of ('jump', cond, target) where target is 'L' (taken) or
    'SKIP', or None if the set cannot express the predicate.
    """
    have = {n: COND[n] for n in iset if n in COND}
    if not have:
        return None
    # direct: chain jumps whose class set is a subset of `want`
    subs = [n for n, c in have.items() if c <= want]
    if frozenset().union(*[have[n] for n in subs]) == want if subs else False:
        return [(n, 'L') for n in subs]
    # inverted: jump over to SKIP for the complement, then an unconditional jump
    comp = frozenset({NEG, ZERO, POS}) - want
    subs = [n for n, c in have.items() if c <= comp]
    cov = frozenset().union(*[have[n] for n in subs]) if subs else frozenset()
    if cov == comp and 'JMP' in have:
        return [(n, 'SKIP') for n in subs] + [('JMP', 'L')]
    return None


# --------------------------------------------------------------- compilation
def start_state(imm=0):
    consts = {'Kz': 0, 'K1': 1, 'Kimm': imm & MASK, 'Kni': (-imm) & MASK}
    rnd = random.Random(12345)
    rv = lambda: tuple(rnd.randrange(65536) for _ in range(NTEST))
    d0, s0 = rv(), rv()
    # the accumulator and the scratch cells hold unknown values on entry, so a
    # sequence cannot quietly rely on acc being zero
    acc0, mem = rv(), {'d': d0, 's': s0, 't0': rv(), 't1': rv()}
    for c, v in consts.items():
        mem[c] = (v,) * NTEST
    return Abs(acc0, (0,) * NTEST, mem), consts, d0, s0


def compile_templates(iset, partial=False):
    """Find a native sequence for every virtual operation, or fail."""
    T = {}
    st, consts, d0, s0 = start_state(0)

    def acc_seq(goal, imm=None, depth=4):
        s2, c2, dd, ss = start_state(imm if imm is not None else 0)
        return search_acc(iset, c2, s2, goal, maxdepth=depth)

    miss = []
    if 'ST_D' not in iset:
        if not partial:
            return None                               # cannot write memory
        miss.append('ST_D')
    st0, c0, d0, s0 = start_state(0)

    seq = acc_seq(s0)
    if seq is None:
        miss.append('mov')
        if not partial:
            return None
    else:
        T['mov'] = seq + (('ST_D', 'd'),)

    # arithmetic may need five instructions on a set without ADD, where the
    # compiler has to find a + b = a - (0 - b) for itself
    seq = acc_seq(tuple((a + b) & MASK for a, b in zip(d0, s0)), depth=5)
    if seq is None:
        miss.append('add')
        if not partial:
            return None
    else:
        T['add'] = seq + (('ST_D', 'd'),)

    seq = acc_seq(tuple((a - b) & MASK for a, b in zip(d0, s0)), depth=5)
    if seq is None:
        miss.append('sub')
        if not partial:
            return None
    else:
        T['sub'] = seq + (('ST_D', 'd'),)

    # immediates: one template for values a 12-bit signed field can hold, one for
    # the rest (which must come from a constant word)
    for tag, probe in (('small', 7), ('big', 40000)):
        s2, c2, dd, ss = start_state(probe)
        g = (probe & MASK,) * NTEST
        sq = search_acc(iset, c2 if tag == 'small' else
                        {k: v for k, v in c2.items() if k not in ('Kimm',)} |
                        {'Kimm': probe & MASK}, s2, g, maxdepth=3)
        if sq is None and tag == 'small' and not partial:
            return None
        T['movi_' + tag] = (sq + (('ST_D', 'd'),)) if sq else None
        gi = tuple((a + probe) & MASK for a in dd)
        sq = search_acc(iset, c2, s2, gi, maxdepth=4)
        T['addi_' + tag] = (sq + (('ST_D', 'd'),)) if sq else None
        gs = tuple((a - probe) & MASK for a in dd)
        sq = search_acc(iset, c2, s2, gs, maxdepth=4)
        T['subi_' + tag] = (sq + (('ST_D', 'd'),)) if sq else None
    for k in ('movi_big', 'addi_small', 'subi_small'):
        if T.get(k) is None:
            miss.append(k)
            if not partial:
                return None

    # XOR: the firmware benchmark of phase 10 needs it for its CRC; the
    # original five-program suite never did, which is why phase 2 concluded
    # logic instructions were dead weight.
    q = acc_seq(tuple(a ^ b for a, b in zip(d0, s0)), depth=5)
    T['xor'] = q + (('ST_D', 'd'),) if q is not None else None

    o = acc_seq(s0)
    if o is None:
        miss.append('out')
        if not partial:
            return None
    else:
        T['out'] = o + (('ST_D', 'port'),)

    # control flow: cover the outcome classes with whatever jumps exist
    load_s = acc_seq(s0)
    for vop, want in (('jz', frozenset({ZERO})), ('jn', frozenset({NEG}))):
        plan = branch_plan(iset, want)
        if plan is None or load_s is None:
            miss.append(vop)
            if not partial:
                return None
        else:
            T[vop] = (load_s, plan)
    if 'JMP' in iset:
        T['jmp'] = ((), [('JMP', 'L')])
    else:
        found = None
        for cname in [c for c in COND if c in iset]:
            for cslot, cls in (('Kz', ZERO), ('K1', POS)):
                if cls in COND[cname]:
                    sq = acc_seq((c0[cslot],) * NTEST)
                    if sq is not None:
                        found = (sq, [(cname, 'L')]); break
            if found: break
        if found is None:
            miss.append('jmp')
            if not partial:
                return None
        else:
            T['jmp'] = found
    return (T, miss) if partial else T


def index_schemes(iset, T):
    """How this instruction set can reach A[i]: index register, or self-patching.

    Both schemes are offered to every set; the search decides which is cheaper,
    and a set that can do neither cannot run the benchmark.
    """
    out = {}
    if ('LD_X' in iset or 'ST_X' in iset) and ('LDX_D' in iset):
        if 'LD_X' in iset and 'ST_X' in iset:
            out['reg'] = dict(ldx=3, stx=3, cycles_ldx=6, cycles_stx=6,
                              selfmod=False)
    # self-patching works for any set that can add to a value and store it
    if T.get('add') is not None:
        n = len(T['add'])
        out['patch'] = dict(ldx=n + 2, stx=n + 2,
                            cycles_ldx=2 * (n + 2), cycles_stx=2 * (n + 2),
                            selfmod=True)
    return out


# ------------------------------------------------------- hardware generation
RTL_ALU = {'LD': 'mdin', 'ADD': 'acc + mdin', 'SUB': 'acc - mdin',
           'AND': 'acc & mdin', 'OR': 'acc | mdin', 'XOR': 'acc ^ mdin',
           'RSB': 'mdin - acc', 'NAND': '~(acc & mdin)'}
RTL_ALU_I = {'LD': 'imm', 'ADD': 'acc + imm', 'SUB': 'acc - imm',
             'AND': 'acc & imm', 'OR': 'acc | imm', 'XOR': 'acc ^ imm',
             'RSB': 'imm - acc', 'NAND': '~(acc & imm)'}
RTL_COND = {'JZ': 'zf', 'JN': 'nf', 'JP': '(~nf & ~zf)', 'JNZ': '~zf',
            'JNN': '~nf', 'JLE': '(nf | zf)', 'JMP': "1'b1"}


def gen_rtl(iset, aw=8):
    """Emit a CPU for exactly this instruction set. Opcodes assigned in order."""
    order = sorted(iset)
    if len(order) > 16:
        return None
    opc = {n: i for i, n in enumerate(order)}
    use_x = any(n in NEEDS_X for n in order)
    use_lr = any(POOL[n]['kind'] in ('call', 'ret') for n in order)
    d_case, e_case, seq_d = [], [], []
    for n in order:
        p, o = POOL[n], opc[n]
        if p['kind'] == 'alu':
            if p['mode'] == 'I':
                d_case.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
                seq_d.append(f"4'd{o}: begin acc <= {RTL_ALU_I[p['op']]};"
                             f" pc <= pc + 1'b1; state <= S_D; end")
            else:
                a = 'xad' if p['mode'] == 'X' else 'iad'
                d_case.append(f"4'd{o}: maddr = {a};")
                seq_d.append(f"4'd{o}: state <= S_E;")
                e_case.append(f"4'd{o}: acc <= {RTL_ALU[p['op']]};")
        elif p['kind'] == 'st':
            a = 'xad' if p['mode'] == 'X' else 'iad'
            d_case.append(f"4'd{o}: begin maddr = {a}; mwe = 1'b1; end")
            seq_d.append(f"4'd{o}: state <= S_W;")
        elif p['kind'] == 'br':
            c = RTL_COND[p['op']]
            d_case.append(f"4'd{o}: begin maddr = {c} ? iad : pc;"
                          f" ifetch = 1'b1; end")
            seq_d.append(f"4'd{o}: begin pc <= ({c} ? iad : pc) + 1'b1;"
                         f" state <= S_D; end")
        elif p['kind'] == 'call':
            d_case.append(f"4'd{o}: begin maddr = iad; ifetch = 1'b1; end")
            seq_d.append(f"4'd{o}: begin lr <= pc; pc <= iad + 1'b1;"
                         f" state <= S_D; end")
        elif p['kind'] == 'ret':
            d_case.append(f"4'd{o}: begin maddr = lr; ifetch = 1'b1; end")
            seq_d.append(f"4'd{o}: begin pc <= lr + 1'b1; state <= S_D; end")
        elif p['kind'] == 'ldx':
            if p['mode'] == 'I':
                d_case.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
                seq_d.append(f"4'd{o}: begin xreg <= mdin[7:0];"
                             f" pc <= pc + 1'b1; state <= S_D; end")
            else:
                d_case.append(f"4'd{o}: maddr = iad;")
                seq_d.append(f"4'd{o}: state <= S_E;")
                e_case.append(f"4'd{o}: xreg <= mdin[7:0];")
        elif p['kind'] == 'inx':
            d_case.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            seq_d.append(f"4'd{o}: begin xreg <= xreg + 8'd1;"
                         f" pc <= pc + 1'b1; state <= S_D; end")
        else:                                     # shifts
            e = "{1'b0, acc[15:1]}" if p['op'] == 'SHR' else "{acc[14:0], 1'b0}"
            d_case.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            seq_d.append(f"4'd{o}: begin acc <= {e};"
                         f" pc <= pc + 1'b1; state <= S_D; end")
    nl = '\n                '
    XRST = "xreg <= 8'd0;" if use_x else ''
    LRRST = "lr <= {AW{1'b0}};" if use_lr else ''
    return f"""// generated for instruction set: {' '.join(order)}
module gcpu #(parameter AW = {aw}) (
    input wire clk, input wire rst,
    output reg [AW-1:0] maddr, output reg mwe, output reg [15:0] mdout,
    input wire [15:0] mdin, output reg ifetch);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;
    reg [AW-1:0] pc; reg [15:0] acc; reg [3:0] op; reg [1:0] state;
    {'reg [7:0] xreg;' if use_x else ''}
    {f'reg [{{AW}}-1:0] lr;' if use_lr else ''}
    wire [3:0] iop = mdin[15:12];
    wire [AW-1:0] iad = mdin[AW-1:0];
    wire [15:0] imm = {{{{4{{mdin[11]}}}}, mdin[11:0]}};
    wire zf = (acc == 16'd0); wire nf = acc[15];
    {'wire [AW-1:0] xad = iad + xreg;' if use_x else ''}
    always @* begin
        maddr = pc; mwe = 1'b0; mdout = acc; ifetch = 1'b0;
        case (state)
            S_D: case (iop)
                {nl.join(d_case)}
                default: maddr = iad;
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin
            pc <= {{AW{{1'b0}}}}; acc <= 16'd0; state <= S_F; op <= 4'd0;
            {XRST} {LRRST}
        end else case (state)
            S_D: begin op <= iop; case (iop)
                {nl.join(seq_d)}
                default: state <= S_E;
            endcase end
            S_E: begin case (op)
                {nl.join(e_case) if e_case else "default: acc <= acc;"}
                default: acc <= acc;
            endcase pc <= pc + 1'b1; state <= S_D; end
            default: begin pc <= pc + 1'b1; state <= S_D; end
        endcase
    end
endmodule
"""


# ------------------------------------------------------------ cost and search
import os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build'); os.makedirs(BUILD, exist_ok=True)

# call-site counts (static) and execution counts (dynamic) of the benchmark,
# taken from the suite itself rather than assumed
STATIC = dict(movi=16, out=6, add=8, subi=10, jz=5, jmp=10, ldx=3, mov=10,
              jn=8, sub=4, addi=6, stx=2, halt=1)
NSCALAR, NARRAY = 7, 16
# measured per-word costs from phases 1-4
G_RAM, G_ROM = 200.0, 4.3
_gate_cache = {}


def core_gates(iset):
    key = tuple(sorted(iset))
    if key in _gate_cache:
        return _gate_cache[key]
    v = gen_rtl(iset)
    if v is None:
        return None
    path = f'{BUILD}/gcpu_tmp.v'
    open(path, 'w').write(v)
    script = (f'read_verilog {path}\n hierarchy -top gcpu\n flatten\n'
              ' proc; opt; fsm; opt; memory; opt\n techmap; opt -full\n'
              ' dfflegalize -cell $_DFF_P_ 0\n abc -g NAND\n opt_clean\n stat')
    out = subprocess.run(['yosys', '-p', script], capture_output=True,
                         text=True).stdout
    tail = out[out.rfind('Printing statistics'):]
    g = lambda c: (int(re.search(rf'\$_{c}_\s+(\d+)', tail).group(1))
                   if re.search(rf'\$_{c}_\s+(\d+)', tail) else 0)
    r = g('NAND') + g('NOT') + 6 * g('DFF_P')
    _gate_cache[key] = r
    return r


def evaluate(iset, dyn):
    """Total gates for an instruction set, or None if it cannot run the suite."""
    iset = set(iset)
    if len(iset) > 16:
        return None
    T = compile_templates(iset)
    if T is None:
        return None
    sch = index_schemes(iset, T)
    if not sch:
        return None
    best = None
    for how, s in sch.items():
        words = sum(STATIC[k] * tlen(T, k) for k in STATIC if k not in
                    ('ldx', 'stx', 'halt'))
        words += STATIC['ldx'] * s['ldx'] + STATIC['stx'] * s['stx'] + 1
        consts = 12
        data = NSCALAR + NARRAY
        cyc = sum(dyn.get(k, 0) * tcyc(T, k) for k in STATIC if k not in
                  ('ldx', 'stx', 'halt'))
        cyc += dyn.get('ldx', 0) * s['cycles_ldx'] + dyn.get('stx', 0) * s['cycles_stx']
        core = core_gates(iset)
        if core is None:
            return None
        if s['selfmod']:
            total = core + G_RAM * (words + consts + data)
        else:
            total = core + G_ROM * (words + consts) + G_RAM * data
        cand = dict(total=round(total), core=core, words=words + consts + data,
                    cycles=cyc, scheme=how, selfmod=s['selfmod'])
        if best is None or cand['total'] < best['total']:
            best = cand
    return best


def tlen(T, k):
    """Words occupied by one call site of virtual operation k."""
    if k in ('jz', 'jn', 'jmp'):
        seq, plan = T[k]
        return len(seq) + len(plan)
    if k in ('movi', 'addi', 'subi'):
        v = T.get(k + '_small') or T.get(k + '_big')
    else:
        v = T[k]
    return len(v)


def tcyc(T, k):
    """Cycles for one execution of virtual operation k."""
    if k in ('jz', 'jn', 'jmp'):
        seq, plan = T[k]
        return sum(POOL[n]['cycles'] for n, _ in seq) + len(plan)
    if k in ('movi', 'addi', 'subi'):
        v = T.get(k + '_small') or T.get(k + '_big')
    else:
        v = T[k]
    return sum(POOL[n]['cycles'] for n, _ in v)


NREQ = 11


def feasibility(iset):
    """How many virtual operations this set can express: a gradient out of the
    infeasible region, so local search is not stranded on a plateau."""
    T, miss = compile_templates(set(iset), partial=True)
    sc = NREQ - len(miss)
    if not index_schemes(set(iset), T):
        sc -= 1
    return sc


def hill_climb(dyn, start, rng, budget):
    """Local search: add, drop or swap one instruction at a time."""
    cur = set(start)
    best = evaluate(cur, dyn)
    used = 1
    while used < budget:
        moves = []
        for n in POOL:
            if n not in cur and len(cur) < 16:
                moves.append(cur | {n})
            elif n in cur:
                moves.append(cur - {n})
        rng.shuffle(moves)
        improved = False
        for m in moves:
            if used >= budget:
                break
            r = evaluate(m, dyn)
            used += 1
            if r and (best is None or r['total'] < best['total']):
                cur, best, improved = m, r, True
                break
        if not improved:
            break
    return cur, best, used


def random_feasible(rng, size=16, tries=400):
    """Uniform random subsets of the pool, rejected until one can run the suite.

    Rejection sampling rather than a constructed seed: nothing about which
    instructions a working machine needs is supplied by me.
    """
    names = list(POOL)
    for _ in range(tries):
        s = set(rng.sample(names, size))
        T = compile_templates(s)
        if T and index_schemes(s, T):
            return s
    return None


def run_search(dyn, restarts=6, budget=90, seed=1):
    rng = random.Random(seed)
    results = []
    for i in range(restarts):
        start = random_feasible(rng)
        if start is None:
            print('  restart %d: no feasible start drawn' % (i + 1), flush=True)
            continue
        s, r, used = hill_climb(dyn, start, rng, budget)
        if r:
            results.append((r['total'], sorted(s), r))
            print('  restart %d: %6d gates, %2d instrs, %s' %
                  (i + 1, r['total'], len(s), r['scheme']), flush=True)
        else:
            print('  restart %d: no usable machine found' % (i + 1), flush=True)
    results.sort(key=lambda t: t[0])
    return results
