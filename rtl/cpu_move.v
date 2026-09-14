// The Ultimate RISC (Jones, 1988): one instruction, MOVE src,dst.
// Arithmetic and control flow are side effects of writing to memory-mapped
// ports. With an accumulator the instruction needs only two address fields, so
// it packs into a single 16-bit word: {dst[7:0], src[7:0]}.
//
// Ports live at PBASE..PBASE+9; everything below PBASE is ordinary memory.
//   0 ACC   read: accumulator      write: acc <- v
//   1 ADD                          write: acc <- acc + v
//   2 SUB                          write: acc <- acc - v
//   3 PC                           write: pc  <- v            (jump)
//   4 PCZ                          write: if acc == 0, pc <- v
//   5 PCN                          write: if acc[15],  pc <- v
//   6 ADR                          write: adr <- v            (index register)
//   7 ADRA                         write: adr <- adr + v
//   8 IND   read: mem[adr]         write: mem[adr] <- v
//   9 OUT                          write: output port strobe
//
// Timing, with the same single-port synchronous RAM as every other design:
//   cycles = 1 + (source needs a memory read) + (destination needs a write)
// so port-to-port is 1 cycle, memory-to-port and port-to-memory are 2, and
// memory-to-memory is 3.
module cpu_move #(parameter AW = 8, PBASE = 8'hF0) (
    input  wire          clk,
    input  wire          rst,
    output reg  [AW-1:0] maddr,
    output reg           mwe,
    output reg  [15:0]   mdout,
    input  wire [15:0]   mdin,
    output reg           ifetch,
    output reg  [15:0]   out_val,
    output reg           out_stb
);
    localparam S_S = 2'd0,   // mdin = instruction: decode, start source access
               S_X = 2'd1,   // mdin = source value: apply it to the destination
               S_F = 2'd2;   // destination was a memory write, so fetch now

    reg [7:0]  pc, adr, dstr;
    reg [15:0] acc;
    reg [1:0]  state;

    wire [7:0] isrc = mdin[7:0];
    wire [7:0] idst = mdin[15:8];

    // source: a memory access is needed unless it is a register port
    wire       sport   = (isrc >= PBASE);
    wire [3:0] sid     = isrc - PBASE;
    wire       src_rd  = (!sport) || (sid == 4'd8);
    wire [7:0] src_adr = (sport && sid == 4'd8) ? adr : isrc;

    // destination: in S_X it is the latched field, in S_S the one being decoded
    wire [7:0]  adst = (state == S_X) ? dstr : idst;
    wire [15:0] aval = (state == S_X) ? mdin : acc;
    wire        dport   = (adst >= PBASE);
    wire [3:0]  did     = adst - PBASE;
    wire        dst_wr  = (!dport) || (did == 4'd8);
    wire [7:0]  dst_adr = (dport && did == 4'd8) ? adr : adst;

    // an applied write to a PC port redirects the fetch in the same cycle
    wire jmp = dport & ((did == 4'd3) |
                        ((did == 4'd4) & (acc == 16'd0)) |
                        ((did == 4'd5) & acc[15]));
    wire [7:0] npc = jmp ? aval[7:0] : pc;

    // is this cycle one where the source value is available for the destination?
    wire applying = (state == S_X) || ((state == S_S) && !src_rd);

    always @* begin
        maddr  = pc;
        mwe    = 1'b0;
        mdout  = aval;
        ifetch = 1'b0;
        if (state == S_F) begin
            maddr = pc; ifetch = 1'b1;
        end else if ((state == S_S) && src_rd) begin
            maddr = src_adr;                       // read the source operand
        end else if (dst_wr) begin
            maddr = dst_adr; mwe = 1'b1;           // write the destination
        end else begin
            maddr = npc; ifetch = 1'b1;            // port write: fetch now
        end
    end

    always @(posedge clk) begin
        out_stb <= 1'b0;
        if (rst) begin
            pc <= 8'd0; acc <= 16'd0; adr <= 8'd0; dstr <= 8'd0; state <= S_F;
        end else begin
            if (state == S_S) dstr <= idst;
            if (state == S_F) begin
                pc    <= pc + 8'd1;
                state <= S_S;
            end else if ((state == S_S) && src_rd) begin
                state <= S_X;
            end else if (dst_wr) begin
                state <= S_F;
            end else begin
                pc    <= npc + 8'd1;
                state <= S_S;
                if (applying) case (did)
                    4'd0: acc <= aval;
                    4'd1: acc <= acc + aval;
                    4'd2: acc <= acc - aval;
                    4'd6: adr <= aval[7:0];
                    4'd7: adr <= adr + aval[7:0];
                    4'd9: begin out_val <= aval; out_stb <= 1'b1; end
                    default: ;                     // PC ports handled by npc
                endcase
            end
        end
    end
endmodule

module comp_move #(parameter AW = 8) (
    input  wire          clk,
    input  wire          rst,
    output wire [15:0]   out_val,
    output wire          out_stb,
    output wire [AW-1:0] maddr,
    output wire          mwe,
    output wire [15:0]   mdout,
    input  wire [15:0]   mdin
);
    wire ifq;
    cpu_move #(.AW(AW)) cpu (
        .clk(clk), .rst(rst), .maddr(maddr), .mwe(mwe), .mdout(mdout),
        .mdin(mdin), .ifetch(ifq), .out_val(out_val), .out_stb(out_stb));
endmodule
