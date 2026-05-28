// Contador de 4 bits que satura em 15 (não faz overflow).
// Pode ser carregado com um valor arbitrário via load_en/load_val.
// Substitui o int relogio_global do simulador C.
module saturating_counter_4bit (
    input  wire       clk,
    input  wire       rst_n,      // reset síncrono ativo-baixo
    input  wire       enable,     // incrementa quando alto
    input  wire [3:0] load_val,   // valor a carregar
    input  wire       load_en,    // força carga (prioridade sobre incremento)
    output reg  [3:0] count
);
    always @(posedge clk) begin
        if (!rst_n)
            count <= 4'd0;
        else if (load_en)
            count <= load_val;
        else if (enable && count < 4'd15)
            count <= count + 4'd1;
        // Se count == 15 e enable=1: permanece em 15 (saturação)
    end
endmodule
