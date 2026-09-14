#!/usr/bin/env python3
"""
Phase 3: a five-program benchmark suite, so that "minimum gates" stops having
the degenerate answer it had in phase 2.

Each benchmark is written ONCE in a small memory-to-memory virtual ISA, and
each target machine supplies macro expansions for the virtual operations. That
guarantees every design point runs the same algorithm on the same data, and
removes the risk of accidentally hand-optimising one machine's assembly harder
than another's.

Virtual ISA
    movi d,imm      mov d,s        add d,s       sub d,s
    addi d,imm      subi d,imm     out s         halt
    jmp L           jz s,L         jn s,L        (jn = signed <0)
    ldx d,base,i    stx base,i,s   (indexed: mem[base + mem[i]])

Suite: Fibonacci, insertion sort, shift-and-add multiply, Euclid's GCD,
binary-to-decimal. 123 output values in total.
"""
import math

MASK = 0xFFFF
ARRN = 16
# Values are kept under 2^14 so that a signed 16-bit `a - b` cannot overflow:
# these machines compare by subtracting and testing the sign, and that is only
# valid when the difference fits in the word. Same reason for the GCD inputs.
ARR0 = [4711, 17, 15000, 1234, 9, 8192, 255, 12000,
        3, 12345, 501, 16000, 777, 2048, 31, 9999]
MULX, MULY = 1234, 5678
GCDA, GCDB = 12600, 4410
DECV, DECN = 54321, 5


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


# --------------------------------------------------------------- the suite
POOLING = True      # set False to give every variable its own word (phase 3)


def suite():
    # The five benchmarks run one after another, so their variables do not each
    # need their own word of RAM -- names are pooled into v0..v6, which is the
    # maximum number live at any point (in the sort and the decimal loop).
    # This is liveness-based coalescing done by hand; no ISA change.
    P, ren = [], {}

    def e(op):
        P.append(tuple(op[:1]) +
                 tuple(ren.get(x, x) if isinstance(x, str) else x
                       for x in op[1:]))

    def pool(**m):
        ren.clear()
        if POOLING:
            ren.update(m)

    pool(a='v0', b='v1', n='v2')

    # ---- B1: 100 Fibonacci numbers, two per iteration
    e(('movi', 'a', 0)); e(('movi', 'b', 1)); e(('movi', 'n', 50))
    e(('label', 'f1'))
    e(('out', 'a')); e(('out', 'b'))
    e(('add', 'a', 'b')); e(('add', 'b', 'a'))
    e(('subi', 'n', 1)); e(('jz', 'n', 'f2')); e(('jmp', 'f1'))
    e(('label', 'f2'))

    # ---- B2: insertion sort of ARRN words, then emit them in order
    pool(i='v0', key='v1', j='v2', t='v3', u='v4', k='v5')
    e(('movi', 'i', 1))
    e(('label', 's1'))
    e(('ldx', 'key', 'ARR', 'i'))
    e(('mov', 'j', 'i')); e(('subi', 'j', 1))
    e(('label', 's2'))
    e(('jn', 'j', 's3'))                      # j < 0 -> insert
    e(('ldx', 't', 'ARR', 'j'))
    e(('mov', 'u', 'key')); e(('sub', 'u', 't'))
    e(('jn', 'u', 's4'))                      # key < A[j] -> shift up
    e(('jmp', 's3'))
    e(('label', 's4'))
    e(('mov', 'k', 'j')); e(('addi', 'k', 1))
    e(('stx', 'ARR', 'k', 't'))
    e(('subi', 'j', 1)); e(('jmp', 's2'))
    e(('label', 's3'))
    e(('mov', 'k', 'j')); e(('addi', 'k', 1))
    e(('stx', 'ARR', 'k', 'key'))
    e(('addi', 'i', 1))
    e(('mov', 't', 'i')); e(('subi', 't', ARRN)); e(('jn', 't', 's1'))
    e(('movi', 'i', 0))
    e(('label', 's5'))
    e(('ldx', 't', 'ARR', 'i')); e(('out', 't'))
    e(('addi', 'i', 1))
    e(('mov', 'u', 'i')); e(('subi', 'u', ARRN)); e(('jn', 'u', 's5'))

    # ---- B3: 16x16 -> 16 multiply, shift and add, MSB first
    pool(x='v0', y='v1', p='v2', cnt='v3')
    e(('movi', 'x', MULX)); e(('movi', 'y', MULY))
    e(('movi', 'p', 0)); e(('movi', 'cnt', 16))
    e(('label', 'm1'))
    e(('add', 'p', 'p'))
    e(('jn', 'y', 'm2')); e(('jmp', 'm3'))
    e(('label', 'm2')); e(('add', 'p', 'x'))
    e(('label', 'm3'))
    e(('add', 'y', 'y'))
    e(('subi', 'cnt', 1)); e(('jz', 'cnt', 'm4')); e(('jmp', 'm1'))
    e(('label', 'm4')); e(('out', 'p'))

    # ---- B4: Euclid's GCD by repeated subtraction
    pool(a='v0', b='v1', t='v2')
    e(('movi', 'a', GCDA)); e(('movi', 'b', GCDB))
    e(('label', 'g1'))
    e(('mov', 't', 'a')); e(('sub', 't', 'b')); e(('jz', 't', 'g3'))
    e(('jn', 't', 'g2'))
    e(('sub', 'a', 'b')); e(('jmp', 'g1'))
    e(('label', 'g2')); e(('sub', 'b', 'a')); e(('jmp', 'g1'))
    e(('label', 'g3')); e(('out', 'a'))

    # ---- B5: binary to decimal, least significant digit first.
    # Restoring division by 10: only left shifts and sign tests are needed.
    pool(v='v0', dcnt='v1', q='v2', rem='v3', cnt='v4', w='v5', t='v6')
    e(('movi', 'v', DECV)); e(('movi', 'dcnt', DECN))
    e(('label', 'd0'))
    e(('movi', 'q', 0)); e(('movi', 'rem', 0))
    e(('movi', 'cnt', 16)); e(('mov', 'w', 'v'))
    e(('label', 'd1'))
    e(('add', 'rem', 'rem'))
    e(('jn', 'w', 'd2')); e(('jmp', 'd3'))
    e(('label', 'd2')); e(('addi', 'rem', 1))
    e(('label', 'd3'))
    e(('add', 'w', 'w')); e(('add', 'q', 'q'))
    e(('mov', 't', 'rem')); e(('subi', 't', 10)); e(('jn', 't', 'd4'))
    e(('subi', 'rem', 10)); e(('addi', 'q', 1))
    e(('label', 'd4'))
    e(('subi', 'cnt', 1)); e(('jz', 'cnt', 'd5')); e(('jmp', 'd1'))
    e(('label', 'd5'))
    e(('out', 'rem')); e(('mov', 'v', 'q'))
    e(('subi', 'dcnt', 1)); e(('jz', 'dcnt', 'd6')); e(('jmp', 'd0'))
    e(('label', 'd6'))
    e(('halt',))
    return P


def golden():
    """Expected output stream, computed directly rather than by interpretation."""
    o = []
    a, b = 0, 1
    for _ in range(50):
        o += [a, b]
        a = (a + b) & MASK
        b = (b + a) & MASK
    o += sorted(ARR0)
    o.append((MULX * MULY) & MASK)
    o.append(math.gcd(GCDA, GCDB))
    v = DECV
    for _ in range(DECN):
        o.append(v % 10)
        v //= 10
    return o


def interp(prog):
    """Reference interpreter for the virtual ISA."""
    lab = {op[1]: i for i, op in enumerate(prog) if op[0] == 'label'}
    m = {'ARR': list(ARR0)}
    out, pc, steps = [], 0, 0
    get = lambda n: m.get(n, 0)
    while pc < len(prog) and steps < 10 ** 7:
        op = prog[pc]
        pc += 1
        steps += 1
        k = op[0]
        if k in ('label',):
            continue
        elif k == 'halt':
            break
        elif k == 'movi':
            m[op[1]] = op[2] & MASK
        elif k == 'mov':
            m[op[1]] = get(op[2])
        elif k == 'add':
            m[op[1]] = (get(op[1]) + get(op[2])) & MASK
        elif k == 'sub':
            m[op[1]] = (get(op[1]) - get(op[2])) & MASK
        elif k == 'addi':
            m[op[1]] = (get(op[1]) + op[2]) & MASK
        elif k == 'subi':
            m[op[1]] = (get(op[1]) - op[2]) & MASK
        elif k == 'out':
            out.append(get(op[1]))
        elif k == 'jmp':
            pc = lab[op[1]]
        elif k == 'jz':
            pc = lab[op[2]] if get(op[1]) == 0 else pc
        elif k == 'jn':
            pc = lab[op[2]] if s16(get(op[1])) < 0 else pc
        elif k == 'ldx':
            m[op[1]] = m[op[2]][get(op[3])]
        elif k == 'stx':
            m[op[1]][get(op[2])] = get(op[3])
        else:
            raise ValueError(k)
    return out


# ------------------------------------------------------------- code emission
# Words are emitted symbolically and resolved after layout is known:
#   ('lit', v)              literal value
#   ('ref', name, off, opc) sym[name] + off, optionally packed with an opcode
# The pseudo-symbol '@' resolves to 0, so ('ref','@',k,..) is the absolute
# address k -- used for the self-modifying targets.
class Target:
    self_modifying = False

    def __init__(self):
        self.words, self.labels, self.sym = [], {}, {}
        self.consts, self.vars = {}, []

    def var(self, name):
        if name not in self.vars:
            self.vars.append(name)
        return name

    def K(self, value):
        name = f'#{value & MASK}'
        self.consts.setdefault(name, ('val', value & MASK))
        return name

    def tmpl(self, opc, base):
        """constant word: an instruction whose address field is `base`"""
        name = f'@t{opc}:{base}'
        self.consts.setdefault(name, ('instr', opc, base))
        return name

    def negbase(self, base):
        """constant word holding -base, for planting an address into code"""
        name = f'@n:{base}'
        self.consts.setdefault(name, ('neg', base))
        return name

    def here(self):
        return len(self.words)

    def lit(self, v):
        self.words.append(('lit', v))

    def ref(self, name, off=0, opc=None):
        self.words.append(('ref', name, off, opc))

    def assemble(self, prog):
        n = ncode = 0
        for _ in range(2):
            self.words, self.labels = [], {}
            for op in prog:
                if op[0] == 'label':
                    self.labels[op[1]] = self.here()
                else:
                    self.gen(op)
            ncode = len(self.words)
            addr, sym = ncode, {'@': 0}
            for c in self.consts:            # read-only: can live in ROM
                sym[c] = addr
                addr += 1
            self.nro = addr
            for v in self.vars:              # mutable: must be RAM
                sym[v] = addr
                addr += 1
            sym['ARR'] = addr
            addr += ARRN
            n = addr
            sym['port'] = n
            sym.update(self.labels)
            self.sym = sym
        mem = [0] * n
        for i, w in enumerate(self.words):
            if w[0] == 'lit':
                mem[i] = w[1] & MASK
            else:
                _, name, off, opc = w
                v = self.sym[name] + off
                mem[i] = ((opc << 12) | v) & MASK if opc is not None else v & MASK
        for c, spec in self.consts.items():
            if spec[0] == 'val':
                mem[self.sym[c]] = spec[1]
            elif spec[0] == 'instr':
                mem[self.sym[c]] = ((spec[1] << 12) | self.sym[spec[2]]) & MASK
            else:
                mem[self.sym[c]] = (-self.sym[spec[1]]) & MASK
        for i, v in enumerate(ARR0):
            mem[self.sym['ARR'] + i] = v & MASK
        return mem, n, ncode, self.nro


# --------------------------------------------------------- accumulator target
LDA, STA, JZ, SUB, ADD, JMP, LDI, ADDI = 0, 1, 2, 3, 4, 5, 6, 7
JN, LDX, LDAX, STAX = 12, 13, 14, 15
ACYC = {LDA: 2, STA: 2, SUB: 2, ADD: 2, LDX: 2, LDAX: 2, STAX: 2,
        JZ: 1, JMP: 1, JN: 1, LDI: 1, ADDI: 1}


class Acc(Target):
    def __init__(self, has_add=False, has_jmp=False, has_index=False,
                 has_imm=False):
        super().__init__()
        self.has_add, self.has_jmp, self.has_index = has_add, has_jmp, has_index
        self.has_imm = has_imm
        self.self_modifying = not has_index
        if not has_add:
            self.var('_t0')

    def i(self, opc, name, off=0):
        self.ref(name, off, opc)

    def imm(self, opc, value):
        self.lit((opc << 12) | (value & 0xFFF))

    def jump(self, L):
        if self.has_jmp:
            self.i(JMP, L)
        else:
            self.i(LDA, self.K(0)); self.i(JZ, L)

    def addmem(self, d, s):
        if self.has_add:
            self.i(LDA, d); self.i(ADD, s); self.i(STA, d)
        else:                                   # no ADD:  d - (0 - s)
            self.i(LDA, self.K(0)); self.i(SUB, s); self.i(STA, '_t0')
            self.i(LDA, d); self.i(SUB, '_t0'); self.i(STA, d)

    def plant(self, tmpl, idx, patch_at):
        """store (tmpl + mem[idx]) into the code word at patch_at"""
        if self.has_add:
            self.i(LDA, tmpl); self.i(ADD, idx)
        else:
            self.i(LDA, self.K(0)); self.i(SUB, idx); self.i(STA, '_t0')
            self.i(LDA, tmpl); self.i(SUB, '_t0')
        self.i(STA, '@', patch_at)

    def gen(self, op):
        k = op[0]
        if k == 'movi':
            self.var(op[1])
            if self.has_imm and -2048 <= op[2] < 2048:
                self.imm(LDI, op[2])
            else:
                self.i(LDA, self.K(op[2]))
            self.i(STA, op[1])
        elif k == 'mov':
            self.var(op[1]); self.var(op[2])
            self.i(LDA, op[2]); self.i(STA, op[1])
        elif k == 'add':
            self.var(op[1]); self.var(op[2]); self.addmem(op[1], op[2])
        elif k == 'sub':
            self.var(op[1]); self.var(op[2])
            self.i(LDA, op[1]); self.i(SUB, op[2]); self.i(STA, op[1])
        elif k in ('addi', 'subi'):
            self.var(op[1])
            delta = op[2] if k == 'addi' else -op[2]
            self.i(LDA, op[1])
            if self.has_imm and -2048 <= delta < 2048:
                self.imm(ADDI, delta)
            else:
                self.i(SUB, self.K(-delta))
            self.i(STA, op[1])
        elif k == 'out':
            self.var(op[1]); self.i(LDA, op[1]); self.i(STA, 'port')
        elif k == 'jmp':
            self.jump(op[1])
        elif k == 'jz':
            self.var(op[1]); self.i(LDA, op[1]); self.i(JZ, op[2])
        elif k == 'jn':
            self.var(op[1]); self.i(LDA, op[1]); self.i(JN, op[2])
        elif k == 'halt':
            self.labels['_halt'] = self.here(); self.jump('_halt')
        elif k == 'ldx':
            _, d, base, idx = op
            self.var(d); self.var(idx)
            if self.has_index:
                self.i(LDX, idx); self.i(LDAX, base); self.i(STA, d)
            else:
                n = 3 if self.has_add else 6
                self.plant(self.tmpl(LDA, base), idx, self.here() + n)
                self.i(LDA, self.K(0))              # <- patched in place
                self.i(STA, d)
        elif k == 'stx':
            _, base, idx, s = op
            self.var(idx); self.var(s)
            if self.has_index:
                self.i(LDX, idx); self.i(LDA, s); self.i(STAX, base)
            else:
                n = 3 if self.has_add else 6
                self.plant(self.tmpl(STA, base), idx, self.here() + n + 1)
                self.i(LDA, s)
                self.i(STA, self.K(0))              # <- patched in place
        else:
            raise ValueError(k)


def emu_acc(mem, n, nout, limit=10 ** 7):
    mem = mem[:] + [0]
    pc = acc = xreg = cyc = ic = 0
    out = []
    while ic < limit and len(out) < nout:
        w = mem[pc]
        opc, ad = (w >> 12) & 0xF, w & 0xFFF
        pc += 1
        ic += 1
        cyc += ACYC[opc]
        if opc == LDA:
            acc = mem[ad]
        elif opc == STA:
            if ad == n:
                out.append(acc)
            else:
                mem[ad] = acc
        elif opc == JZ:
            if acc == 0:
                pc = ad
        elif opc == SUB:
            acc = (acc - mem[ad]) & MASK
        elif opc == ADD:
            acc = (acc + mem[ad]) & MASK
        elif opc == JMP:
            pc = ad
        elif opc == LDI:
            acc = ad if ad < 0x800 else ad - 0x1000
            acc &= MASK
        elif opc == ADDI:
            acc = (acc + (ad if ad < 0x800 else ad - 0x1000)) & MASK
        elif opc == JN:
            if acc & 0x8000:
                pc = ad
        elif opc == LDX:
            xreg = mem[ad] & 0xFF
        elif opc == LDAX:
            acc = mem[ad + xreg]
        elif opc == STAX:
            t = ad + xreg
            if t == n:
                out.append(acc)
            else:
                mem[t] = acc
        else:
            raise ValueError(opc)
    return out, cyc, ic


# ---------------------------------------------------------------- SUBLEQ
class Subleq(Target):
    """subleq A,B,C : M[B] -= M[A]; if M[B] <= 0 goto C, else fall through."""
    self_modifying = True

    def __init__(self):
        super().__init__()
        for v in ('_Z', '_T', '_U'):
            self.var(v)

    def sq(self, A, B, C=None, Aoff=0, Boff=0):
        self.ref(A, Aoff)
        self.ref(B, Boff)
        if C is None:
            self.lit(self.here() + 1)
        elif isinstance(C, int):
            self.lit(C)
        else:
            self.ref(C)

    def clr(self, x, off=0):
        self.sq(x, x, Aoff=off, Boff=off)

    def plant(self, base, idx_neg, at):
        """write (base + idx) into the code word at `at`; idx_neg holds -idx"""
        self.clr('@', off=at)
        self.sq(self.negbase(base), '@', Boff=at)     # word = base
        self.sq(idx_neg, '@', Boff=at)                # word += idx

    def gen(self, op):
        k = op[0]
        if k == 'movi':
            self.var(op[1]); self.clr(op[1]); self.sq(self.K(-op[2]), op[1])
        elif k == 'mov':
            self.var(op[1]); self.var(op[2])
            self.clr(op[1]); self.clr('_Z')
            self.sq(op[2], '_Z'); self.sq('_Z', op[1])
        elif k == 'add':
            self.var(op[1]); self.var(op[2])
            self.clr('_Z'); self.sq(op[2], '_Z'); self.sq('_Z', op[1])
        elif k == 'sub':
            self.var(op[1]); self.var(op[2]); self.sq(op[2], op[1])
        elif k == 'addi':
            self.var(op[1]); self.sq(self.K(-op[2]), op[1])
        elif k == 'subi':
            self.var(op[1]); self.sq(self.K(op[2]), op[1])
        elif k == 'out':
            self.var(op[1])
            self.clr('_Z'); self.sq(op[1], '_Z'); self.sq('_Z', 'port')
        elif k == 'jmp':
            self.sq('_Z', '_Z', op[1])
        elif k == 'jn':                     # s < 0  ==  (s + 1) <= 0
            # NB: "-s <= 0" would be one instruction shorter but is wrong for
            # s = -32768, since negating it overflows -- and the multiply and
            # divide loops both shift an operand through exactly 0x8000.
            self.var(op[1])
            self.clr('_T'); self.sq(self.K(-1), '_T')    # _T = 1
            self.clr('_Z'); self.sq(op[1], '_Z')         # _Z = -s
            self.sq('_Z', '_T', op[2])                   # _T = s+1; br if <= 0
        elif k == 'jz':                     # s >= 0 and s <= 0
            self.var(op[1])
            a = self.here() + 3 * 3
            nz = self.here() + 5 * 3
            self.clr('_T')
            self.sq(op[1], '_T', a)         # _T = -s; branch if s >= 0
            self.sq('_Z', '_Z', nz)
            self.clr('_U')
            self.sq('_T', '_U', op[2])      # _U = s; branch if s <= 0
        elif k == 'halt':
            h = self.here()
            self.sq('_Z', '_Z', h)
        elif k == 'ldx':
            _, d, base, idx = op
            self.var(d); self.var(idx)
            p = self.here() + 7 * 3         # A-field of the fetch instruction
            self.clr('_Z'); self.sq(idx, '_Z')          # _Z = -idx
            self.plant(base, '_Z', p)
            self.clr(d); self.clr('_Z')
            self.sq('@', '_Z', Aoff=p)                  # _Z = -M[base+idx]
            self.sq('_Z', d)
        elif k == 'stx':
            _, base, idx, s = op
            self.var(idx); self.var(s)
            q1 = self.here() + 11 * 3       # operand words of the clearing subleq
            q3 = self.here() + 14 * 3 + 1   # B-field of the storing subleq
            self.clr('_Z'); self.sq(idx, '_Z')
            for t in (q1, q1 + 1, q3):
                self.plant(base, '_Z', t)
            self.sq('@', '@', Aoff=q1, Boff=q1 + 1)     # M[target] = 0
            self.clr('_Z'); self.sq(s, '_Z')            # _Z = -s
            self.sq('_Z', '@', Boff=q3)                 # M[target] = s
        else:
            raise ValueError(k)


def emu_subleq(mem, n, nout, limit=10 ** 8):
    mem = mem[:] + [0]
    pc = cyc = ic = 0
    out = []
    while ic < limit and len(out) < nout:
        A, B, C = mem[pc], mem[pc + 1], mem[pc + 2]
        va = 0 if A == n else mem[A]
        vb = 0 if B == n else mem[B]
        r = (vb - va) & MASK
        if B == n:
            out.append(r)
        else:
            mem[B] = r
        pc = C if s16(r) <= 0 else pc + 3
        cyc += 6
        ic += 1
    return out, cyc, ic


# ------------------------------------------------------------------ designs
DESIGNS = [
    dict(key='sq',    label='SUBLEQ',                    nops=1,
         make=lambda: Subleq(), defs=[]),
    dict(key='a5',    label='LDA STA JZ SUB JN',         nops=5,
         make=lambda: Acc(), defs=['HAS_SIGN']),
    dict(key='a7',    label='+ ADD JMP',                 nops=7,
         make=lambda: Acc(has_add=True, has_jmp=True),
         defs=['HAS_SIGN', 'HAS_ADD', 'HAS_JMP']),
    dict(key='a10',   label='+ LDX LDAX STAX',           nops=10,
         make=lambda: Acc(has_add=True, has_jmp=True, has_index=True),
         defs=['HAS_SIGN', 'HAS_ADD', 'HAS_JMP', 'HAS_INDEX']),
    dict(key='a12',   label='+ LDI ADDI (immediates)',   nops=12,
         make=lambda: Acc(has_add=True, has_jmp=True, has_index=True,
                          has_imm=True),
         defs=['HAS_SIGN', 'HAS_ADD', 'HAS_JMP', 'HAS_INDEX', 'HAS_IMM']),
    dict(key='a14',   label='+ AND OR XOR SHR',          nops=14,
         make=lambda: Acc(has_add=True, has_jmp=True, has_index=True),
         defs=['HAS_SIGN', 'HAS_ADD', 'HAS_JMP', 'HAS_INDEX', 'HAS_LOGIC']),
]


def build():
    prog = suite()
    gold = golden()
    assert interp(prog) == gold, 'virtual ISA program does not match the model'
    out = {}
    for d in DESIGNS:
        t = d['make']()
        mem, n, ncode, nro = t.assemble(prog)
        emu = emu_subleq if d['key'] == 'sq' else emu_acc
        vals, cyc, ic = emu(mem, n, len(gold))
        assert vals == gold, (d['key'], len(vals), vals[:6], gold[:6])
        out[d['key']] = dict(mem=mem, n=n, ncode=ncode, nro=nro,
                             cycles=cyc, instrs=ic,
                             selfmod=t.self_modifying, **{x: d[x] for x in
                             ('label', 'nops', 'defs')})
    return out, gold


if __name__ == '__main__':
    res, gold = build()
    print(f'{len(gold)} outputs expected; all design points verified\n')
    print('%-24s %4s %7s %7s %9s %9s %5s' %
          ('design', 'ops', 'code', 'words', 'instrs', 'cycles', 'smc'))
    for d in DESIGNS:
        r = res[d['key']]
        print('%-24s %4d %7d %7d %9d %9d %5s' %
              (r['label'], r['nops'], r['ncode'], r['n'], r['instrs'],
               r['cycles'], 'yes' if r['selfmod'] else 'no'))
