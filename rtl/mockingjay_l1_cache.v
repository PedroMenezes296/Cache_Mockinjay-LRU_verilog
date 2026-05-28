// Cache L1 de 2 vias com política de substituição Mockingjay (ETR).
//
// REQUISITO DO PROFESSOR: comparadores paralelos.
// As vias 0 e 1 são comparadas SIMULTANEAMENTE via wires combinacionais.
// Dois módulos etr_calculator rodam em paralelo no mesmo ciclo.
// Um MUX combinacional seleciona a vítima — nenhum for-loop.
//
// Protocolo de uso:
//   1. Apresente tag_in, set_index_in, global_time
//   2. Pulse access_en=1 por um ciclo
//   3. No próximo posedge: hit/l2_access_needed ficam válidos, done=1
//   4. No ciclo seguinte: done volta a 0
module mockingjay_l1_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [20:0] tag_in,
    input  wire [5:0]  set_index_in,
    input  wire [3:0]  global_time,
    output reg         hit,
    output reg         l2_access_needed,
    output reg         way_used,        // qual via foi tocada (debug)
    output reg         done
);
    // ----------------------------------------------------------------
    // Memória de estado: 2 vias x 64 conjuntos
    // ----------------------------------------------------------------
    reg        valid    [0:1][0:63];
    reg [20:0] tag_store[0:1][0:63];
    reg [3:0]  last_acc [0:1][0:63];
    reg [3:0]  interval [0:1][0:63];

    integer i, j;

    // ----------------------------------------------------------------
    // Estágio combinacional — tudo em paralelo, sem for-loop
    // ----------------------------------------------------------------
    wire hit_way0 = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
    wire hit_way1 = valid[1][set_index_in] && (tag_store[1][set_index_in] == tag_in);
    wire l1_hit   = hit_way0 | hit_way1;
    wire hit_way_sel = hit_way1; // 0 se hit na via0, 1 se hit na via1

    // ETR das duas vias calculados em paralelo
    wire [4:0] etr0; wire neg0;
    wire [4:0] etr1; wire neg1;

    etr_calculator u_etr0 (
        .last_access  (last_acc[0][set_index_in]),
        .interval     (interval[0][set_index_in]),
        .current_time (global_time),
        .etr          (etr0),
        .etr_negative (neg0)
    );
    etr_calculator u_etr1 (
        .last_access  (last_acc[1][set_index_in]),
        .interval     (interval[1][set_index_in]),
        .current_time (global_time),
        .etr          (etr1),
        .etr_negative (neg1)
    );

    // ETR efetivo: se negativo, trata como 5'b11111 (máximo)
    wire [4:0] eff0 = neg0 ? 5'b11111 : etr0;
    wire [4:0] eff1 = neg1 ? 5'b11111 : etr1;

    // Detecção de via vazia
    wire empty0 = !valid[0][set_index_in];
    wire empty1 = !valid[1][set_index_in];

    // Seleção de vítima: prioridade → via vazia, depois maior ETR
    wire victim_way = empty0          ? 1'b0 :
                      empty1          ? 1'b1 :
                      (eff0 >= eff1)  ? 1'b0 : 1'b1;

    // Intervalo aprendido no hit (saturado em 4 bits)
    wire [4:0] learned_full = {1'b0, global_time} - {1'b0, last_acc[hit_way_sel][set_index_in]};
    wire [3:0] learned = (learned_full > 5'd15) ? 4'hF : learned_full[3:0];

    // ----------------------------------------------------------------
    // Estágio sequencial — atualiza estado no posedge
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            done             <= 1'b0;
            hit              <= 1'b0;
            l2_access_needed <= 1'b0;
            for (i = 0; i < 2; i = i + 1)
                for (j = 0; j < 64; j = j + 1) begin
                    valid[i][j]     <= 1'b0;
                    tag_store[i][j] <= 21'd0;
                    last_acc[i][j]  <= 4'd0;
                    interval[i][j]  <= 4'hF; // MAX_INTERVALO em 4 bits
                end
        end else if (access_en) begin
            done <= 1'b1;
            if (l1_hit) begin
                // HIT: aprende intervalo e atualiza timestamp
                hit              <= 1'b1;
                l2_access_needed <= 1'b0;
                way_used         <= hit_way_sel;
                interval[hit_way_sel][set_index_in] <= learned;
                last_acc[hit_way_sel][set_index_in] <= global_time;
            end else begin
                // MISS: instala bloco na via vítima
                hit              <= 1'b0;
                l2_access_needed <= 1'b1;
                way_used         <= victim_way;
                valid[victim_way][set_index_in]     <= 1'b1;
                tag_store[victim_way][set_index_in] <= tag_in;
                last_acc[victim_way][set_index_in]  <= global_time;
                interval[victim_way][set_index_in]  <= 4'hF;
            end
        end else begin
            done             <= 1'b0;
            l2_access_needed <= 1'b0;
        end
    end
endmodule
