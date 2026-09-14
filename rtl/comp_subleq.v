// SUBLEQ with a memory-mapped output port at address N.
// A write to N strobes the port; a read of N returns 0, which is what lets
// `subleq Z, port` emit +a after `subleq a, Z` has put -a in Z.
module comp_subleq #(parameter N = 50, AW = 6) (
    input  wire          clk,
    input  wire          rst,
    output reg  [15:0]   out_val,
    output reg           out_stb,
    output wire [AW-1:0] maddr,
    output wire          mwe,
    output wire [15:0]   mdout,
    input  wire [15:0]   ram_dout
);
    wire ifq;
    wire port = (maddr == N[AW-1:0]);
    reg  prev_port;
    wire [15:0] mdin = prev_port ? 16'd0 : ram_dout;

    subleq_cpu #(.AW(AW)) cpu (
        .clk(clk), .rst(rst), .maddr(maddr), .mwe(mwe),
        .mdout(mdout), .mdin(mdin), .ifetch(ifq));

    always @(posedge clk) begin
        prev_port <= port;
        out_stb   <= port & mwe;
        if (port & mwe) out_val <= mdout;
    end
endmodule
