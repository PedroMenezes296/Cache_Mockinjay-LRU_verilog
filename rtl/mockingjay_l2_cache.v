// Cache L2 de 8 vias com política Mockingjay (ETR).
// Só acessada quando a L1 sinaliza l2_access_needed.
//
// 8 instâncias de etr_calculator rodam em paralelo.
// A vítima é selecionada por uma árvore de comparadores de 3 níveis:
//   Nível 1: (0v1), (2v3), (4v5), (6v7) → 4 ganhadores
//   Nível 2: (w01 v w23), (w45 v w67)   → 2 ganhadores
//   Nível 3: resultado final              → vítima
module mockingjay_l2_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [19:0] tag_in,          // tag L2 = 20 bits
    input  wire [5:0]  set_index_in,
    input  wire [3:0]  global_time,
    output reg         hit,
    output reg  [2:0]  way_used,
    output reg         done
);
    reg        valid    [0:7][0:63];
    reg [19:0] tag_store[0:7][0:63];
    reg [3:0]  last_acc [0:7][0:63];
    reg [3:0]  interval [0:7][0:63];

    integer i, j;

    // ----------------------------------------------------------------
    // 8 comparadores de tag em paralelo
    // ----------------------------------------------------------------
    wire hit_way [0:7];
    assign hit_way[0] = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
    assign hit_way[1] = valid[1][set_index_in] && (tag_store[1][set_index_in] == tag_in);
    assign hit_way[2] = valid[2][set_index_in] && (tag_store[2][set_index_in] == tag_in);
    assign hit_way[3] = valid[3][set_index_in] && (tag_store[3][set_index_in] == tag_in);
    assign hit_way[4] = valid[4][set_index_in] && (tag_store[4][set_index_in] == tag_in);
    assign hit_way[5] = valid[5][set_index_in] && (tag_store[5][set_index_in] == tag_in);
    assign hit_way[6] = valid[6][set_index_in] && (tag_store[6][set_index_in] == tag_in);
    assign hit_way[7] = valid[7][set_index_in] && (tag_store[7][set_index_in] == tag_in);

    wire l2_hit = |{hit_way[7],hit_way[6],hit_way[5],hit_way[4],
                    hit_way[3],hit_way[2],hit_way[1],hit_way[0]};

    wire [2:0] hit_way_sel = hit_way[1] ? 3'd1 :
                             hit_way[2] ? 3'd2 :
                             hit_way[3] ? 3'd3 :
                             hit_way[4] ? 3'd4 :
                             hit_way[5] ? 3'd5 :
                             hit_way[6] ? 3'd6 :
                             hit_way[7] ? 3'd7 : 3'd0;

    // ----------------------------------------------------------------
    // 8 calculadores ETR em paralelo
    // ----------------------------------------------------------------
    wire [4:0] etr [0:7];
    wire       neg [0:7];

    etr_calculator u_etr0(.last_access(last_acc[0][set_index_in]),.interval(interval[0][set_index_in]),.current_time(global_time),.etr(etr[0]),.etr_negative(neg[0]));
    etr_calculator u_etr1(.last_access(last_acc[1][set_index_in]),.interval(interval[1][set_index_in]),.current_time(global_time),.etr(etr[1]),.etr_negative(neg[1]));
    etr_calculator u_etr2(.last_access(last_acc[2][set_index_in]),.interval(interval[2][set_index_in]),.current_time(global_time),.etr(etr[2]),.etr_negative(neg[2]));
    etr_calculator u_etr3(.last_access(last_acc[3][set_index_in]),.interval(interval[3][set_index_in]),.current_time(global_time),.etr(etr[3]),.etr_negative(neg[3]));
    etr_calculator u_etr4(.last_access(last_acc[4][set_index_in]),.interval(interval[4][set_index_in]),.current_time(global_time),.etr(etr[4]),.etr_negative(neg[4]));
    etr_calculator u_etr5(.last_access(last_acc[5][set_index_in]),.interval(interval[5][set_index_in]),.current_time(global_time),.etr(etr[5]),.etr_negative(neg[5]));
    etr_calculator u_etr6(.last_access(last_acc[6][set_index_in]),.interval(interval[6][set_index_in]),.current_time(global_time),.etr(etr[6]),.etr_negative(neg[6]));
    etr_calculator u_etr7(.last_access(last_acc[7][set_index_in]),.interval(interval[7][set_index_in]),.current_time(global_time),.etr(etr[7]),.etr_negative(neg[7]));

    // ETR efetivo (negativo → MAX)
    wire [4:0] eff [0:7];
    assign eff[0] = neg[0] ? 5'b11111 : etr[0];
    assign eff[1] = neg[1] ? 5'b11111 : etr[1];
    assign eff[2] = neg[2] ? 5'b11111 : etr[2];
    assign eff[3] = neg[3] ? 5'b11111 : etr[3];
    assign eff[4] = neg[4] ? 5'b11111 : etr[4];
    assign eff[5] = neg[5] ? 5'b11111 : etr[5];
    assign eff[6] = neg[6] ? 5'b11111 : etr[6];
    assign eff[7] = neg[7] ? 5'b11111 : etr[7];

    // Vias vazias
    wire empty [0:7];
    assign empty[0] = !valid[0][set_index_in];
    assign empty[1] = !valid[1][set_index_in];
    assign empty[2] = !valid[2][set_index_in];
    assign empty[3] = !valid[3][set_index_in];
    assign empty[4] = !valid[4][set_index_in];
    assign empty[5] = !valid[5][set_index_in];
    assign empty[6] = !valid[6][set_index_in];
    assign empty[7] = !valid[7][set_index_in];

    // Árvore de comparadores — nível 1 (4 comparações simultâneas)
    wire [2:0] w01 = (eff[0] >= eff[1]) ? 3'd0 : 3'd1;
    wire [2:0] w23 = (eff[2] >= eff[3]) ? 3'd2 : 3'd3;
    wire [2:0] w45 = (eff[4] >= eff[5]) ? 3'd4 : 3'd5;
    wire [2:0] w67 = (eff[6] >= eff[7]) ? 3'd6 : 3'd7;

    // Nível 2
    wire [2:0] w0123 = (eff[w01] >= eff[w23]) ? w01 : w23;
    wire [2:0] w4567 = (eff[w45] >= eff[w67]) ? w45 : w67;

    // Nível 3 — vítima com maior ETR
    wire [2:0] etr_victim = (eff[w0123] >= eff[w4567]) ? w0123 : w4567;

    // Seleção final: via vazia tem prioridade
    wire [2:0] victim_way = empty[0] ? 3'd0 :
                            empty[1] ? 3'd1 :
                            empty[2] ? 3'd2 :
                            empty[3] ? 3'd3 :
                            empty[4] ? 3'd4 :
                            empty[5] ? 3'd5 :
                            empty[6] ? 3'd6 :
                            empty[7] ? 3'd7 : etr_victim;

    // Intervalo aprendido no hit
    wire [4:0] learned_full = {1'b0, global_time} - {1'b0, last_acc[hit_way_sel][set_index_in]};
    wire [3:0] learned = (learned_full > 5'd15) ? 4'hF : learned_full[3:0];

    // ----------------------------------------------------------------
    // Estágio sequencial
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            done     <= 1'b0;
            hit      <= 1'b0;
            way_used <= 3'd0;
            for (i = 0; i < 8; i = i + 1)
                for (j = 0; j < 64; j = j + 1) begin
                    valid[i][j]     <= 1'b0;
                    tag_store[i][j] <= 20'd0;
                    last_acc[i][j]  <= 4'd0;
                    interval[i][j]  <= 4'hF;
                end
        end else if (access_en) begin
            done <= 1'b1;
            if (l2_hit) begin
                hit      <= 1'b1;
                way_used <= hit_way_sel;
                interval[hit_way_sel][set_index_in] <= learned;
                last_acc[hit_way_sel][set_index_in] <= global_time;
            end else begin
                hit      <= 1'b0;
                way_used <= victim_way;
                valid[victim_way][set_index_in]     <= 1'b1;
                tag_store[victim_way][set_index_in] <= tag_in;
                last_acc[victim_way][set_index_in]  <= global_time;
                interval[victim_way][set_index_in]  <= 4'hF;
            end
        end else begin
            done <= 1'b0;
        end
    end
endmodule
