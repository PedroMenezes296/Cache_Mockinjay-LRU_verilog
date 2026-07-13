// Testbench de casos de borda (item 2.10 do checklist de validação).
// Cobre cenários NÃO exercitados pelos traces curtos:
//   L1 (mockingjay_l1_cache):
//     - flag valid checada antes da tag (tag=0 + valid=0 => MISS, não HIT espúrio)
//     - mesmo endereço consecutivo => 2º acesso é HIT
//     - reset no meio da operação => estado limpo
//     - access_en=0 => done permanece 0
//     - saturação do relógio global em 15 => ETR continua sem overflow
//   Controller (cache_controller):
//     - result_valid fica alto por exatamente 1 ciclo
//     - FSM retorna a IDLE após cada acesso
//     - global_time incrementa exatamente 1 vez por acesso
//     - policy_sel=0 ativa só a via LRU (mj_l1_en permanece 0)
//
// Rodar: iverilog -o tb_edge rtl/*.v tb/tb_edge_cases.v && vvp tb_edge
`timescale 1ns/1ps
module tb_edge_cases;
    integer erros = 0;
    task chk; input cond; input [255:0] msg; begin
        if (cond) $display("PASSOU: %0s", msg);
        else begin erros=erros+1; $display("FALHOU: %0s", msg); end
    end endtask

    // ================= DUT 1: mockingjay_l1_cache =================
    reg  clk, rst_n, access_en;
    reg  [20:0] tag_in;
    reg  [5:0]  set_index_in;
    reg  [3:0]  global_time;
    wire        hit, l2_access_needed, way_used, done;

    mockingjay_l1_cache u_l1(
        .clk(clk), .rst_n(rst_n), .access_en(access_en),
        .tag_in(tag_in), .set_index_in(set_index_in), .global_time(global_time),
        .hit(hit), .l2_access_needed(l2_access_needed), .way_used(way_used), .done(done)
    );

    task l1_access; input [5:0] s; input [20:0] t; input [3:0] gt; begin
        global_time=gt; set_index_in=s; tag_in=t; access_en=1;
        @(posedge clk); #1 access_en=0;
        wait(done); @(posedge clk); #1;
    end endtask

    always #5 clk = ~clk;

    // ================= DUT 2: cache_controller =================
    reg         c_start, c_policy;
    reg  [31:0] c_addr;
    wire        c_rvalid, c_l1h, c_l2h, c_fmiss;
    wire [2:0]  c_state;

    cache_controller u_ctrl(
        .clk(clk), .rst_n(rst_n), .start(c_start), .address(c_addr),
        .policy_sel(c_policy), .result_valid(c_rvalid),
        .l1_hit_out(c_l1h), .l2_hit_out(c_l2h), .full_miss_out(c_fmiss),
        .state_debug(c_state)
    );

    integer rv_cycles, mj_en_seen, t0, dt;
    // Conta ciclos de result_valid alto e observa enables internos durante 1 acesso.
    task ctrl_access; input [31:0] a; input pol; begin
        c_addr=a; c_policy=pol;
        rv_cycles=0; mj_en_seen=0;
        @(posedge clk); #1 c_start=1;
        @(posedge clk); #1 c_start=0;
        // amostra até result_valid e mais 1 ciclo
        while (u_ctrl.state !== 3'd0 || c_rvalid===1'b1) begin
            if (c_rvalid===1'b1) rv_cycles=rv_cycles+1;
            if (u_ctrl.mj_l1_en===1'b1) mj_en_seen=1;
            @(posedge clk); #1;
        end
    end endtask

    initial begin
        // ---------- Reset inicial ----------
        clk=0; rst_n=0; access_en=0; global_time=0; c_start=0; c_policy=0; c_addr=0;
        @(posedge clk); #1 rst_n=1; @(posedge clk); #1;

        $display("===== L1: flag valid antes da tag =====");
        l1_access(6'd0, 21'd0, 4'd1);                 // tag 0 numa via vazia
        chk(hit===1'b0, "tag=0 com valid=0 => MISS (sem hit espurio)");

        $display("===== L1: mesmo endereco consecutivo =====");
        l1_access(6'd3, 21'd9, 4'd2);                 // instala
        chk(hit===1'b0, "1o acesso ao bloco novo => MISS");
        l1_access(6'd3, 21'd9, 4'd3);                 // repete
        chk(hit===1'b1, "2o acesso ao mesmo bloco => HIT");

        $display("===== L1: reset no meio da operacao =====");
        global_time=4; set_index_in=6'd3; tag_in=21'd9; access_en=1;
        @(posedge clk); #1;                            // operacao em andamento
        rst_n=0; access_en=0;                          // reset cai no meio
        @(posedge clk); #1 rst_n=1;
        @(posedge clk); #1;
        chk(done===1'b0, "apos reset, done volta a 0");
        l1_access(6'd3, 21'd9, 4'd5);                  // bloco antes presente
        chk(hit===1'b0, "apos reset o estado foi limpo => MISS");

        $display("===== L1: access_en=0 mantem done=0 =====");
        access_en=0;
        @(posedge clk); #1; @(posedge clk); #1;
        chk(done===1'b0, "sem access_en, done permanece 0");

        $display("===== L1: saturacao do relogio global em 15 =====");
        l1_access(6'd7, 21'd20, 4'd15);                // instala no tempo 15 (max)
        chk(hit===1'b0, "instala bloco com global_time=15 => MISS");
        l1_access(6'd7, 21'd20, 4'd15);                // re-acessa ainda em 15
        chk(hit===1'b1, "re-acesso com relogio saturado (15) => HIT sem overflow");

        // ---------- Controller ----------
        rst_n=0; @(posedge clk); #1 rst_n=1; @(posedge clk); #1;

        $display("===== Controller: result_valid 1 ciclo + retorno a IDLE + global_time =====");
        t0 = u_ctrl.global_time;
        ctrl_access(32'h0000_0000, 1'b1);              // 1 acesso Mockingjay
        dt = u_ctrl.global_time - t0;
        chk(rv_cycles===1, "result_valid alto por exatamente 1 ciclo");
        chk(u_ctrl.state===3'd0, "FSM retornou a IDLE apos o acesso");
        chk(dt===1, "global_time incrementou exatamente 1 vez no acesso");

        $display("===== Controller: policy_sel=0 nao ativa via Mockingjay =====");
        ctrl_access(32'h0000_0040, 1'b0);              // acesso LRU
        chk(mj_en_seen===0, "com policy_sel=0, mj_l1_en permanece 0");

        $display("=== TB_EDGE_CASES: %0d erro(s) ===", erros);
        if (erros==0) $display("RESULTADO: CORRETO"); else $display("RESULTADO: INCORRETO");
        $finish;
    end
endmodule
