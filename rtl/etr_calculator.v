// Calcula o ETR (Estimated Time of Reuse) de uma via da cache.
// ETR = (ultimo_acesso + intervalo_previsto) - relogio_atual
// Lógica puramente combinacional — nenhum flip-flop.
//
// etr_negative=1 significa ETR < 0 (estritamente negativo): o bloco está "atrasado".
// O chamador deve tratar isso como MAX (5'b11111) para escolha de vítima.
// IMPORTANTE: ETR == 0 NÃO é negativo — fica protegido (eff=0). Isso espelha
// exatamente o `if (tempo_estimado_reuso < 0)` do simulador C de referência.
module etr_calculator (
    input  wire [3:0] last_access,   // ultimo_acesso (4 bits saturados)
    input  wire [3:0] interval,      // intervalo_previsto (4 bits saturados)
    input  wire [3:0] current_time,  // relogio_global atual
    output wire [4:0] etr,           // resultado de 5 bits (pode ser > 15)
    output wire       etr_negative   // 1 se ETR <= 0
);
    wire [4:0] sum = {1'b0, last_access} + {1'b0, interval};

    assign etr          = sum - {1'b0, current_time};
    assign etr_negative = (sum < {1'b0, current_time});
endmodule
