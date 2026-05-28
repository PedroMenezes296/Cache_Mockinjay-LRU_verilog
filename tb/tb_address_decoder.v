// Testbench: address_decoder
// Verifica extração de tag e set_index para L1 e L2,
// replicando os cálculos do simulador C.
`timescale 1ns/1ps
module tb_address_decoder;
    reg [31:0] addr;

    wire [5:0]  set_l1;
    wire [20:0] tag_l1;
    wire [5:0]  set_l2;
    wire [19:0] tag_l2;

    address_decoder #(.OFFSET_BITS(5), .INDEX_BITS(6), .TAG_BITS(21)) u_l1(
        .addr(addr), .set_index(set_l1), .tag(tag_l1)
    );
    address_decoder #(.OFFSET_BITS(6), .INDEX_BITS(6), .TAG_BITS(20)) u_l2(
        .addr(addr), .set_index(set_l2), .tag(tag_l2)
    );

    task check_l1;
        input [31:0] a;
        input [5:0]  exp_set;
        input [20:0] exp_tag;
        begin
            addr = a; #1;
            if (set_l1 !== exp_set || tag_l1 !== exp_tag)
                $display("L1 FALHOU addr=0x%h: set=%0d(esp %0d) tag=%0d(esp %0d)",
                          a, set_l1, exp_set, tag_l1, exp_tag);
            else
                $display("L1 PASSOU addr=0x%h → set=%0d tag=%0d", a, set_l1, tag_l1);
        end
    endtask

    task check_l2;
        input [31:0] a;
        input [5:0]  exp_set;
        input [19:0] exp_tag;
        begin
            addr = a; #1;
            if (set_l2 !== exp_set || tag_l2 !== exp_tag)
                $display("L2 FALHOU addr=0x%h: set=%0d(esp %0d) tag=%0d(esp %0d)",
                          a, set_l2, exp_set, tag_l2, exp_tag);
            else
                $display("L2 PASSOU addr=0x%h → set=%0d tag=%0d", a, set_l2, tag_l2);
        end
    endtask

    initial begin
        // 0x0000: set_l1 = (0/32)%64=0, tag_l1 = 0/(32*64)=0
        check_l1(32'h00000000, 6'd0, 21'd0);
        // 0x0800: 0x0800=2048 → (2048/32)%64=64%64=0, tag=2048/2048=1
        check_l1(32'h00000800, 6'd0, 21'd1);
        // 0x1000: 0x1000=4096 → (4096/32)%64=128%64=0, tag=4096/2048=2
        check_l1(32'h00001000, 6'd0, 21'd2);

        // L2 — 0x0800=2048: set=(2048/64)%64=32%64=32, tag=2048/(64*64)=0
        check_l2(32'h00000000, 6'd0,  20'd0);
        check_l2(32'h00000800, 6'd32, 20'd0);
        check_l2(32'h00001000, 6'd0,  20'd1);

        $finish;
    end
endmodule
