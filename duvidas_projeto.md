# Dúvidas sobre o Projeto de Cache L1/L2

---

## A L2 tem apenas o MockingJay?

Sim. Existe apenas `rtl/mockingjay_l2_cache.v` — não há `lru_l2_cache.v`.

O sinal `policy_sel` em `rtl/cache_controller.v` seleciona a política **somente para L1**, via MUX de sinais:

```verilog
wire l1_hit       = policy_sel ? mj_l1_hit       : lru_l1_hit;
wire l1_l2_needed = policy_sel ? mj_l1_l2_needed : lru_l1_l2_needed;
wire l1_done      = policy_sel ? mj_l1_done      : lru_l1_done;
```

A L2 é sempre instanciada como `u_mj_l2` (Mockingjay), sem alternativa de política.

**Justificativa arquitetural:** a L2 só é acessada em L1 miss — já é o caminho mais caro. Usar LRU simples nela desperdiçaria a oportunidade de aplicar a política mais inteligente exatamente onde os erros têm maior custo (acesso à memória principal). O Mockingjay com árvore de comparadores de 3 níveis é o algoritmo fixo da L2 por decisão de projeto.

---

## Por que a L2 tem Tag e offset maior que a L1?

Correção importante: o **offset** da L2 é maior, mas a **tag é menor** — há uma troca causada pelo tamanho do bloco.

O `rtl/address_decoder.v` é parametrizado e instanciado com valores diferentes para cada nível:

| Campo  | L1 (bloco 32 B) | L2 (bloco 64 B) | Por quê                          |
|--------|-----------------|-----------------|----------------------------------|
| OFFSET | 5 bits (2⁵=32)  | **6 bits** (2⁶=64) | log₂(tamanho do bloco)        |
| INDEX  | 6 bits (64 sets)| 6 bits (64 sets)| ambas têm 64 conjuntos           |
| TAG    | **21 bits**     | 20 bits         | 32 − OFFSET − INDEX = bits restantes |
| Total  | 32 bits         | 32 bits         |                                  |

**Por que L2 usa bloco maior (64 B)?** Exploração de localidade espacial — ao buscar um bloco na memória principal (acesso muito caro), compensa trazer mais dados contíguos de uma só vez. Isso reduz o número de acessos à memória principal no futuro. Na L1, blocos menores (32 B) reduzem o custo de substituição e mantêm a cache menor (4 KB).

**Consequência direta:** como o offset consome 1 bit a mais na L2, sobram apenas 20 bits para a tag (e não 21). A L2 tem offset maior e tag menor — não ambos maiores.

---

## O relógio global de apenas 4 bits é defensável?

Para os testes atuais (traces curtos de até ~15 acessos), funciona corretamente. Para benchmarks de 2000 acessos, é uma limitação conhecida e documentada.

O `rtl/saturating_counter_4bit.v` satura em 15:

```verilog
else if (enable && count < 4'd15)
    count <= count + 1;
```

**O que acontece nos benchmarks:**

A partir do acesso nº 16, `global_time` permanece em 15. Todo novo bloco carregado aprende `last_acc = 15`. O cálculo do ETR passa a ser:

```
ETR = (last_acc + interval) − current_time
    = (15 + interval) − 15
    = interval
```

O relógio perde o significado temporal absoluto — o ETR se torna apenas o `interval` aprendido localmente, sem relação com o tempo real de execução. Isso pode divergir do simulador C de referência, que usa inteiros de 64 bits sem saturação.

**Defesa para a fase atual:**
- Traces curtos (≤15 acessos): resultados idênticos ao simulador C — validado nesta sprint.
- Para benchmarks longos, a largura de `interval` e `etr` precisaria ser reavaliada.
- Uma ampliação para 8 ou 12 bits resolveria o problema sem impacto de área significativo no Cyclone III EP3C25F324C6.

Esta limitação está documentada em `CLAUDE.md` (seção Limitações Conhecidas, item 2).

---

## Como funciona o tempo de clock? Seria possível diminuir?

O "tempo de clock" aqui se refere à **latência em ciclos de clock por acesso** — não à frequência do clock. A FSM em `rtl/cache_controller.v` tem 7 estados e os seguintes caminhos:

| Caminho     | Sequência de estados                                 | Ciclos |
|-------------|------------------------------------------------------|--------|
| L1 Hit      | IDLE → L1_CHECK (×2) → L1_HIT → OUTPUT              | ~5     |
| L2 Hit      | IDLE → L1_CHECK (×2) → L1_MISS_L2_CHECK (×2) → L2_HIT → OUTPUT  | ~7 |
| Full Miss   | IDLE → L1_CHECK (×2) → L1_MISS_L2_CHECK (×2) → L2_MISS → OUTPUT | ~7 |

O `L1_CHECK` aguarda 2 ciclos porque espera o sinal `l1_done` ser asserted — 1 ciclo para disparar o acesso, 1 ciclo para capturar o resultado.

**Seria possível reduzir?** Sim, com os seguintes trade-offs:

1. **Remover o estado OUTPUT:** retornar o resultado diretamente nos estados L1_HIT/L2_HIT/L2_MISS. Economiza 1 ciclo. Risco: a lógica de saída precisa estar pronta no mesmo ciclo da decisão.

2. **Combinar IDLE + L1_CHECK:** iniciar o acesso no mesmo ciclo em que `start` chega. Economiza 1 ciclo. Risco: caminho combinacional crítico se a comparação de tags for longa.

3. **L1_CHECK em 1 ciclo:** como a comparação de tags já é combinacional (`always @(*)`), o resultado pode ser capturado em 1 ciclo ao invés de 2, exigindo que `l1_done` seja gerado no mesmo ciclo que o acesso é disparado.

4. **Pipeline de acessos:** permitir que um novo acesso entre em L1_CHECK enquanto o resultado anterior ainda está em OUTPUT. Aumenta throughput sem reduzir a latência de um acesso individual, mas é a otimização mais complexa.

**Importante:** a frequência de clock real (Fmax) é determinada pelo caminho combinacional mais longo (comparação de tags + árvore de ETR de 3 níveis na L2). Reduzir o número de ciclos por acesso coloca mais lógica combinacional em série dentro de um ciclo, o que pode **reduzir o Fmax**. O design atual é conservador e adequado à fase de validação RTL no Cyclone III.
