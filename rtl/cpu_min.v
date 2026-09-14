// Two extreme design points, for the ends of the sweep.
//
// cpu_fib2 : a register machine with two 16-bit data registers and a counter.
//            No data memory at all, so every instruction is 1 cycle. This is
//            deliberately specialised towards the benchmark -- it is here to
//            show what "optimising for one program" converges to.
//
// fib_fsm  : no instruction set, no program memory. The benchmark burned
//            directly into a state machine. This is the true floor.

// ---------------------------------------------------------------- cpu_fib2
//   0 LDIA i   A <- imm        4 OUTB     port <- B
//   1 LDIB i   B <- imm        5 ADDBA    A <- A + B
//   2 LDC  i   C <- imm        6 ADDAB    B <- B + A
//   3 OUTA     port <- A       7 DJNZ a   C--, if C != 0 pc <- a
//                              8 JMP  a
module cpu_fib2 #(parameter AW = 4) (
    input  wire          clk,
    input  wire          rst,
    output wire [AW-1:0] maddr,
    input  wire [15:0]   mdin,
    output reg  [15:0]   out_val,
    output reg           out_stb
);
    reg [AW-1:0] pc;
    reg [15:0]   ra, rb;
    reg [7:0]    rc;
    reg          run;

    wire [3:0]    op   = mdin[15:12];
    wire [AW-1:0] ad   = mdin[AW-1:0];
    wire          c_go = (rc != 8'd1);
    // Branch targets are driven combinationally in the same cycle, so a taken
    // branch costs no bubble -- the same trick cpu_acc uses for JZ/JMP.
    wire          brt  = run & (((op == 4'd7) & c_go) | (op == 4'd8));

    assign maddr = brt ? ad : pc;

    always @(posedge clk) begin
        out_stb <= 1'b0;
        if (rst) begin
            pc <= {AW{1'b0}}; ra <= 16'd0; rb <= 16'd0; rc <= 8'd0; run <= 1'b0;
        end else begin
            run <= 1'b1;
            pc  <= maddr + 1'b1;
            if (run) case (op)
                4'd0: ra <= {8'd0, mdin[7:0]};
                4'd1: rb <= {8'd0, mdin[7:0]};
                4'd2: rc <= mdin[7:0];
                4'd3: begin out_val <= ra; out_stb <= 1'b1; end
                4'd4: begin out_val <= rb; out_stb <= 1'b1; end
                4'd5: ra <= ra + rb;
                4'd6: rb <= rb + ra;
                4'd7: rc <= rc - 8'd1;
                default: ;
            endcase
        end
    end
endmodule

// ---------------------------------------------------------------- fib_fsm
module fib_fsm (
    input  wire        clk,
    input  wire        rst,
    output reg  [15:0] out_val,
    output reg         out_stb
);
    reg [15:0] a, b;
    reg [7:0]  c;
    reg [1:0]  s;
    wire [15:0] sum = a + b;

    always @(posedge clk) begin
        out_stb <= 1'b0;
        if (rst) begin
            a <= 16'd0; b <= 16'd1; c <= 8'd50; s <= 2'd0;
        end else case (s)
            2'd0: begin out_val <= a; out_stb <= 1'b1; s <= 2'd1; end
            2'd1: begin out_val <= b; out_stb <= 1'b1; a <= sum; s <= 2'd2; end
            2'd2: begin b <= sum; c <= c - 8'd1;      // a already updated
                        s <= (c != 8'd1) ? 2'd0 : 2'd3; end
            default: s <= 2'd3;
        endcase
    end
endmodule

// ------------------------------------------------------- system wrappers
// The output port (16-bit register + strobe + address decode) is inside the
// synthesised "core" for every design, so all design points carry it equally.

module comp_fib2 #(parameter AW = 4) (
    input  wire        clk,
    input  wire        rst,
    output wire [15:0] out_val,
    output wire        out_stb,
    output wire [AW-1:0] maddr,
    input  wire [15:0]   mdin
);
    cpu_fib2 #(.AW(AW)) cpu (
        .clk(clk), .rst(rst), .maddr(maddr), .mdin(mdin),
        .out_val(out_val), .out_stb(out_stb));
endmodule
