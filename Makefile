# Reproduces every number in README.md.
#   make            - assemble, simulate, count gates
#   make fmax       - additionally place & route on an iCE40 for a real Fmax
#   make clean
#
# Tools: iverilog, yosys, python3  (+ nextpnr-ice40 for `make fmax`)
#   apt-get install iverilog yosys nextpnr-ice40

ACC_WORDS  ?= 136          # program+data+array footprint, printed by sw/asm.py
SUB_WORDS  ?= 157
SEEDS      ?= 1 2 3 4

.PHONY: all sim gates ram sweep fmax clean
all: sim gates ram

build:
	mkdir -p build

# ---- software: assemble both programs, check them against a reference model
build/acc.hex build/subleq.hex build/params.vh: sw/asm.py | build
	python3 sw/asm.py

# ---- RTL simulation: cycle counts + functional verification of both CPUs
sim: build/sim
	./build/sim

build/sim: rtl/tb.v rtl/acc_cpu.v rtl/subleq_cpu.v build/acc.hex
	iverilog -g2012 -o $@ rtl/tb.v rtl/acc_cpu.v rtl/subleq_cpu.v

# ---- area: map each CPU core to 2-input NANDs and plain D flip-flops
gates:
	@for m in acc sub; do \
	  echo "=== $$m core, NAND-mapped ==="; \
	  yosys -s synth/gates_$$m.ys 2>&1 | grep -A30 "Printing statistics" | grep -E '^\s+\$$_'; \
	done

# ---- area: the program store of each machine, built from gates
ram:
	@for n in $(ACC_WORDS) $(SUB_WORDS); do \
	  echo "=== RAM $${n}x16 from gates ==="; \
	  sh synth/gates_ram.sh $$n 2>&1 \
	    | grep -A20 "Printing statistics" | grep -E '^\s+\$$_'; \
	done

# ---- speed: place & route the whole computer, report timing-closed Fmax
fmax: | build
	@for m in acc sub; do \
	  yosys -q -s synth/ice40_$$m.ys; \
	  echo -n "top_$$m routed Fmax:"; \
	  for s in $(SEEDS); do \
	    nextpnr-ice40 --hx8k --package ct256 --json build/$$m.json --freq 200 --seed $$s 2>&1 \
	      | grep -i "Max frequency for clock" | tail -1 \
	      | grep -oE "[0-9]+\.[0-9]+ MHz" | head -1 | tr '\n' ' '; \
	  done; echo; \
	done

# ---- phase 2: design-space sweep (assembles, simulates and synthesises
#      every design point, then prints the gate/cycle table)
sweep:
	python3 sw/sweep.py

clean:
	rm -rf build
