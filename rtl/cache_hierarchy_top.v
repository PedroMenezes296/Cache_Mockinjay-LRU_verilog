// =============================================================================
// cache_hierarchy_top.v
// -----------------------------------------------------------------------------
// Top sintetizavel da hierarquia L1/L2 para uso no Quartus.
// Wrapper sobre cache_controller com interface estilo req_valid/done/busy.
//
// Nao possui initial, task, $display, $finish ou dumpvars.
// =============================================================================

`timescale 1ns/1ps

module cache_hierarchy_top (
    input  wire        clk,
    input  wire        rst,          // ativo-alto (inverte internamente para rst_n)

    // Requisicao externa
    input  wire        req_valid,
    input  wire [31:0] req_addr,
    input  wire [31:0] req_pc,       // recebido mas nao utilizado (Mockingjay nao usa PC)
    input  wire        policy_sel,   // 0 = LRU, 1 = Mockingjay

    // Sinalizacao de controle
    output reg         done,
    output reg         busy,

    // Resultado do acesso
    output reg         resp_l1_hit,
    output reg         resp_l1_miss,
    output reg         resp_l2_access,
    output reg         resp_l2_hit,
    output reg         resp_l2_miss,

    // Contadores acumulados
    output wire [31:0] l1_hit_count,
    output wire [31:0] l1_miss_count,
    output wire [31:0] l2_hit_count,
    output wire [31:0] l2_miss_count,

    // Debug de estado interno
    output wire [2:0]  state_debug
);

    // =========================================================================
    // Adaptacao de reset: cache_controller usa rst_n (ativo-baixo)
    // =========================================================================
    wire rst_n;
    assign rst_n = ~rst;

    // =========================================================================
    // Deteccao de borda de subida em req_valid para gerar pulso de start
    // cache_controller espera exatamente 1 ciclo de pulso em start
    // =========================================================================
    reg  req_valid_prev;
    wire start;

    always @(posedge clk) begin
        if (rst)
            req_valid_prev <= 1'b0;
        else
            req_valid_prev <= req_valid;
    end

    assign start = req_valid & ~req_valid_prev;

    // =========================================================================
    // Sinais do cache_controller
    // =========================================================================
    wire        result_valid;
    wire        l1_hit_out;
    wire        l2_hit_out;
    wire        full_miss_out;
    wire [2:0]  ctrl_state_debug;

    assign state_debug = ctrl_state_debug;

    // =========================================================================
    // Instancia do controlador da hierarquia
    // =========================================================================
    cache_controller u_ctrl (
        .clk          (clk),
        .rst_n        (rst_n),
        .start        (start),
        .address      (req_addr),
        .policy_sel   (policy_sel),
        .result_valid (result_valid),
        .l1_hit_out   (l1_hit_out),
        .l2_hit_out   (l2_hit_out),
        .full_miss_out(full_miss_out),
        .state_debug  (ctrl_state_debug)
    );

    // =========================================================================
    // Controle de busy/done e mapeamento das respostas
    // =========================================================================
    always @(posedge clk) begin
        if (rst) begin
            done           <= 1'b0;
            busy           <= 1'b0;
            resp_l1_hit    <= 1'b0;
            resp_l1_miss   <= 1'b0;
            resp_l2_access <= 1'b0;
            resp_l2_hit    <= 1'b0;
            resp_l2_miss   <= 1'b0;
        end
        else begin
            done <= 1'b0; // pulso de 1 ciclo

            if (start)
                busy <= 1'b1;

            if (result_valid) begin
                done  <= 1'b1;
                busy  <= 1'b0;

                resp_l1_hit    <= l1_hit_out;
                resp_l1_miss   <= ~l1_hit_out;
                resp_l2_access <= l2_hit_out | full_miss_out;
                resp_l2_hit    <= l2_hit_out;
                resp_l2_miss   <= full_miss_out;
            end
        end
    end

    // =========================================================================
    // Contadores de hit/miss (32 bits, acumulados)
    // =========================================================================
    reg [31:0] r_l1_hit_count;
    reg [31:0] r_l1_miss_count;
    reg [31:0] r_l2_hit_count;
    reg [31:0] r_l2_miss_count;

    assign l1_hit_count  = r_l1_hit_count;
    assign l1_miss_count = r_l1_miss_count;
    assign l2_hit_count  = r_l2_hit_count;
    assign l2_miss_count = r_l2_miss_count;

    always @(posedge clk) begin
        if (rst) begin
            r_l1_hit_count  <= 32'd0;
            r_l1_miss_count <= 32'd0;
            r_l2_hit_count  <= 32'd0;
            r_l2_miss_count <= 32'd0;
        end
        else if (result_valid) begin
            if (l1_hit_out)
                r_l1_hit_count  <= r_l1_hit_count  + 32'd1;
            else
                r_l1_miss_count <= r_l1_miss_count + 32'd1;

            if (l2_hit_out)
                r_l2_hit_count  <= r_l2_hit_count  + 32'd1;
            else if (full_miss_out)
                r_l2_miss_count <= r_l2_miss_count + 32'd1;
        end
    end

endmodule
// =============================================================================
// fim do cache_hierarchy_top.v
// =============================================================================
