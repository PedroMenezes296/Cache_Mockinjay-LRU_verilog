// Testbench: saturating_counter_4bit
// Verifica que o contador satura em 15 e que load funciona.
`timescale 1ns/1ps
module tb_saturating_counter;
    reg clk, rst_n, enable, load_en;
    reg [3:0] load_val;
    wire [3:0] count;

    saturating_counter_4bit dut(
        .clk(clk), .rst_n(rst_n), .enable(enable),
        .load_val(load_val), .load_en(load_en), .count(count)
    );

    always #5 clk = ~clk;

    integer i;
    initial begin
        clk=0; rst_n=0; enable=0; load_en=0; load_val=0;
        @(posedge clk); #1 rst_n=1;

        // Teste 1: incrementar 20 vezes, deve parar em 15
        enable=1;
        for (i=0; i<20; i=i+1) begin
            @(posedge clk);
            $display("Ciclo %0d: count=%0d", i+1, count);
        end
        enable=0;
        if (count !== 4'd15)
            $display("FALHOU: esperado 15, obteve %0d", count);
        else
            $display("PASSOU: saturacao em 15 OK");

        // Teste 2: load de valor 7
        @(posedge clk); #1 load_val=4'd7; load_en=1;
        @(posedge clk); #1 load_en=0;
        @(posedge clk);
        if (count !== 4'd7)
            $display("FALHOU: load esperado 7, obteve %0d", count);
        else
            $display("PASSOU: load OK");

        // Teste 3: incrementar a partir de 7 até 15
        enable=1;
        for (i=0; i<10; i=i+1) @(posedge clk);
        enable=0;
        if (count !== 4'd15)
            $display("FALHOU: re-saturacao esperado 15, obteve %0d", count);
        else
            $display("PASSOU: re-saturacao a partir de 7 OK");

        $finish;
    end
endmodule
