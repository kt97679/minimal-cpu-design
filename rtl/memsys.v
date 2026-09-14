// Harvard-ish memory subsystem: code in a synthesised ROM at addresses
// [0, NCODE), mutable data in a gate-built RAM at [NCODE, NCODE+NDATA).
// None of the programs in the sweep self-modify, so their code does not need
// to sit in writable memory -- and a ROM word is far cheaper than a RAM word.
module memsys #(parameter NCODE = 11, NDATA = 2, AW = 4) (
    input  wire          clk,
    input  wire [AW-1:0] addr,
    input  wire          we,
    input  wire [15:0]   din,
    output wire [15:0]   dout
);
    wire [15:0] rom_q;
    reg         sel_d;

    rom code (.clk(clk), .addr(addr), .q(rom_q));

    always @(posedge clk) sel_d <= (addr < NCODE[AW-1:0]);

    generate if (NDATA > 0) begin : g_ram
        wire [15:0] ram_q;
        ramg #(.N(NDATA), .AW(AW)) data (
            .clk(clk), .addr(addr - NCODE[AW-1:0]), .we(we), .din(din), .dout(ram_q));
        assign dout = sel_d ? rom_q : ram_q;
    end else begin : g_norams
        assign dout = rom_q;
    end endgenerate
endmodule
