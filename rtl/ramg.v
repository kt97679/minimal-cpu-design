// Gate-level register-file RAM used only for area accounting: synthesising this
// with memory_map turns it into flip-flops + address decode/mux, so we can
// count what the program store of each machine actually costs in gates.
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
    always @(posedge clk) begin
        if (we) mem[addr] <= din;
        dout <= mem[addr];
    end
endmodule
