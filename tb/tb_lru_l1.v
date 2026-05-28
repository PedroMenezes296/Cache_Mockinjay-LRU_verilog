// Testbench: lru_l1_cache
// Replica os 8 acessos de trace_validacao.txt com política LRU.
// Resultado esperado: 2 hits, 6 misses (25% hit rate).
// Referência: validacao/LRU-GIOVANA.txt
`timescale 1ns/1ps
module tb_lru_l1;
    reg  clk, rst_n, access_en;
    reg  [20:0] tag_in;
    reg  [5:0]  set_index_in;
    wire        hit, l2_access_needed, way_used, done;

    lru_l1_cache dut(
        .clk(clk), .rst_n(rst_n), .access_en(access_en),
        .tag_in(tag_in), .set_index_in(set_index_in),
        .hit(hit), .l2_access_needed(l2_access_needed),
        .way_used(way_used), .done(done)
    );

    always #5 clk = ~clk;

    // trace_validacao.txt: 0x0000 A, 0x0800 B, 0x0000 A, 0x0800 B, 0x1000 C, 0x0000 A, 0x0800 B, 0x1000 C
    // Para L1: set=(addr>>5)%64, tag=addr>>11
    // 0x0000: set=0, tag=0 (A)
    // 0x0800: set=0, tag=1 (B)
    // 0x1000: set=0, tag=2 (C)
    reg [26:0] trace [0:7]; // {set[5:0], tag[20:0]}
    integer i, hits, misses;

    task do_access;
        input [5:0]  s;
        input [20:0] t;
        input integer idx;
        begin
            set_index_in=s; tag_in=t; access_en=1;
            @(posedge clk); #1 access_en=0;
            wait(done);
            @(posedge clk); #1;
            $display("Acesso %0d (set=%0d tag=%0d): %s",
                      idx+1, s, t, hit ? "HIT" : "MISS");
            if (hit) hits=hits+1; else misses=misses+1;
        end
    endtask

    initial begin
        clk=0; rst_n=0; access_en=0; hits=0; misses=0;
        @(posedge clk); #1 rst_n=1; @(posedge clk);

        do_access(6'd0, 21'd0, 0); // A - MISS
        do_access(6'd0, 21'd1, 1); // B - MISS
        do_access(6'd0, 21'd0, 2); // A - HIT
        do_access(6'd0, 21'd1, 3); // B - HIT
        do_access(6'd0, 21'd2, 4); // C - MISS (expulsa A, LRU)
        do_access(6'd0, 21'd0, 5); // A - MISS (foi expulso)
        do_access(6'd0, 21'd1, 6); // B - MISS (expulsa B? depende do estado LRU)
        do_access(6'd0, 21'd2, 7); // C - MISS

        $display("=== LRU L1 ===");
        $display("Hits: %0d | Misses: %0d | Hit Rate: %.1f%%",
                  hits, misses, (hits*100.0)/(hits+misses));
        $display("Esperado: 2 hits, 6 misses (25%%)");

        if (hits==2 && misses==6)
            $display("RESULTADO: CORRETO");
        else
            $display("RESULTADO: INCORRETO — revisar logica LRU");

        $finish;
    end
endmodule
