module top_acc(input clk, input rst, output [15:0] probe);
  wire [11:0] a; wire we; wire [15:0] wd, rd; wire iff;
  reg [15:0] mem [0:1023]; reg [15:0] dout;
  always @(posedge clk) begin if (we) mem[a[9:0]] <= wd; dout <= mem[a[9:0]]; end
  assign rd = dout;
  acc_cpu u(.clk(clk),.rst(rst),.maddr(a),.mwe(we),.mdout(wd),.mdin(rd),.ifetch(iff));
  assign probe = rd;
endmodule
module top_sub(input clk, input rst, output [15:0] probe);
  wire [11:0] a; wire we; wire [15:0] wd, rd; wire iff;
  reg [15:0] mem [0:1023]; reg [15:0] dout;
  always @(posedge clk) begin if (we) mem[a[9:0]] <= wd; dout <= mem[a[9:0]]; end
  assign rd = dout;
  subleq_cpu u(.clk(clk),.rst(rst),.maddr(a),.mwe(we),.mdout(wd),.mdin(rd),.ifetch(iff));
  assign probe = rd;
endmodule
