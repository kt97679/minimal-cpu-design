// SUBLEQ with memory-mapped functional units -- the same amenity the MOVE
// machine gets. Still exactly one instruction; what changes is that some
// addresses are wired to hardware rather than to storage:
//
//   N     OUT   write strobes the output port; reads as 0
//   N+1   ADR   an index register: reads its value, writes set it
//   N+2   IND   reads mem[ADR], writes mem[ADR]
//
// With these, `subleq ADR,ADR` clears the index, `subleq K,ADR` adds to it and
// `subleq IND,Z` reads an array element -- so indexed access no longer requires
// the program to modify its own code.
module comp_subleq2 #(parameter N = 800, AW = 10) (
    input  wire          clk,
    input  wire          rst,
    output reg  [15:0]   out_val,
    output reg           out_stb,
    output wire [AW-1:0] ram_addr,
    output wire          ram_we,
    output wire [15:0]   ram_din,
    input  wire [15:0]   ram_dout
);
    wire [AW-1:0] maddr;
    wire          mwe;
    wire [15:0]   mdout;
    wire          ifq;

    wire is_out = (maddr == N[AW-1:0]);
    wire is_adr = (maddr == N[AW-1:0] + 1);
    wire is_ind = (maddr == N[AW-1:0] + 2);

    reg [AW-1:0] adr;
    reg          was_out, was_adr;

    assign ram_addr = is_ind ? adr : maddr;
    assign ram_we   = mwe & ~is_out & ~is_adr;
    assign ram_din  = mdout;

    wire [15:0] mdin = was_out ? 16'd0
                     : was_adr ? {{(16 - AW){1'b0}}, adr}
                     : ram_dout;

    subleq_cpu #(.AW(AW)) cpu (
        .clk(clk), .rst(rst), .maddr(maddr), .mwe(mwe),
        .mdout(mdout), .mdin(mdin), .ifetch(ifq));

    // adr must be reset: the program clears the index with `subleq ADR,ADR`,
    // and an undefined register would stay undefined (x - x = x).
    always @(posedge clk) begin
        if (rst) begin
            adr <= {AW{1'b0}}; was_out <= 1'b0; was_adr <= 1'b0; out_stb <= 1'b0;
        end else begin
            was_out <= is_out;
            was_adr <= is_adr;
            out_stb <= is_out & mwe;
            if (is_out & mwe) out_val <= mdout;
            if (is_adr & mwe) adr     <= mdout[AW-1:0];
        end
    end
endmodule
