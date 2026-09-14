// SUBLEQ one-instruction machine.
//   M[B] <- M[B] - M[A];  if (M[B] <= 0 signed) pc <- C  else pc <- pc+3
// Instruction = 3 consecutive 16-bit words (A, B, C), addresses are 12 bit.
// Same single-port synchronous RAM interface / 1-cycle read latency as acc_cpu.
module subleq_cpu (
    input  wire        clk,
    input  wire        rst,
    output reg  [11:0] maddr,
    output reg         mwe,
    output reg  [15:0] mdout,
    input  wire [15:0] mdin,
    output reg         ifetch     // maddr is the A-word (start of an instruction)
);
    localparam S_F  = 3'd0,  // drive addr = pc  (fetch A)
               S_A  = 3'd1,  // mdin = A, drive addr = pc (fetch B)
               S_B  = 3'd2,  // mdin = B, drive addr = pc (fetch C)
               S_C  = 3'd3,  // mdin = C, drive addr = regA
               S_VA = 3'd4,  // mdin = M[A], drive addr = regB
               S_VB = 3'd5;  // mdin = M[B], compute, write back to regB

    reg [11:0] pc, regA, regB, regC;
    reg [15:0] vA;
    reg  [2:0] state;

    wire [15:0] diff = mdin - vA;
    wire        take = (diff == 16'd0) | diff[15];   // <= 0, signed

    always @* begin
        maddr  = pc;
        mwe    = 1'b0;
        mdout  = diff;
        ifetch = (state == S_F);
        case (state)
            S_C:     maddr = regA;
            S_VA:    maddr = regB;
            S_VB: begin maddr = regB; mwe = 1'b1; end
            default: maddr = pc;                    // S_F / S_A / S_B
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            pc <= 12'd0; state <= S_F;
            regA <= 12'd0; regB <= 12'd0; regC <= 12'd0; vA <= 16'd0;
        end else begin
            case (state)
                S_F:  begin pc <= pc + 12'd1; state <= S_A; end
                S_A:  begin regA <= mdin[11:0]; pc <= pc + 12'd1; state <= S_B; end
                S_B:  begin regB <= mdin[11:0]; pc <= pc + 12'd1; state <= S_C; end
                S_C:  begin regC <= mdin[11:0]; state <= S_VA; end
                S_VA: begin vA <= mdin; state <= S_VB; end
                default: begin                        // S_VB
                    if (take) pc <= regC;
                    state <= S_F;                     // pc already = instr+3
                end
            endcase
        end
    end
endmodule
