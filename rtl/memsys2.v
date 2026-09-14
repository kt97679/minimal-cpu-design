// Memory subsystem with read-only data folded into the ROM.
//   [0, NRO)            code AND constants  -> synthesised ROM, ~4 gates/word
//   [NRO, NRO+NDATA)    mutable scalars and arrays -> gate-built RAM
// The data RAM is addressed with only DAW = ceil(log2(NDATA)) bits rather than
// the full address width, which shrinks its per-word decoder.
module memsys2 #(parameter NRO = 212, NDATA = 35, AW = 8, DAW = 6) (
    input  wire          clk,
    input  wire [AW-1:0] addr,
    input  wire          we,
    input  wire [15:0]   din,
    output wire [15:0]   dout
);
    wire [15:0]   rom_q, ram_q;
    wire [AW-1:0] off = addr - NRO[AW-1:0];
    reg           sel_d;

    rom code (.clk(clk), .addr(addr), .q(rom_q));
    ramg #(.N(NDATA), .AW(DAW)) data (
        .clk(clk), .addr(off[DAW-1:0]), .we(we), .din(din), .dout(ram_q));

    always @(posedge clk) sel_d <= (addr < NRO[AW-1:0]);
    assign dout = sel_d ? rom_q : ram_q;
endmodule
