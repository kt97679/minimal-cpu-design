`timescale 1ns/1ps
`include "build/params.vh"

// single-port synchronous RAM, 4096 x 16
module ram (
    input  wire        clk,
    input  wire [11:0] addr,
    input  wire        we,
    input  wire [15:0] din,
    output reg  [15:0] dout
);
    reg [15:0] mem [0:4095];
    always @(posedge clk) begin
        if (we) mem[addr] <= din;
        dout <= mem[addr];
    end
endmodule

module tb;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;

    wire [11:0] a_addr, s_addr;
    wire        a_we, s_we, a_if, s_if;
    wire [15:0] a_do, s_do, a_di, s_di;

    ram ra (.clk(clk), .addr(a_addr), .we(a_we), .din(a_do), .dout(a_di));
    ram rs (.clk(clk), .addr(s_addr), .we(s_we), .din(s_do), .dout(s_di));

    acc_cpu    ca (.clk(clk), .rst(rst), .maddr(a_addr), .mwe(a_we),
                   .mdout(a_do), .mdin(a_di), .ifetch(a_if));
    subleq_cpu cs (.clk(clk), .rst(rst), .maddr(s_addr), .mwe(s_we),
                   .mdout(s_do), .mdin(s_di), .ifetch(s_if));

    integer acyc = 0, scyc = 0, ainstr = 0, sinstr = 0;
    reg adone = 0, sdone = 0;
    integer i, errs = 0;
    reg [15:0] exp [0:99];

    initial begin
        $readmemh("build/acc.hex",      ra.mem);
        $readmemh("build/subleq.hex",   rs.mem);
        $readmemh("build/expected.txt", exp);
        @(negedge clk); rst = 0;
    end

    always @(posedge clk) if (!rst) begin
        if (!adone) begin
            acyc = acyc + 1;
            if (a_if) begin
                ainstr = ainstr + 1;
                if (a_addr == `ACC_HALT) adone = 1;
            end
        end
        if (!sdone) begin
            scyc = scyc + 1;
            if (s_if) begin
                sinstr = sinstr + 1;
                if (s_addr == `SUB_HALT) sdone = 1;
            end
        end
        if (adone && sdone) begin
            // ainstr/sinstr counted the halt fetch too
            $display("ACC    : %0d cycles, %0d instructions", acyc, ainstr - 1);
            $display("SUBLEQ : %0d cycles, %0d instructions", scyc, sinstr - 1);
            for (i = 0; i < 100; i = i + 1) begin
                if (ra.mem[`ARR_ACC + i] !== exp[i]) begin
                    errs = errs + 1;
                    $display("ACC mismatch at %0d: %h != %h", i, ra.mem[`ARR_ACC+i], exp[i]);
                end
                if (rs.mem[`ARR_SUB + i] !== exp[i]) begin
                    errs = errs + 1;
                    $display("SUB mismatch at %0d: %h != %h", i, rs.mem[`ARR_SUB+i], exp[i]);
                end
            end
            $display("verification: %0d errors", errs);
            $display("F90..F99 (mod 2^16), acc machine: %h %h %h %h %h %h %h %h %h %h",
                ra.mem[`ARR_ACC+90], ra.mem[`ARR_ACC+91], ra.mem[`ARR_ACC+92],
                ra.mem[`ARR_ACC+93], ra.mem[`ARR_ACC+94], ra.mem[`ARR_ACC+95],
                ra.mem[`ARR_ACC+96], ra.mem[`ARR_ACC+97], ra.mem[`ARR_ACC+98],
                ra.mem[`ARR_ACC+99]);
            $finish;
        end
    end

    initial begin
        #2000000;
        $display("TIMEOUT acyc=%0d scyc=%0d", acyc, scyc);
        $finish;
    end
endmodule
