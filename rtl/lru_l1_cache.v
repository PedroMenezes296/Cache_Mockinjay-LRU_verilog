// Cache L1 de 2 vias com política LRU — usado para comparação com Mockingjay.
//
// Com 2 vias, o estado LRU é 1 bit por conjunto:
//   age=0 → via 0 é LRU (será expulsa)
//   age=1 → via 1 é LRU (será expulsa)
// Isso substitui o uint32_t idade do simulador C por 1 bit.
//
// Mesma interface do mockingjay_l1_cache para facilitar comparação no testbench.
module lru_l1_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [20:0] tag_in,
    input  wire [5:0]  set_index_in,
    output reg         hit,
    output reg         l2_access_needed,
    output reg         way_used,
    output reg         done
);
    reg        valid    [0:1][0:63];
    reg [20:0] tag_store[0:1][0:63];
    reg        lru_bit  [0:63]; // 0=via0 é LRU, 1=via1 é LRU

    integer i, j;

    // ----------------------------------------------------------------
    // Estágio combinacional — comparadores paralelos
    // ----------------------------------------------------------------
    wire hit_way0 = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
    wire hit_way1 = valid[1][set_index_in] && (tag_store[1][set_index_in] == tag_in);
    wire l1_hit   = hit_way0 | hit_way1;
    wire hit_way_sel = hit_way1;

    wire empty0 = !valid[0][set_index_in];
    wire empty1 = !valid[1][set_index_in];

    // Vítima LRU: via vazia primeiro, depois a que tem lru_bit apontando para ela
    wire victim_way = empty0 ? 1'b0 :
                      empty1 ? 1'b1 :
                      lru_bit[set_index_in]; // lru_bit=0 → expulsa via0; lru_bit=1 → expulsa via1

    // ----------------------------------------------------------------
    // Estágio sequencial
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
                end
            for (j = 0; j < 64; j = j + 1)
                lru_bit[j] <= 1'b0;
        end else if (access_en) begin
            done <= 1'b1;
            if (l1_hit) begin
                hit              <= 1'b1;
                l2_access_needed <= 1'b0;
                way_used         <= hit_way_sel;
                // Via acessada vira MRU: o bit aponta para a outra via como LRU
                lru_bit[set_index_in] <= ~hit_way_sel;
            end else begin
                hit              <= 1'b0;
                l2_access_needed <= 1'b1;
                way_used         <= victim_way;
                valid[victim_way][set_index_in]     <= 1'b1;
                tag_store[victim_way][set_index_in] <= tag_in;
                // Via instalada vira MRU
                lru_bit[set_index_in] <= ~victim_way;
            end
        end else begin
            done             <= 1'b0;
            l2_access_needed <= 1'b0;
        end
    end
endmodule
