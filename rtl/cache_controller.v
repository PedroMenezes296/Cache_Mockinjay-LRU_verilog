// FSM top-level: orquestra L1 → L2 para um acesso de memória.
//
// policy_sel=0: LRU | policy_sel=1: Mockingjay
//
// Fluxo de estados:
//   IDLE → L1_CHECK → L1_HIT  → OUTPUT → IDLE
//                  ↘ L1_MISS_L2_CHECK → L2_HIT  → OUTPUT → IDLE
//                                     ↘ L2_MISS → OUTPUT → IDLE
module cache_controller (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,          // pulse para iniciar um acesso
    input  wire [31:0] address,
    input  wire        policy_sel,     // 0=LRU, 1=Mockingjay
    output reg         result_valid,
    output reg         l1_hit_out,
    output reg         l2_hit_out,
    output reg         full_miss_out,
    output reg  [2:0]  state_debug
);
    // ----------------------------------------------------------------
    // Estados FSM
    // ----------------------------------------------------------------
    localparam IDLE             = 3'd0;
    localparam L1_CHECK         = 3'd1;
    localparam L1_HIT           = 3'd2;
    localparam L1_MISS_L2_CHECK = 3'd3;
    localparam L2_HIT           = 3'd4;
    localparam L2_MISS          = 3'd5;
    localparam OUTPUT           = 3'd6;

    reg [2:0] state, next_state;

    // ----------------------------------------------------------------
    // Decodificadores de endereço (combinacionais)
    // ----------------------------------------------------------------
    wire [5:0]  set_l1;
    wire [20:0] tag_l1;
    wire [5:0]  set_l2;
    wire [19:0] tag_l2;

    address_decoder #(.OFFSET_BITS(5), .INDEX_BITS(6), .TAG_BITS(21)) u_dec_l1 (
        .addr(address), .set_index(set_l1), .tag(tag_l1)
    );
    address_decoder #(.OFFSET_BITS(6), .INDEX_BITS(6), .TAG_BITS(20)) u_dec_l2 (
        .addr(address), .set_index(set_l2), .tag(tag_l2)
    );

    // ----------------------------------------------------------------
    // Clock global (4 bits saturados) — incrementa por acesso
    // ----------------------------------------------------------------
    wire [3:0] global_time;
    reg        clk_enable;

    saturating_counter_4bit u_global_clk (
        .clk(clk), .rst_n(rst_n),
        .enable(clk_enable),
        .load_val(4'd0), .load_en(1'b0),
        .count(global_time)
    );

    // ----------------------------------------------------------------
    // Sinais de controle dos caches
    // ----------------------------------------------------------------
    reg  mj_l1_en, lru_l1_en, mj_l2_en;

    wire mj_l1_hit,  mj_l1_l2_needed, mj_l1_done;
    wire lru_l1_hit, lru_l1_l2_needed, lru_l1_done;
    wire mj_l2_hit,  mj_l2_done;

    mockingjay_l1_cache u_mj_l1 (
        .clk(clk), .rst_n(rst_n),
        .access_en(mj_l1_en),
        .tag_in(tag_l1), .set_index_in(set_l1),
        .global_time(global_time),
        .hit(mj_l1_hit), .l2_access_needed(mj_l1_l2_needed),
        .way_used(), .done(mj_l1_done)
    );

    lru_l1_cache u_lru_l1 (
        .clk(clk), .rst_n(rst_n),
        .access_en(lru_l1_en),
        .tag_in(tag_l1), .set_index_in(set_l1),
        .hit(lru_l1_hit), .l2_access_needed(lru_l1_l2_needed),
        .way_used(), .done(lru_l1_done)
    );

    mockingjay_l2_cache u_mj_l2 (
        .clk(clk), .rst_n(rst_n),
        .access_en(mj_l2_en),
        .tag_in(tag_l2), .set_index_in(set_l2),
        .global_time(global_time),
        .hit(mj_l2_hit), .way_used(), .done(mj_l2_done)
    );

    // Aliases conforme política selecionada
    wire l1_hit       = policy_sel ? mj_l1_hit        : lru_l1_hit;
    wire l1_l2_needed = policy_sel ? mj_l1_l2_needed  : lru_l1_l2_needed;
    wire l1_done      = policy_sel ? mj_l1_done        : lru_l1_done;

    // ----------------------------------------------------------------
    // FSM — lógica de próximo estado (combinacional)
    // ----------------------------------------------------------------
    always @(*) begin
        next_state = state;
        case (state)
            IDLE:             if (start)    next_state = L1_CHECK;
            L1_CHECK:         if (l1_done)  next_state = l1_hit ? L1_HIT : L1_MISS_L2_CHECK;
            L1_HIT:                         next_state = OUTPUT;
            L1_MISS_L2_CHECK: if (mj_l2_done) next_state = mj_l2_hit ? L2_HIT : L2_MISS;
            L2_HIT:                         next_state = OUTPUT;
            L2_MISS:                        next_state = OUTPUT;
            OUTPUT:                         next_state = IDLE;
            default:                        next_state = IDLE;
        endcase
    end

    // ----------------------------------------------------------------
    // FSM — registros de estado e saídas (sequencial)
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            state        <= IDLE;
            result_valid <= 1'b0;
            l1_hit_out   <= 1'b0;
            l2_hit_out   <= 1'b0;
            full_miss_out<= 1'b0;
            clk_enable   <= 1'b0;
            mj_l1_en     <= 1'b0;
            lru_l1_en    <= 1'b0;
            mj_l2_en     <= 1'b0;
        end else begin
            state      <= next_state;
            state_debug<= next_state;

            // Defaults
            result_valid <= 1'b0;
            clk_enable   <= 1'b0;
            mj_l1_en     <= 1'b0;
            lru_l1_en    <= 1'b0;
            mj_l2_en     <= 1'b0;

            case (next_state)
                L1_CHECK: begin
                    clk_enable   <= 1'b1; // incrementa clock por acesso
                    mj_l1_en     <= policy_sel;
                    lru_l1_en    <= ~policy_sel;
                end
                L1_MISS_L2_CHECK: begin
                    mj_l2_en     <= 1'b1;
                end
                OUTPUT: begin
                    result_valid  <= 1'b1;
                    l1_hit_out    <= (state == L1_HIT);
                    l2_hit_out    <= (state == L2_HIT);
                    full_miss_out <= (state == L2_MISS);
                end
            endcase
        end
    end
endmodule
