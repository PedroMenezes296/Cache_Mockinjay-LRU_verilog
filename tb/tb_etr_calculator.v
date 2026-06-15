// Testbench: etr_calculator
// Verifica casos do simulador C:
//   - ETR positivo normal
//   - ETR zero → NÃO é negativo (etr_negative=0), bloco protegido (espelha if(etr<0) do C)
//   - ETR estritamente negativo → etr_negative=1
//   - Soma saturando em 5 bits
`timescale 1ns/1ps
module tb_etr_calculator;
    reg [3:0] last_access, interval, current_time;
    wire [4:0] etr;
    wire       etr_negative;

    etr_calculator dut(
        .last_access(last_access),
        .interval(interval),
        .current_time(current_time),
        .etr(etr),
        .etr_negative(etr_negative)
    );

    task check;
        input [3:0] la, iv, ct;
        input [4:0] exp_etr;
        input       exp_neg;
        begin
            last_access=la; interval=iv; current_time=ct; #1;
            if (etr!==exp_etr || etr_negative!==exp_neg)
                $display("FALHOU la=%0d iv=%0d ct=%0d: etr=%0d(esp %0d) neg=%b(esp %b)",
                          la,iv,ct,etr,exp_etr,etr_negative,exp_neg);
            else
                $display("PASSOU la=%0d iv=%0d ct=%0d → etr=%0d neg=%b", la,iv,ct,etr,etr_negative);
        end
    endtask

    initial begin
        // ETR estritamente negativo: last=2, interval=2, time=5 → sum=4, ETR=4-5=-1
        // Em 5 bits o etr "estoura" para 31 (don't-care quando neg=1); o que importa é neg=1.
        check(4'd2, 4'd2, 4'd5, 5'd31, 1'b1);

        // ETR positivo: last=3, interval=5, time=6 → ETR=2
        check(4'd3, 4'd5, 4'd6, 5'd2, 1'b0);

        // ETR=0 (caso da via A no acesso 5 do trace_validacao): last=3, interval=2, time=5
        // sum=5, ETR=0 → NÃO é negativo (neg=0) → eff=0 → bloco PROTEGIDO (espelha if(etr<0) do C).
        check(4'd3, 4'd2, 4'd5, 5'd0, 1'b0);

        // Intervalo máximo: last=15, interval=15, time=1 → sum=30, ETR=29 → positivo
        check(4'd15, 4'd15, 4'd1, 5'd29, 1'b0);

        $finish;
    end
endmodule
