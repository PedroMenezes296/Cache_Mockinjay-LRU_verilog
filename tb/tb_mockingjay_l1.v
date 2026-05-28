// Testbench: mockingjay_l1_cache
// Replica os 8 acessos de trace_validacao.txt com Mockingjay.
// Resultado esperado: 4 hits, 4 misses (50% hit rate).
// Referência: validacao/MOCKINGJAY-PERAÇA.txt
//
// Trace: A A B B A B A B  (endereços 0x0000 0x0800 0x0000 0x0800 0x1000 0x0000 0x0800 0x1000)
// Decisão chave (acesso 5 - C chega, cache cheia com A e B):
//   A aprendeu intervalo=2 (acessada nos clocks 1 e 3) → ETR_A = (3+2)-5 = 0 → negativo → MAX
//   B aprendeu intervalo=2 (acessada nos clocks 2 e 4) → ETR_B = (4+2)-5 = 1 → positivo
//   Mockingjay expulsa B (maior ETR real = 1 vs MAX do A) ← A tem MAX que é "pior"
//   Espera: A permanece, B é expulso → acesso 6 (A) é HIT
`timescale 1ns/1ps
module tb_mockingjay_l1;
    reg  clk, rst_n, access_en;
    reg  [20:0] tag_in;
    reg  [5:0]  set_index_in;
    reg  [3:0]  global_time;
    wire        hit, l2_access_needed, way_used, done;

    mockingjay_l1_cache dut(
        .clk(clk), .rst_n(rst_n), .access_en(access_en),
        .tag_in(tag_in), .set_index_in(set_index_in),
        .global_time(global_time),
        .hit(hit), .l2_access_needed(l2_access_needed),
        .way_used(way_used), .done(done)
    );

    always #5 clk = ~clk;

    integer i, hits, misses;

    task do_access;
        input [5:0]  s;
        input [20:0] t;
        input integer idx;
        begin
            global_time = idx + 1; // relogio incrementa por acesso
            set_index_in=s; tag_in=t; access_en=1;
            @(posedge clk); #1 access_en=0;
            wait(done);
            @(posedge clk); #1;
            $display("Acesso %0d (set=%0d tag=%0d clock=%0d): %s",
                      idx+1, s, t, global_time, hit ? "HIT" : "MISS");
            if (hit) hits=hits+1; else misses=misses+1;
        end
    endtask

    initial begin
        clk=0; rst_n=0; access_en=0; global_time=0; hits=0; misses=0;
        @(posedge clk); #1 rst_n=1; @(posedge clk);

        do_access(6'd0, 21'd0, 0); // clock=1: A - MISS
        do_access(6'd0, 21'd1, 1); // clock=2: B - MISS
        do_access(6'd0, 21'd0, 2); // clock=3: A - HIT (aprende intervalo=2)
        do_access(6'd0, 21'd1, 3); // clock=4: B - HIT (aprende intervalo=2)
        do_access(6'd0, 21'd2, 4); // clock=5: C - MISS (expulsa B, ETR_A<=0)
        do_access(6'd0, 21'd0, 5); // clock=6: A - HIT (Mockingjay acertou!)
        do_access(6'd0, 21'd1, 6); // clock=7: B - MISS (expulsa C)
        do_access(6'd0, 21'd2, 7); // clock=8: C - HIT

        $display("=== MOCKINGJAY L1 ===");
        $display("Hits: %0d | Misses: %0d | Hit Rate: %.1f%%",
                  hits, misses, (hits*100.0)/(hits+misses));
        $display("Esperado: 4 hits, 4 misses (50%%)");

        if (hits==4 && misses==4)
            $display("RESULTADO: CORRETO - Mockingjay superou LRU!");
        else
            $display("RESULTADO: INCORRETO — revisar logica ETR");

        $finish;
    end
endmodule
