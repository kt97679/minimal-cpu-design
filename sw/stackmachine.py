#!/usr/bin/env python3
"""
Phase 9a: a stack machine, which phases 1-8 could not reach.

Every machine so far has had an accumulator and memory operands, because my
compiler searched over register states and my instruction pool was built from
(operation x addressing mode x register). A zero-address machine is outside
that frame entirely, and Forth is the standing argument that it should be
denser.

Two things are worth stating before the numbers.

Computed addressing is native here. `push base; push i; add; fetch` is how a
stack machine indexes, so it needs neither an index register nor self-modifying
code. By construction it lands in the cheap cluster of phases 3-8 -- that part
is not an empirical result, it is what the addressing model gives you.

Forth's density, on the other hand, comes from threading and factoring into
named words, which needs CALL/RETURN. No machine in this project has a
subroutine instruction, so this is a stack machine without the mechanism Forth
is actually dense because of. That is a limit of the experiment, not a verdict
on Forth.

The compiler here searches, exactly as the accumulator one does -- breadth-first
over stack states, verified on random test vectors -- so the two targets are
compiled on equal terms and neither gets hand-written macros.
"""
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autosearch import ALU, COND, NEG, ZERO, POS, MASK, BUILD, ROOT

NTEST = 4
SCRATCH = ('t0', 't1')


def build_pool():
    """{binary ALU op} + {stack shuffle} + {memory} + {branch}, enumerated."""
    p = {}
    for op in ALU:
        if op == 'LD':
            continue                      # meaningless with no destination
        p[op] = dict(name=op, kind='alu', op=op, pops=2, pushes=1, cycles=1)
    for n, (po, pu) in dict(DUP=(1, 2), DROP=(1, 0), SWAP=(2, 2),
                            OVER=(2, 3)).items():
        p[n] = dict(name=n, kind='shuf', op=n, pops=po, pushes=pu, cycles=1)
    p['LIT'] = dict(name='LIT', kind='lit', op='LIT', pops=0, pushes=1, cycles=1)
    p['LOAD'] = dict(name='LOAD', kind='load', op='LOAD', pops=0, pushes=1, cycles=2)
    p['STORE'] = dict(name='STORE', kind='store', op='STORE', pops=1, pushes=0, cycles=2)
    p['FETCH'] = dict(name='FETCH', kind='fetch', op='FETCH', pops=1, pushes=1, cycles=2)
    p['STOREI'] = dict(name='STOREI', kind='storei', op='STOREI', pops=2, pushes=0, cycles=2)
    for c in COND:
        p[c] = dict(name=c, kind='br', op=c, pops=0 if c == 'JMP' else 1,
                    pushes=0, cycles=1)
    for n in ('SHR', 'SHL'):
        p[n] = dict(name=n, kind='sh', op=n, pops=1, pushes=1, cycles=1)
    p['CALL'] = dict(name='CALL', kind='call', op='CALL', pops=0, pushes=0, cycles=1)
    p['RET'] = dict(name='RET', kind='ret', op='RET', pops=0, pushes=0, cycles=1)
    return p


POOL = build_pool()


class St:
    __slots__ = ('s', 'mem')

    def __init__(self, s, mem):
        self.s, self.mem = s, mem        # s[0] is top of stack

    def key(self):
        return (self.s, tuple(sorted(self.mem.items())))


def step(st, ins, operand, consts, depth):
    s, mem = list(st.s), dict(st.mem)
    k, need = ins['kind'], ins['pops']
    if len(s) < need:
        return None
    if len(s) - ins['pops'] + ins['pushes'] > depth:
        return None                      # would overflow the hardware stack
    if k == 'lit':
        if operand not in consts:
            return None
        s.insert(0, (consts[operand],) * NTEST)
    elif k == 'load':
        if operand not in mem:
            return None
        s.insert(0, mem[operand])
    elif k == 'store':
        if operand not in SCRATCH:
            return None                  # d and s written only at the end
        mem[operand] = s.pop(0)
    elif k == 'fetch' or k == 'storei':
        return None                      # address-computed forms: array use only
    elif k == 'alu':
        b = s.pop(0); a = s.pop(0)
        f = ALU[ins['op']]
        s.insert(0, tuple(f(x, y) & MASK for x, y in zip(a, b)))
    elif k == 'sh':
        v = s.pop(0)
        f = (lambda x: x >> 1) if ins['op'] == 'SHR' else (lambda x: (x << 1) & MASK)
        s.insert(0, tuple(f(x) for x in v))
    elif k == 'shuf':
        o = ins['op']
        if o == 'DUP':
            s.insert(0, s[0])
        elif o == 'DROP':
            s.pop(0)
        elif o == 'SWAP':
            s[0], s[1] = s[1], s[0]
        elif o == 'OVER':
            s.insert(0, s[1])
    else:
        return None
    return St(tuple(s), mem)


def start_state(imm, seed=12345):
    rnd = random.Random(seed)
    rv = lambda: tuple(rnd.randrange(65536) for _ in range(NTEST))
    consts = {'Kz': 0, 'K1': 1, 'Kimm': imm & MASK, 'Kni': (-imm) & MASK}
    d0, s0 = rv(), rv()
    mem = {'d': d0, 's': s0, 't0': rv(), 't1': rv()}
    for c, v in consts.items():
        mem[c] = (v,) * NTEST
    return St((), mem), consts, d0, s0


def find_seq(iset, consts, start, goal, depth, maxdepth=5, beam=20000):
    """Shortest sequence leaving `goal` on top of the stack, `s` preserved."""
    usable = [POOL[n] for n in iset if POOL[n]['kind'] in
              ('alu', 'shuf', 'lit', 'load', 'store', 'sh')]
    operands = ['d', 's', 't0', 't1'] + list(consts)
    frontier = {start.key(): (start, ())}
    for _ in range(maxdepth):
        nxt = {}
        for _, (st, seq) in frontier.items():
            for ins in usable:
                ops = operands if ins['kind'] in ('lit', 'load', 'store') else ['-']
                for opd in ops:
                    ns = step(st, ins, opd, consts, depth)
                    if ns is None:
                        continue
                    if ns.s and ns.s[0] == goal and ns.mem['s'] == start.mem['s']:
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
    have = {n: COND[POOL[n]['op']] for n in iset if POOL[n]['kind'] == 'br'}
    if not have:
        return None
    subs = [n for n, c in have.items() if c <= want]
    if subs and frozenset().union(*[have[n] for n in subs]) == want:
        return [(n, 'L') for n in subs]
    comp = frozenset({NEG, ZERO, POS}) - want
    subs = [n for n, c in have.items() if c <= comp]
    cov = frozenset().union(*[have[n] for n in subs]) if subs else frozenset()
    if cov == comp and 'JMP' in have:
        return [(n, 'SKIP') for n in subs] + [('JMP', 'L')]
    return None


def compile_all(iset, depth):
    T = {}
    if 'STORE' not in iset:
        return None
    st0, c0, d0, s0 = start_state(0)

    def val(goal, imm=0, dep=5):
        s2, c2, dd, ss = start_state(imm)
        return find_seq(iset, c2, s2, goal, depth, maxdepth=dep)

    for key, goal in (('mov', s0),
                      ('add', tuple((a + b) & MASK for a, b in zip(d0, s0))),
                      ('sub', tuple((a - b) & MASK for a, b in zip(d0, s0)))):
        q = val(goal)
        if q is None:
            return None
        T[key] = q + (('STORE', 'd'),)
    for tag, probe in (('small', 7), ('big', 40000)):
        s2, c2, dd, ss = start_state(probe)
        for key, goal in ((f'movi_{tag}', (probe & MASK,) * NTEST),
                          (f'addi_{tag}', tuple((a + probe) & MASK for a in dd)),
                          (f'subi_{tag}', tuple((a - probe) & MASK for a in dd))):
            q = find_seq(iset, c2, s2, goal, depth, maxdepth=5)
            T[key] = q + (('STORE', 'd'),) if q else None
    for k in ('movi_big', 'addi_small', 'subi_small'):
        if T.get(k) is None:
            return None
    T['xor'] = None
    qx = val(tuple(a ^ b for a, b in zip(d0, s0)))
    if qx is not None:
        T['xor'] = qx + (('STORE', 'd'),)
    q = val(s0)
    if q is None:
        return None
    T['out'] = q + (('STORE', 'port'),)
    for vop, want in (('jz', frozenset({ZERO})), ('jn', frozenset({NEG}))):
        plan = branch_plan(iset, want)
        if plan is None:
            return None
        T[vop] = (val(s0), plan)         # conditional branches pop their operand
        if T[vop][0] is None:
            return None
    if 'JMP' in iset:
        T['jmp'] = ((), [('JMP', 'L')])
    else:
        found = None
        for cname in [c for c in COND if c in iset]:
            for slot, cls in (('Kz', ZERO), ('K1', POS)):
                if cls in COND[POOL[cname]['op']]:
                    q = val((c0[slot],) * NTEST, dep=3)
                    if q is not None:
                        found = (q, [(cname, 'L')]); break
            if found:
                break
        if found is None:
            return None
        T['jmp'] = found
    return T


def index_scheme(iset, depth):
    """`push base; push i; add; fetch` -- native, so never self-modifying."""
    need_l = {'LIT', 'LOAD', 'ADD', 'FETCH', 'STORE'}
    need_s = {'LIT', 'LOAD', 'ADD', 'STOREI'}
    if not need_l <= set(iset) or not need_s <= set(iset) or depth < 3:
        return None
    return dict(ldx=5, stx=5, cycles_ldx=1 + 2 + 1 + 2 + 2,
                cycles_stx=2 + 1 + 2 + 1 + 2, selfmod=False)


# ------------------------------------------------------- hardware generation
def sexpr(op, a, b):
    if op == 'RSB':
        return f'{b} - {a}'
    if op == 'NAND':
        return f'~({a} & {b})'
    return f'{a} ' + {'ADD': '+', 'SUB': '-', 'AND': '&', 'OR': '|',
                      'XOR': '^'}[op] + f' {b}'


def gen_rtl(iset, depth, aw=8):
    order = sorted(iset)
    if len(order) > 16:
        return None
    opc = {n: i for i, n in enumerate(order)}
    D = depth
    push = lambda v: '; '.join([f's{i} <= s{i-1}' for i in range(D - 1, 0, -1)] +
                               [f's0 <= {v}'])
    pop = lambda: '; '.join(f's{i} <= s{i+1}' for i in range(D - 1))
    pop2 = lambda: '; '.join(f's{i} <= s{i+2}' for i in range(D - 2))
    d, sq, ex = [], [], []
    for n in order:
        p, o = POOL[n], opc[n]
        k = p['kind']
        if k == 'lit':
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin {push('imm')}; pc <= pc + 1'b1; state <= S_D; end")
        elif k == 'load':
            d.append(f"4'd{o}: maddr = iad;")
            sq.append(f"4'd{o}: state <= S_E;")
            ex.append(f"4'd{o}: begin {push('mdin')}; end")
        elif k == 'store':
            d.append(f"4'd{o}: begin maddr = iad; mwe = 1'b1; mdout = s0; end")
            sq.append(f"4'd{o}: begin {pop()}; state <= S_W; end")
        elif k == 'fetch':
            d.append(f"4'd{o}: maddr = s0[AW-1:0];")
            sq.append(f"4'd{o}: state <= S_E;")
            ex.append(f"4'd{o}: begin s0 <= mdin; end")
        elif k == 'storei':
            d.append(f"4'd{o}: begin maddr = s0[AW-1:0]; mwe = 1'b1; mdout = s1; end")
            sq.append(f"4'd{o}: begin {pop2()}; state <= S_W; end")
        elif k == 'alu':
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin s0 <= {sexpr(p['op'], 's1', 's0')}; "
                      + '; '.join(f's{i} <= s{i+1}' for i in range(1, D - 1))
                      + f"; pc <= pc + 1'b1; state <= S_D; end")
        elif k == 'sh':
            e = "{1'b0, s0[15:1]}" if p['op'] == 'SHR' else "{s0[14:0], 1'b0}"
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin s0 <= {e}; pc <= pc + 1'b1; state <= S_D; end")
        elif k == 'shuf':
            op = p['op']
            if op == 'DUP':
                act = push('s0')
            elif op == 'DROP':
                act = pop()
            elif op == 'SWAP':
                act = 's0 <= s1; s1 <= s0'
            else:
                act = push('s1')
            d.append(f"4'd{o}: begin maddr = pc; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin {act}; pc <= pc + 1'b1; state <= S_D; end")
        elif k == 'call':
            d.append(f"4'd{o}: begin maddr = iad; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin lr <= pc; pc <= iad + 1'b1; state <= S_D; end")
        elif k == 'ret':
            d.append(f"4'd{o}: begin maddr = lr; ifetch = 1'b1; end")
            sq.append(f"4'd{o}: begin pc <= lr + 1'b1; state <= S_D; end")
        else:                                            # branch
            c = ("1'b1" if p['op'] == 'JMP' else
                 {'JZ': 'zf', 'JN': 'nf', 'JP': '(~nf & ~zf)', 'JNZ': '~zf',
                  'JNN': '~nf', 'JLE': '(nf | zf)'}[p['op']])
            d.append(f"4'd{o}: begin maddr = {c} ? iad : pc; ifetch = 1'b1; end")
            body = f"pc <= ({c} ? iad : pc) + 1'b1"
            if p['pops']:
                body += '; ' + pop()
            sq.append(f"4'd{o}: begin {body}; state <= S_D; end")
    nl = '\n                '
    use_lr = any(POOL[n]['kind'] in ('call', 'ret') for n in order)
    regs = ' '.join(f'reg [15:0] s{i};' for i in range(D)) + \
           (' reg [AW-1:0] lr;' if use_lr else '')
    rst = ' '.join(f's{i} <= 16\'d0;' for i in range(D))
    return f"""// generated stack machine, depth {D}, set={' '.join(order)}
module gcpu #(parameter AW = {aw}) (
    input wire clk, input wire rst,
    output reg [AW-1:0] maddr, output reg mwe, output reg [15:0] mdout,
    input wire [15:0] mdin, output reg ifetch);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;
    reg [AW-1:0] pc; reg [3:0] op; reg [1:0] state;
    {regs}
    wire [3:0] iop = mdin[15:12];
    wire [AW-1:0] iad = mdin[AW-1:0];
    wire [15:0] imm = {{{{4{{mdin[11]}}}}, mdin[11:0]}};
    wire zf = (s0 == 16'd0); wire nf = s0[15];
    always @* begin
        maddr = pc; mwe = 1'b0; mdout = s0; ifetch = 1'b0;
        case (state)
            S_D: case (iop)
                {nl.join(d)}
                default: maddr = iad;
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin
            pc <= {{AW{{1'b0}}}}; state <= S_F; op <= 4'd0; {rst}
        end else case (state)
            S_D: begin op <= iop; case (iop)
                {nl.join(sq)}
                default: state <= S_E;
            endcase end
            S_E: begin case (op)
                {nl.join(ex) if ex else "default: ;"}
                default: ;
            endcase pc <= pc + 1'b1; state <= S_D; end
            default: begin pc <= pc + 1'b1; state <= S_D; end
        endcase
    end
endmodule
"""


_c = {}


def core_gates(iset, depth):
    k = (depth, tuple(sorted(iset)))
    if k in _c:
        return _c[k]
    v = gen_rtl(iset, depth)
    if v is None:
        return None
    open(f'{BUILD}/stack_tmp.v', 'w').write(v)
    out = subprocess.run(['yosys', '-p',
        f'read_verilog {BUILD}/stack_tmp.v\n hierarchy -top gcpu\n flatten\n'
        ' proc; opt; fsm; opt; memory; opt\n techmap; opt -full\n'
        ' dfflegalize -cell $_DFF_P_ 0\n abc -g NAND\n opt_clean\n stat'],
        capture_output=True, text=True).stdout
    tail = out[out.rfind('Printing statistics'):]
    g = lambda c: (int(re.search(rf'\$_{c}_\s+(\d+)', tail).group(1))
                   if re.search(rf'\$_{c}_\s+(\d+)', tail) else 0)
    r = g('NAND') + g('NOT') + 6 * g('DFF_P')
    _c[k] = r
    return r
