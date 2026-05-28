// Extrai tag e set_index de um endereço de 32 bits.
// Parametrizado para funcionar tanto na L1 quanto na L2.
// Lógica puramente combinacional — nenhum flip-flop.
module address_decoder #(
    parameter OFFSET_BITS = 5,   // L1: 5 (bloco 32B), L2: 6 (bloco 64B)
    parameter INDEX_BITS  = 6,   // sempre 6 (64 conjuntos)
    parameter TAG_BITS    = 21   // L1: 21, L2: 20
)(
    input  wire [31:0]            addr,
    output wire [INDEX_BITS-1:0]  set_index,
    output wire [TAG_BITS-1:0]    tag
);
    assign set_index = addr[OFFSET_BITS + INDEX_BITS - 1 : OFFSET_BITS];
    assign tag       = addr[31 : OFFSET_BITS + INDEX_BITS];
endmodule
