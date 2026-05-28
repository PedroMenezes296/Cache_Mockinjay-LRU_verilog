// Testbench de integração completa: cache_controller (L1 + L2)
// Carrega traces via $readmemh e exibe estatísticas para comparar com simulador C.
//
// Para rodar com Icarus Verilog:
//   iverilog -o sim_out -I../rtl ../rtl/*.v tb_cache_top.v && vvp sim_out
`timescale 1ns/1ps
module tb_cache_top;
    reg  clk, rst_n, start, policy_sel;
    reg  [31:0] address;
    wire        result_valid, l1_hit_out, l2_hit_out, full_miss_out;
    wire [2:0]  state_debug;

    cache_controller dut(
        .clk(clk), .rst_n(rst_n),
        .start(start), .address(address),
        .policy_sel(policy_sel),
        .result_valid(result_valid),
        .l1_hit_out(l1_hit_out),
        .l2_hit_out(l2_hit_out),
        .full_miss_out(full_miss_out),
        .state_debug(state_debug)
    );

    always #5 clk = ~clk;

    reg [31:0] trace_mem [0:2047];
    integer i, num_acessos;
    integer hits_l1, misses_l1, hits_l2, misses_l2;

    task run_trace;
        input [127:0] nome;
        input integer n;
        input         pol;
        begin
            // Reset
            rst_n=0; start=0; policy_sel=pol;
            @(posedge clk); @(posedge clk); #1 rst_n=1;
            @(posedge clk);

            hits_l1=0; misses_l1=0; hits_l2=0; misses_l2=0;

            for (i=0; i<n; i=i+1) begin
                address = trace_mem[i];
                @(posedge clk); #1 start=1;
                @(posedge clk); #1 start=0;
                // Aguarda resultado
                wait(result_valid == 1'b1);
                @(posedge clk); #1;

                if (l1_hit_out) begin
                    hits_l1 = hits_l1 + 1;
                    $display("[%0d] 0x%h → L1 HIT", i+1, address);
                end else if (l2_hit_out) begin
                    misses_l1 = misses_l1 + 1;
                    hits_l2   = hits_l2 + 1;
                    $display("[%0d] 0x%h → L1 MISS | L2 HIT", i+1, address);
                end else begin
                    misses_l1 = misses_l1 + 1;
                    misses_l2 = misses_l2 + 1;
                    $display("[%0d] 0x%h → L1 MISS | L2 MISS", i+1, address);
                end
            end

            $display("=== %s | Politica: %s ===", nome, pol ? "MOCKINGJAY" : "LRU");
            $display("[L1] Hits: %0d  Misses: %0d  HitRate: %.1f%%",
                hits_l1, misses_l1, (n>0) ? (hits_l1*100.0)/n : 0.0);
            $display("[L2] Hits: %0d  Misses: %0d  HitRate: %.1f%%",
                hits_l2, misses_l2, (misses_l1>0) ? (hits_l2*100.0)/misses_l1 : 0.0);
            $display("");
        end
    endtask

    initial begin
        clk=0;

        // -------------------------------------------------------
        // Teste 1: trace_validacao (8 acessos) — Mockingjay
        // Esperado: L1 4H/4M (50%)
        // -------------------------------------------------------
        $readmemh("sim/traces_hex/trace_validacao.mem", trace_mem);
        run_trace("trace_validacao", 8, 1'b1);

        // -------------------------------------------------------
        // Teste 2: trace_validacao (8 acessos) — LRU
        // Esperado: L1 2H/6M (25%)
        // -------------------------------------------------------
        $readmemh("sim/traces_hex/trace_validacao.mem", trace_mem);
        run_trace("trace_validacao", 8, 1'b0);

        // -------------------------------------------------------
        // Teste 3: trace_mixed_hotset (8 acessos) — Mockingjay
        // Esperado: L1 4H/4M, L2 1H/3M
        // -------------------------------------------------------
        $readmemh("sim/traces_hex/trace_mixed_hotset.mem", trace_mem);
        run_trace("trace_mixed_hotset", 8, 1'b1);

        $finish;
    end
endmodule
