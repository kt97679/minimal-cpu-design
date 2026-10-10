// Gate-level register-file RAM used only for area accounting.
//
// Storage is a level-sensitive latch array, not edge-triggered flip-flops: an
// addressed memory writes one word at a time with the address held for the
// whole write, so the cells never need a clock edge. The read output stays
// registered, so the CPU interface and its one-cycle read latency are
// unchanged. The latches are transparent only while the clock is low, so a
// write and the next read never overlap -- a half-cycle write, which is how
// latch-based register files are normally clocked.
`ifndef NWORDS
 `define NWORDS 136
`endif
module ramg #(parameter N = `NWORDS, AW = 8) (
    input  wire          clk,
    input  wire [AW-1:0] addr,
    input  wire          we,
    input  wire [15:0]   din,
    output reg  [15:0]   dout
);
    reg [15:0] mem [0:N-1];
    integer i;
    always @* begin
        for (i = 0; i < N; i = i + 1)
            if (we && !clk && addr == i[AW-1:0]) mem[i] = din;
    end
    always @(posedge clk) dout <= mem[addr];
endmodule
