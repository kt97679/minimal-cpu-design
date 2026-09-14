// 4-instruction accumulator machine.
// Word = 16 bit, instr = {2'b??, op[1:0], addr[11:0]}
//   op 00 LOAD  acc <- M[addr]
//   op 01 STORE M[addr] <- acc
//   op 10 JZ    if (acc==0) pc <- addr
//   op 11 SUB   acc <- acc - M[addr]
// Single-port synchronous RAM: address driven combinationally this cycle,
// data arrives next cycle.  Next fetch is overlapped with the last cycle of
// the current instruction.
module acc_cpu (
    input  wire        clk,
    input  wire        rst,
    output reg  [11:0] maddr,
    output reg         mwe,
    output reg  [15:0] mdout,
    input  wire [15:0] mdin,
    output reg         ifetch      // this cycle's maddr is an instruction fetch
);
    localparam S_D = 2'd0,   // decode: mdin = instruction word
               S_E = 2'd1,   // execute: mdin = operand data (LOAD/SUB)
               S_W = 2'd2;   // store wrote last cycle, now refetch

    reg [11:0] pc;
    reg [15:0] acc;
    reg  [1:0] state;
    reg        is_sub;       // 0 = LOAD, 1 = SUB

    wire [1:0]  op  = mdin[13:12];
    wire [11:0] adr = mdin[11:0];
    wire        zero = (acc == 16'd0);

    always @* begin
        maddr  = pc;
        mwe    = 1'b0;
        mdout  = acc;
        ifetch = 1'b0;
        case (state)
            S_D: case (op)
                     2'b00, 2'b11: maddr = adr;              // LOAD / SUB operand
                     2'b01: begin maddr = adr; mwe = 1'b1; end // STORE
                     default: begin                           // JZ: fetch next
                         maddr  = zero ? adr : pc;
                         ifetch = 1'b1;
                     end
                 endcase
            default: begin maddr = pc; ifetch = 1'b1; end     // S_E / S_W refetch
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            pc <= 12'd0; acc <= 16'd0; state <= 2'd3; is_sub <= 1'b0;
        end else begin
            case (state)
                S_D: begin
                    is_sub <= op[0];
                    case (op)
                        2'b00, 2'b11: state <= S_E;
                        2'b01:        state <= S_W;
                        default: begin                       // JZ
                            if (zero) pc <= adr + 12'd1;
                            else      pc <= pc + 12'd1;
                            state <= S_D;
                        end
                    endcase
                end
                S_E: begin
                    acc   <= is_sub ? (acc - mdin) : mdin;
                    pc    <= pc + 12'd1;
                    state <= S_D;
                end
                default: begin                               // S_W
                    pc    <= pc + 12'd1;
                    state <= S_D;
                end
            endcase
        end
    end
endmodule
