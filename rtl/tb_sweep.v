`timescale 1ns/1ps
`ifndef NOUT
 `define NOUT 100
`endif
// Generic sweep testbench. Select a design with -DDUT_xxx and pass its memory
// size with -DNWORDS / -DAWIDTH. Counts cycles to the 100th output strobe and
// checks the emitted stream against build/expected.txt.
module tb;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;

    wire [15:0] out_val;
    wire        out_stb;

`ifdef DUT_FSM
    fib_fsm dut (.clk(clk), .rst(rst), .out_val(out_val), .out_stb(out_stb));
`else
    wire [`AWIDTH-1:0] maddr;
    wire [15:0]        rd;
 `ifdef DUT_FIB2
    wire mwe = 1'b0;
    wire [15:0] wd = 16'd0;
    comp_fib2 #(.AW(`AWIDTH)) dut (
        .clk(clk), .rst(rst), .out_val(out_val), .out_stb(out_stb),
        .maddr(maddr), .mdin(rd));
 `elsif DUT_SUBLEQ
    wire mwe;
    wire [15:0] wd;
    comp_subleq #(.N(`NWORDS), .AW(`AWIDTH)) dut (
        .clk(clk), .rst(rst), .out_val(out_val), .out_stb(out_stb),
        .maddr(maddr), .mwe(mwe), .mdout(wd), .ram_dout(rd));
 `else
    wire mwe;
    wire [15:0] wd;
    comp_acc #(.N(`NWORDS), .AW(`AWIDTH)) dut (
        .clk(clk), .rst(rst), .out_val(out_val), .out_stb(out_stb),
        .maddr(maddr), .mwe(mwe), .mdout(wd), .mdin(rd));
 `endif
    ramg #(.N(`NWORDS), .AW(`AWIDTH)) ram (
        .clk(clk), .addr(maddr), .we(mwe), .din(wd), .dout(rd));
`endif

    integer cyc = 0, nout = 0, errs = 0;
    reg [15:0] exp [0:`NOUT-1];

    initial begin
`ifndef DUT_FSM
        $readmemh(`HEXFILE, ram.mem);
`endif
        $readmemh("build/expected.txt", exp);
        @(negedge clk); rst = 0;
    end

    always @(posedge clk) if (!rst) begin
        cyc = cyc + 1;
        if (out_stb) begin
            if (nout < `NOUT && out_val !== exp[nout]) begin
                errs = errs + 1;
                if (errs < 5)
                    $display("  mismatch at %0d: got %h expected %h",
                             nout, out_val, exp[nout]);
            end
            nout = nout + 1;
            if (nout == `NOUT) begin
                $display("RESULT cycles=%0d outputs=%0d errors=%0d", cyc, nout, errs);
                $finish;
            end
        end
    end

    initial begin
        #50000000;
        $display("RESULT TIMEOUT cyc=%0d outputs=%0d", cyc, nout);
        $finish;
    end
endmodule
