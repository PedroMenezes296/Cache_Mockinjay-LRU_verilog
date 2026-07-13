# Relatório de Síntese — Quartus II (Flow Summary)

**Data da compilação:** Thu Jun 18 02:19:52 2026
**Ferramenta:** Quartus II 64-Bit — versão 13.1.0 Build 162 (10/23/2013 SJ Web Edition)
**Módulo top-level:** `cache_hierarchy_top`
**Família / Dispositivo:** Cyclone III — **EP3C25F324C6**
**Status:** Flow Failed

---

## O que é o Flow Summary?

O **Flow Summary** é o relatório de síntese gerado pelo Quartus ao tentar mapear o design RTL para os recursos físicos do FPGA. Ele indica:

1. Quantos recursos o design *precisa* (lado esquerdo de cada barra `X / Y`).
2. Quantos recursos o dispositivo *tem disponível* (lado direito).
3. A porcentagem de ocupação.

Se qualquer recurso ultrapassar 100%, a ferramenta **aborta** com `Flow Failed` — não é possível colocar mais lógica do que o chip comporta.

---

## Tabela de Métricas

| Métrica | Usado | Disponível | Ocupação | Observação |
|---|---|---|---|---|
| **Total logic elements (LEs)** | 27.180 | 24.624 | **110%** | **Causa do Flow Failed** |
| Total combinational functions | 17.250 | 24.624 | 70% | Lógica puramente combinacional (MUX, comparadores, decoders) |
| Dedicated logic registers | 21.731 | 24.624 | 88% | Flip-flops: memória de estado (tags, valid, interval, last_access) |
| Total registers | 21.731 | — | — | Soma de todos os registradores (igual ao item acima neste design) |
| Total pins | 206 | 216 | 95% | Portas de I/O usadas (sinais externos do módulo top) |
| Total virtual pins | 0 | — | — | Nenhum pino virtual usado (esperado) |
| **Total memory bits** | **0** | 608.256 | **0%** | **BRAMs completamente ociosas — ponto crítico** |
| Embedded Multiplier 9-bit | 0 | 132 | 0% | Nenhum multiplicador de hardware necessário (esperado em cache) |
| Total PLLs | 0 | 4 | 0% | Nenhum PLL instanciado (esperado na fase RTL) |

---

## Por que o Flow Falhou

O único motivo do `Flow Failed` é o **estouro de Logic Elements**:

```
27.180 LEs necessários > 24.624 LEs disponíveis  →  110%  →  Overflow
```

O Quartus não consegue fazer o roteamento/fitting porque simplesmente não existe espaço físico no chip para acomodar o design na forma em que está sintetizado.

---

## Causa Raiz: Arrays de Cache Implementados como Flip-Flops

O dado mais revelador da tabela é o contraste:

| Recurso | Usado | Esperado para um cache |
|---|---|---|
| Dedicated logic registers | 21.731 (88%) | Alto — arrays de memória |
| **Total memory bits (BRAM)** | **0 (0%)** | Deveria ser **alto** |

O EP3C25F324C6 possui **608.256 bits de memória embarcada (BRAMs)**, mas o design os ignorou completamente.

### O que aconteceu

Os arrays multidimensionais dos módulos de cache (declarados como `reg [X:0] nome [0:W][0:S]`) foram **sintetizados como flip-flops distribuídos**, e não como blocos de RAM embarcados. Isso acontece porque:

1. O Quartus infere BRAM automaticamente apenas quando o padrão de acesso segue o modelo de memória síncrona com um único porto de leitura/escrita.
2. Arrays indexados por múltiplas dimensões simultâneas (como `tag[via][conjunto]`) com leitura paralela nas duas vias no mesmo ciclo fogem do padrão de BRAM simples.
3. Sem diretivas explícitas (`(* ramstyle = "M9K" *)`), o sintetizador opta pelo caminho mais conservador: flip-flops.

### Quantos bits os arrays ocupam

Estimativa dos principais arrays por módulo:

| Array | Dimensão | Bits por módulo |
|---|---|---|
| `tag[2][64]` em L1 (×2 módulos) | 2 × 64 × 21 bits | 2.688 bits |
| `valid[2][64]` em L1 | 2 × 64 × 1 | 128 bits |
| `interval[2][64]` em L1 | 2 × 64 × 4 | 512 bits |
| `last_access[2][64]` em L1 | 2 × 64 × 4 | 512 bits |
| `tag[8][64]` em L2 | 8 × 64 × 20 bits | 10.240 bits |
| `valid[8][64]` em L2 | 8 × 64 × 1 | 512 bits |
| `interval[8][64]` em L2 | 8 × 64 × 4 | 2.048 bits |
| `last_access[8][64]` em L2 | 8 × 64 × 4 | 2.048 bits |

**Total estimado:** ~18.688 bits de dados de cache — que caberiam facilmente nos **608.256 bits de BRAM** disponíveis. Em vez disso, cada bit está consumindo um flip-flop dentro de um LE.

---

## Outros Pontos de Atenção

### Pins: 95% (206 / 216)

O design expõe 206 sinais externos no módulo `cache_hierarchy_top`. Isso está muito próximo do limite do dispositivo. Para a integração com o core RV32I, novos sinais serão necessários (`write_en`, `wdata`, `rdata`, `dirty`, `stall`/`ready`) — o que provavelmente excederia o limite de pinos também.

**Ação recomendada:** verificar quais sinais de debug (`state_debug`, `way_used`) podem ser removidos ou agrupados em bus antes da integração.

### Registradores: 88% (21.731 / 24.624)

Os 21.731 flip-flops quase atingem a capacidade total do dispositivo isoladamente. Mesmo que a lógica combinacional coubesse, a quantidade de registradores sozinha deixaria o chip quase saturado.

---

## Caminhos de Solução

### Opção 1 — Inferência de BRAM com atributo Quartus (recomendado)

Adicionar a diretiva de síntese antes dos arrays nos arquivos RTL:

```verilog
(* ramstyle = "M9K" *) reg [20:0] tag    [0:7][0:63];
(* ramstyle = "M9K" *) reg [3:0]  interval [0:7][0:63];
```

Isso instrui o Quartus a mapear o array para blocos M9K (BRAMs de 9K bits cada) em vez de flip-flops. A leitura precisaria ser síncrona (resultado disponível no ciclo seguinte), o que pode exigir ajuste de 1 ciclo na FSM.

### Opção 2 — Reduzir largura dos campos

Diminuir o número de conjuntos ou vias para caber nos 24.624 LEs disponíveis (solução paliativa, altera a arquitetura definida):

| Mudança | Impacto estimado de LEs |
|---|---|
| L2 de 8 vias → 4 vias | −~5.000 LEs |
| L1 de 64 sets → 32 sets | −~1.500 LEs |

### Opção 3 — Dispositivo com mais recursos

Usar um FPGA maior da mesma família (ex.: EP3C40, EP3C55, EP3C80). O EP3C55 possui ~55.856 LEs e 2.396.160 bits de memória, comportando o design sem alterações.

---

## Conclusão

O design está **logicamente correto** (validado em simulação — ver `sim/validation_report.md`). O `Flow Failed` é exclusivamente um problema de **mapeamento de recursos físicos**: os arrays de cache foram sintetizados como flip-flops, consumindo 88% dos registradores do chip, o que resulta em 110% de uso de Logic Elements.

A solução principal é habilitar a inferência de BRAM (Opção 1), que liberaria ~18.000 bits dos flip-flops para os blocos M9K ociosos — reduzindo o uso de LEs para a faixa de 40–60% e deixando o design sintetizável no EP3C25F324C6.
