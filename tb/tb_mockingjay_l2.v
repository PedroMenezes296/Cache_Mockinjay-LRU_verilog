// Testbench unitário: mockingjay_l2_cache (8 vias, política Mockingjay/ETR).
// Cobre: hit/miss básico, preenchimento das 8 vias, HIT com way_used correto,
// aprendizado de intervalo e seleção de vítima pela árvore de comparadores (maior eff).
//
// Rodar: iverilog -o tb_l2 rtl/etr_calculator.v rtl/mockingjay_l2_cache.v tb/tb_mockingjay_l2.v && vvp tb_l2
`timescale 1ns/1ps
module tb_mockingjay_l2;
    reg  clk, rst_n, access_en;
    reg  [19:0] tag_in;
    reg  [5:0]  set_index_in;
    reg  [3:0]  global_time;
    wire        hit, done;
    wire [2:0]  way_used;

    mockingjay_l2_cache dut(
        .clk(clk), .rst_n(rst_n), .access_en(access_en),
        .tag_in(tag_in), .set_index_in(set_index_in),
        .global_time(global_time),
        .hit(hit), .way_used(way_used), .done(done)
    );

    always #5 clk = ~clk;

    integer erros;

    // Executa um acesso de 1 ciclo (protocolo idêntico ao do L1) e devolve hit/way.
    task do_access;
        input [5:0]  s;
        input [19:0] t;
        input [3:0]  gt;
        begin
            global_time=gt; set_index_in=s; tag_in=t; access_en=1;
            @(posedge clk); #1 access_en=0;
            wait(done);
            @(posedge clk); #1;
        end
    endtask

    task expect_miss;
        input [5:0] s; input [19:0] t; input [3:0] gt;
        begin
            do_access(s,t,gt);
            if (hit !== 1'b0) begin erros=erros+1; $display("FALHOU: tag=%0d esperava MISS, veio HIT", t); end
            else $display("PASSOU: tag=%0d MISS (way_used=%0d)", t, way_used);
        end
    endtask

    task expect_hit;
        input [5:0] s; input [19:0] t; input [3:0] gt; input [2:0] exp_way;
        begin
            do_access(s,t,gt);
            if (hit !== 1'b1) begin erros=erros+1; $display("FALHOU: tag=%0d esperava HIT, veio MISS", t); end
            else if (way_used !== exp_way) begin erros=erros+1; $display("FALHOU: tag=%0d HIT mas way=%0d (esp %0d)", t, way_used, exp_way); end
            else $display("PASSOU: tag=%0d HIT na via %0d", t, way_used);
        end
    endtask

    initial begin
        clk=0; rst_n=0; access_en=0; global_time=0; erros=0;
        @(posedge clk); #1 rst_n=1; @(posedge clk);

        $display("--- Preenche as 8 vias do conjunto 0 (tags 0..7, tempos 1..8) ---");
        expect_miss(6'd0, 20'd0, 4'd1); // way0
        expect_miss(6'd0, 20'd1, 4'd2); // way1
        expect_miss(6'd0, 20'd2, 4'd3); // way2
        expect_miss(6'd0, 20'd3, 4'd4); // way3
        expect_miss(6'd0, 20'd4, 4'd5); // way4
        expect_miss(6'd0, 20'd5, 4'd6); // way5
        expect_miss(6'd0, 20'd6, 4'd7); // way6
        expect_miss(6'd0, 20'd7, 4'd8); // way7  (conjunto cheio)

        $display("--- HIT na tag 0 (via 0): aprende intervalo = 9-1 = 8 ---");
        expect_hit(6'd0, 20'd0, 4'd9, 3'd0);

        // Estado de ETR no tempo 10 (eff = ETR, nenhum negativo aqui):
        //   way0 tag0: last=9 int=8 -> ETR=7
        //   way1 tag1: last=2 int=15 -> ETR=7
        //   way2 tag2: last=3 int=15 -> ETR=8
        //   way3 tag3: last=4 int=15 -> ETR=9
        //   way4 tag4: last=5 int=15 -> ETR=10
        //   way5 tag5: last=6 int=15 -> ETR=11
        //   way6 tag6: last=7 int=15 -> ETR=12
        //   way7 tag7: last=8 int=15 -> ETR=13  <- MAIOR -> vítima
        $display("--- MISS tag 8 (cheio): deve expulsar a via 7 (maior ETR=13) ---");
        expect_miss(6'd0, 20'd8, 4'd10);
        if (way_used !== 3'd7) begin erros=erros+1; $display("FALHOU: vítima foi via %0d, esperado via 7", way_used); end
        else $display("PASSOU: vítima correta = via 7");

        $display("--- Confirma: tag 7 foi expulsa (MISS), tag 0 permanece (HIT) ---");
        // tag 0 ainda na via 0:
        expect_hit(6'd0, 20'd0, 4'd11, 3'd0);
        // tag 7 deve ter virado MISS (foi substituída por tag 8 na via 7):
        do_access(6'd0, 20'd7, 4'd12);
        if (hit !== 1'b0) begin erros=erros+1; $display("FALHOU: tag 7 deveria ser MISS (foi expulsa)"); end
        else $display("PASSOU: tag 7 é MISS (confirmou expulsão)");

        $display("--- Conjunto independente: tag 0 no conjunto 5 deve ser MISS ---");
        expect_miss(6'd5, 20'd0, 4'd13);

        $display("=== TB_MOCKINGJAY_L2: %0d erro(s) ===", erros);
        if (erros==0) $display("RESULTADO: CORRETO"); else $display("RESULTADO: INCORRETO");
        $finish;
    end
endmodule
