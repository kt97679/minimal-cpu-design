#!/bin/sh
# Gate-level cost of an N x 16 program store.
# usage: synth/gates_ram.sh 136
N=${1:-136}
yosys -p "
  read_verilog rtl/ramg.v
  chparam -set N $N ramg
  hierarchy -top ramg
  proc; opt; memory_map; opt -full
  techmap; opt -full
  dfflegalize -cell \$_DFF_P_ 0
  abc -g NAND
  opt_clean
  stat"
