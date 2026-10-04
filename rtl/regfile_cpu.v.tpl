// Register-file machine: {op[3:0], reg[RB-1:0], addr[AW-1:0]}
// Per-register opcodes do not scale -- 8 registers would need 38 of them and a
// 4-bit opcode allows 16 -- so the register is a field, selecting into a file.
module gcpu #(parameter R = RVAL, parameter RB = RBVAL, parameter AW = 9) (
    input wire clk, input wire rst,
    output reg [AW-1:0] maddr, output reg mwe, output reg [15:0] mdout,
    input wire [15:0] mdin, output reg ifetch);
    localparam S_D = 2'd0, S_E = 2'd1, S_W = 2'd2, S_F = 2'd3;
    reg [AW-1:0] pc; reg [3:0] op; reg [1:0] state; reg [RB-1:0] rs;
    reg [7:0] xreg;
    reg [15:0] rf [0:R-1];
    integer i;
    wire [3:0] iop = mdin[15:12];
    wire [RB-1:0] ireg = mdin[11:12-RB];
    wire [AW-1:0] iad = mdin[AW-1:0];
    wire [15:0] cur = rf[ireg];
    wire zf = (cur == 16'd0); wire nf = cur[15];
    wire [AW-1:0] xad = iad + xreg;
    always @* begin
        maddr = pc; mwe = 1'b0; mdout = cur; ifetch = 1'b0;
        case (state)
            4'd0: ;
            default: ;
        endcase
        case (state)
            S_D: case (iop)
                4'd0, 4'd2, 4'd3: maddr = iad;              // LD / ADD / SUB
                4'd1: begin maddr = iad; mwe = 1'b1; end     // ST
                4'd4: begin maddr = pc; ifetch = 1'b1; end   // MOV r, r'
                4'd5: begin maddr = zf ? iad : pc; ifetch = 1'b1; end
                4'd6: begin maddr = nf ? iad : pc; ifetch = 1'b1; end
                4'd7: begin maddr = iad; ifetch = 1'b1; end  // JMP
                4'd8: maddr = iad;                           // LDX
                4'd9: maddr = xad;                           // LDAX
                4'd10: begin maddr = xad; mwe = 1'b1; end    // STAX
                default: maddr = iad;
            endcase
            default: begin maddr = pc; ifetch = 1'b1; end
        endcase
    end
    always @(posedge clk) begin
        if (rst) begin
            pc <= {AW{1'b0}}; state <= S_F; op <= 4'd0; xreg <= 8'd0;
            rs <= {RB{1'b0}};
            for (i = 0; i < R; i = i + 1) rf[i] <= 16'd0;
        end else case (state)
            S_D: begin op <= iop; rs <= ireg; case (iop)
                4'd0, 4'd2, 4'd3, 4'd8, 4'd9: state <= S_E;
                4'd1, 4'd10: state <= S_W;
                4'd4: begin rf[ireg] <= rf[iad[RB-1:0]];
                            pc <= pc + 1'b1; state <= S_D; end
                4'd5: begin pc <= (zf ? iad : pc) + 1'b1; state <= S_D; end
                4'd6: begin pc <= (nf ? iad : pc) + 1'b1; state <= S_D; end
                4'd7: begin pc <= iad + 1'b1; state <= S_D; end
                default: state <= S_E;
            endcase end
            S_E: begin
                case (op)
                    4'd0, 4'd9: rf[rs] <= mdin;
                    4'd2: rf[rs] <= rf[rs] + mdin;
                    4'd3: rf[rs] <= rf[rs] - mdin;
                    4'd8: xreg <= mdin[7:0];
                    default: ;
                endcase
                pc <= pc + 1'b1; state <= S_D;
            end
            default: begin pc <= pc + 1'b1; state <= S_D; end
        endcase
    end
endmodule
