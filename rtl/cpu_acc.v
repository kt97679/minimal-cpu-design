// Accumulator CPU with instruction groups selectable at compile time, so that
// every design point in the sweep shares one microarchitecture and the only
// variable is the instruction set.
//
//   (always)      0 LDA m   1 STA m   2 JZ a    3 SUB m
//   HAS_ADD       4 ADD m
//   HAS_JMP       5 JMP a
//   HAS_CTR       6 LDC i   7 DJNZ a        (8-bit counter register)
//   HAS_LOGIC     8 AND m   9 OR m    10 XOR m  11 SHR
//   HAS_SIGN     12 JN a                        (branch on acc[15])
//   HAS_INDEX    13 LDX m  14 LDAX m  15 STAX m (8-bit index register X)
//
// Word = 16 bit: {op[3:0], addr/imm[11:0]}.  Single-port synchronous RAM,
// 1-cycle read latency, next fetch overlapped with the last cycle of the
// current instruction -- identical to the original two designs.
module cpu_acc #(parameter AW = 8) (
    input  wire          clk,
    input  wire          rst,
    output reg  [AW-1:0] maddr,
    output reg           mwe,
    output reg  [15:0]   mdout,
    input  wire [15:0]   mdin,
    output reg           ifetch
);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;

    reg [AW-1:0] pc;
    reg [15:0]   acc;
    reg [3:0]    op;
    reg [1:0]    state;
`ifdef HAS_CTR
    reg [7:0]    ctr;
    wire         ctr_go = (ctr != 8'd1);
`endif
`ifdef HAS_INDEX
    reg [7:0]    xreg;
`endif

    wire [3:0]    iop  = mdin[15:12];
    wire [AW-1:0] iad  = mdin[AW-1:0];
    wire          zero = (acc == 16'd0);
`ifdef HAS_INDEX
    wire [AW-1:0] xad  = iad + xreg;   // xreg zero-extends to AW
`endif

    always @* begin
        maddr  = pc;
        mwe    = 1'b0;
        mdout  = acc;
        ifetch = 1'b0;
        case (state)
            S_D: case (iop)
                4'd1: begin maddr = iad; mwe = 1'b1; end             // STA
                4'd2: begin maddr = zero ? iad : pc; ifetch = 1'b1; end
`ifdef HAS_JMP
                4'd5: begin maddr = iad; ifetch = 1'b1; end
`endif
`ifdef HAS_CTR
                4'd6: begin maddr = pc; ifetch = 1'b1; end           // LDC
                4'd7: begin maddr = ctr_go ? iad : pc; ifetch = 1'b1; end
`endif
`ifdef HAS_SIGN
                4'd12: begin maddr = acc[15] ? iad : pc; ifetch = 1'b1; end
`endif
`ifdef HAS_INDEX
                4'd14: maddr = xad;                                  // LDAX
                4'd15: begin maddr = xad; mwe = 1'b1; end            // STAX
`endif
                default: maddr = iad;                                // operand fetch
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end            // S_E / S_W / S_F
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            pc <= {AW{1'b0}}; acc <= 16'd0; state <= S_F; op <= 4'd0;
`ifdef HAS_CTR
            ctr <= 8'd0;
`endif
`ifdef HAS_INDEX
            xreg <= 8'd0;
`endif
        end else begin
            case (state)
                S_D: begin
                    op <= iop;
                    case (iop)
                        4'd1: state <= S_W;
                        4'd2: begin
                            pc    <= (zero ? iad : pc) + 1'b1;
                            state <= S_D;
                        end
`ifdef HAS_JMP
                        4'd5: begin pc <= iad + 1'b1; state <= S_D; end
`endif
`ifdef HAS_CTR
                        4'd6: begin ctr <= mdin[7:0]; pc <= pc + 1'b1; state <= S_D; end
                        4'd7: begin
                            ctr   <= ctr - 8'd1;
                            pc    <= (ctr_go ? iad : pc) + 1'b1;
                            state <= S_D;
                        end
`endif
`ifdef HAS_SIGN
                        4'd12: begin
                            pc    <= (acc[15] ? iad : pc) + 1'b1;
                            state <= S_D;
                        end
`endif
`ifdef HAS_INDEX
                        4'd15: state <= S_W;                         // STAX
`endif
                        default: state <= S_E;
                    endcase
                end
                S_E: begin
                    case (op)
                        4'd0:    acc <= mdin;
                        4'd3:    acc <= acc - mdin;
`ifdef HAS_ADD
                        4'd4:    acc <= acc + mdin;
`endif
`ifdef HAS_LOGIC
                        4'd8:    acc <= acc & mdin;
                        4'd9:    acc <= acc | mdin;
                        4'd10:   acc <= acc ^ mdin;
                        4'd11:   acc <= {1'b0, acc[15:1]};
`endif
`ifdef HAS_INDEX
                        4'd14:   acc <= mdin;                        // LDAX
`endif
                        default: acc <= acc;
                    endcase
`ifdef HAS_INDEX
                    if (op == 4'd13) xreg <= mdin[7:0];              // LDX
`endif
                    pc    <= pc + 1'b1;
                    state <= S_D;
                end
                default: begin pc <= pc + 1'b1; state <= S_D; end     // S_W / S_F
            endcase
        end
    end
endmodule

module comp_acc #(parameter N = 29, AW = 5) (
    input  wire        clk,
    input  wire        rst,
    output reg  [15:0] out_val,
    output reg         out_stb,
    output wire [AW-1:0] maddr,
    output wire          mwe,
    output wire [15:0]   mdout,
    input  wire [15:0]   mdin
);
    wire ifq;
    wire port = mwe & (maddr == N[AW-1:0]);

    cpu_acc #(.AW(AW)) cpu (
        .clk(clk), .rst(rst), .maddr(maddr), .mwe(mwe),
        .mdout(mdout), .mdin(mdin), .ifetch(ifq));

    always @(posedge clk) begin
        out_stb <= port;
        if (port) out_val <= mdout;
    end
endmodule

