# ProjetoCache — Hierarquia de Cache em Verilog RTL

Sprint 3 do Projeto Integrador (Engenharia de Computação). Implementação em Verilog RTL de uma hierarquia de cache L1/L2 com dois algoritmos de substituição: **LRU** (baseline) e **Mockingjay** (heurística ETR desenvolvida pelo grupo). O objetivo é sintetizável em FPGA e reproduz exatamente os resultados do simulador C das Sprints 1 e 2.

---

## O que o projeto faz

O hardware simula o que acontece quando um processador busca dados na memória:

```
CPU → acessa endereço de 32 bits
        │
        ▼
    [Cache L1]  ─── HIT  → dados entregues em ~2 ciclos
        │
       MISS
        │
        ▼
    [Cache L2]  ─── HIT  → dados entregues em ~5 ciclos
        │
       MISS
        │
        ▼
    Memória principal (fora do escopo deste projeto)
```

Dois algoritmos de substituição decidem **qual bloco expulsar** quando a cache está cheia e precisa acomodar um novo dado:

| Algoritmo | Ideia | Vantagem |
|---|---|---|
| **LRU** | Expulsa o bloco acessado há mais tempo | Simples, predizível |
| **Mockingjay** | Expulsa o bloco que vai demorar mais para ser usado (ETR) | Mais acertos em padrões recorrentes |

---

## Arquitetura da Cache

### Cache L1 (Dados)
- **Capacidade:** 4 KB, 2 vias (2-way set associative)
- **Bloco:** 32 bytes → offset = `addr[4:0]` (5 bits)
- **64 conjuntos** → index = `addr[10:5]` (6 bits)
- **Tag:** `addr[31:11]` (21 bits)

### Cache L2 (Unificada)
- **Capacidade:** 32 KB, 8 vias
- **Bloco:** 64 bytes → offset = `addr[5:0]` (6 bits)
- **64 conjuntos** → index = `addr[11:6]` (6 bits)
- **Tag:** `addr[31:12]` (20 bits)
- Só é acessada em caso de L1 miss

---

## Estrutura de Arquivos

```
rtl/                          ← Verilog sintetizável
  address_decoder.v           ← extrai tag e set_index do endereço (combinacional)
  saturating_counter_4bit.v   ← contador 0–15 que trava no máximo
  etr_calculator.v            ← calcula ETR de uma via (combinacional)
  mockingjay_l1_cache.v       ← L1 2-way com política Mockingjay
  lru_l1_cache.v              ← L1 2-way com política LRU (comparação)
  mockingjay_l2_cache.v       ← L2 8-way com política Mockingjay
  cache_controller.v          ← FSM top-level: conecta L1, L2 e decodificadores

tb/                           ← Testbenches (não sintetizáveis)
  tb_cache_top.v              ← simulação completa com traces
  tb_address_decoder.v
  tb_saturating_counter.v
  tb_etr_calculator.v
  tb_mockingjay_l1.v
  tb_lru_l1.v

sim/
  traces_hex/                 ← sequências de endereços em hexadecimal puro
    trace_validacao.mem       ← 8 acessos para validação
    trace_mixed_hotset.mem    ← 8 acessos com L2 ativo
  expected_outputs/           ← gabarito do simulador C
    validacao_mj.txt
    validacao_lru.txt
```

---

## Módulos — Passo a Passo

### 1. `address_decoder.v` — Decodificador de Endereço

Recebe um endereço de 32 bits e extrai, em um único ciclo combinacional, os campos:

```
Endereço de 32 bits:
 [31 ────── 11][10 ──── 5][4 ──── 0]
      tag         index      offset
```

É parametrizado: a mesma implementação serve para L1 (offset=5, tag=21) e L2 (offset=6, tag=20).

---

### 2. `saturating_counter_4bit.v` — Contador Saturado de 4 bits

Contador de 0 a 15 que **não faz overflow**: ao chegar em 15, permanece em 15. Substitui o `int relogio_global` do simulador C. Usado como relógio global de acesso — incrementa uma vez por acesso à cache.

```
0 → 1 → 2 → ... → 14 → 15 → 15 → 15 (trava aqui)
```

---

### 3. `etr_calculator.v` — Calculador de ETR

Implementa a fórmula do algoritmo Mockingjay:

```
ETR = (ultimo_acesso + intervalo_previsto) - relogio_atual
```

- **ETR alto** → bloco vai demorar para ser usado → bom candidato a vítima
- **ETR ≤ 0** → bloco está "atrasado" → tratado como ETR máximo (31)
- Lógica puramente combinacional; o resultado fica disponível no mesmo ciclo

---

### 4. `lru_l1_cache.v` — Cache L1 com LRU

Cache L1 de 2 vias com substituição pelo menos recentemente usado. Com 2 vias, o estado LRU inteiro cabe em **1 bit por conjunto**:

- `lru_bit=0` → via 0 é a LRU (será expulsa no próximo miss)
- `lru_bit=1` → via 1 é a LRU

As duas vias são comparadas **em paralelo** (wires combinacionais), sem for-loops, conforme requisito do professor.

**Protocolo:** `access_en=1` dispara o acesso; `done=1` no ciclo seguinte indica que `hit` e `l2_access_needed` são válidos.

---

### 5. `mockingjay_l1_cache.v` — Cache L1 com Mockingjay

Cache L1 de 2 vias que usa ETR para escolher a vítima. Dois módulos `etr_calculator` rodam **simultaneamente** (em paralelo) e um MUX combinacional seleciona a via com maior ETR para expulsão.

**Em um HIT:** aprende o intervalo de reutilização: `intervalo = relogio_atual - ultimo_acesso` (saturado em 4 bits).

**Em um MISS:** instala o novo bloco na via vítima com `intervalo = 4'hF` (desconhecido = máximo).

---

### 6. `mockingjay_l2_cache.v` — Cache L2 com Mockingjay

Mesma lógica da L1, mas com **8 vias**. Para encontrar a vítima sem for-loop, usa uma **árvore de comparadores de 3 níveis**:

```
Nível 1: (via0 vs via1), (via2 vs via3), (via4 vs via5), (via6 vs via7)  → 4 ganhadores
Nível 2: (w01 vs w23), (w45 vs w67)                                       → 2 ganhadores
Nível 3: resultado final                                                   → vítima
```

Todas as 8 comparações de tag e os 8 cálculos ETR acontecem em paralelo no mesmo ciclo.

---

### 7. `cache_controller.v` — Controlador (FSM Top-Level)

Orquestra L1 e L2 por meio de uma máquina de estados finitos (FSM). O sinal `policy_sel` escolhe o algoritmo:

- `policy_sel=0` → LRU
- `policy_sel=1` → Mockingjay

**Fluxo de estados:**

```
IDLE → L1_CHECK → (hit?)  → L1_HIT           → OUTPUT → IDLE
                → (miss?) → L1_MISS_L2_CHECK  → (hit?) → L2_HIT  → OUTPUT → IDLE
                                               → (miss?)→ L2_MISS → OUTPUT → IDLE
```

Em `OUTPUT`, os sinais `l1_hit_out`, `l2_hit_out`, `full_miss_out` ficam válidos por um ciclo com `result_valid=1`.

---

### 8. `tb_cache_top.v` — Testbench de Integração

Carrega traces de endereços (`$readmemh`), injeta um acesso por vez no `cache_controller` e contabiliza hits/misses em L1 e L2. Ao final, imprime as estatísticas para comparar com o gabarito do simulador C.

---

## Resultados Esperados (Gabarito)

| Trace | Algoritmo | L1 Hits | L1 Misses | L2 Hits | L2 Misses |
|---|---|---|---|---|---|
| `trace_validacao.mem` (8 acessos) | Mockingjay | **4** | **4** | — | — |
| `trace_validacao.mem` (8 acessos) | LRU | **2** | **6** | — | — |
| `trace_mixed_hotset.mem` (8 acessos) | Mockingjay | **4** | **4** | **1** | **3** |

**Por que Mockingjay bate LRU no `trace_validacao`?**

```
Acesso 5: C entra → Mockingjay expulsa B (maior ETR = vai demorar mais)
Acesso 6: A → HIT  ✓  (Mockingjay protegeu A)
           LRU teria expulsado A (era o menos recente) → MISS ✗
```

---

## Pré-requisitos

Escolha uma das ferramentas de simulação:

| Ferramenta | Como obter | Custo |
|---|---|---|
| **Icarus Verilog** | https://bleyer.org/icarus/ | Gratuito |
| **ModelSim / QuestaSim** | Incluído no pacote Intel Quartus | Gratuito (edição web) |
| **Vivado Simulator** | Incluído no Vivado | Gratuito (edição WebPACK) |

---

## Como Rodar

### Opção A — Icarus Verilog (mais simples, recomendado para testes rápidos)

**Simulação completa (L1 + L2, ambos os algoritmos):**

```bash
# Na raiz do projeto
iverilog -o sim_out \
  rtl/address_decoder.v \
  rtl/saturating_counter_4bit.v \
  rtl/etr_calculator.v \
  rtl/mockingjay_l1_cache.v \
  rtl/lru_l1_cache.v \
  rtl/mockingjay_l2_cache.v \
  rtl/cache_controller.v \
  tb/tb_cache_top.v

vvp sim_out
```

**Saída esperada:**
```
[1] 0x00000000 → L1 MISS | L2 MISS
[2] 0x00000800 → L1 MISS | L2 MISS
[3] 0x00000000 → L1 HIT
[4] 0x00000800 → L1 HIT
[5] 0x00001000 → L1 MISS | L2 MISS
[6] 0x00000000 → L1 HIT
[7] 0x00000800 → L1 MISS | L2 MISS
[8] 0x00001000 → L1 HIT
=== trace_validacao | Politica: MOCKINGJAY ===
[L1] Hits: 4  Misses: 4  HitRate: 50.0%
...
```

---

### Opção B — Testes Unitários (módulo por módulo)

Execute cada teste isoladamente para depurar um módulo específico:

```bash
# Contador saturado
iverilog -o tb_sat rtl/saturating_counter_4bit.v tb/tb_saturating_counter.v && vvp tb_sat

# Decodificador de endereço
iverilog -o tb_dec rtl/address_decoder.v tb/tb_address_decoder.v && vvp tb_dec

# Calculador ETR
iverilog -o tb_etr rtl/etr_calculator.v tb/tb_etr_calculator.v && vvp tb_etr

# Cache L1 LRU
iverilog -o tb_lru rtl/lru_l1_cache.v rtl/etr_calculator.v tb/tb_lru_l1.v && vvp tb_lru

# Cache L1 Mockingjay
iverilog -o tb_mj rtl/mockingjay_l1_cache.v rtl/etr_calculator.v tb/tb_mockingjay_l1.v && vvp tb_mj
```

---

### Opção C — ModelSim / QuestaSim

```bash
# Compilar todos os arquivos
vlog rtl/*.v tb/tb_cache_top.v

# Rodar simulação em modo batch
vsim -c tb_cache_top -do "run -all; quit"
```

---

### Opção D — Vivado (interface gráfica)

1. **New Project** → adicionar `rtl/*.v` como Design Sources
2. Adicionar `tb/tb_cache_top.v` como Simulation Source
3. **Run Simulation → Run Behavioral Simulation**
4. No console Tcl: `run all`

---

## Ordem de Validação Recomendada

Siga esta sequência para depurar com menos esforço:

1. `tb_saturating_counter` — valida saturação em 15
2. `tb_address_decoder` — valida aritmética de bits (tag e index)
3. `tb_etr_calculator` — valida fórmula ETR
4. `tb_lru_l1` — valida padrão de comparadores paralelos (mais simples)
5. `tb_mockingjay_l1` — **marco: 4 hits / 4 misses no trace_validacao**
6. `tb_cache_top` — simulação completa, compara com gabarito

---

## Hierarquia de Módulos

```
tb_cache_top
└── cache_controller
    ├── address_decoder #(OFFSET=5, INDEX=6, TAG=21)   u_dec_l1
    ├── address_decoder #(OFFSET=6, INDEX=6, TAG=20)   u_dec_l2
    ├── saturating_counter_4bit                         u_global_clk
    ├── mockingjay_l1_cache                             u_mj_l1
    │   ├── etr_calculator                              u_etr0
    │   └── etr_calculator                              u_etr1
    ├── lru_l1_cache                                    u_lru_l1
    └── mockingjay_l2_cache                             u_mj_l2
        ├── etr_calculator                              u_etr0
        ├── etr_calculator                              u_etr1
        │   ...
        └── etr_calculator                              u_etr7
```

---

## Restrições de Hardware Implementadas

- **Comparadores paralelos:** todas as vias são comparadas simultaneamente via `wire` e MUX — nenhum for-loop em lógica RTL
- **Contadores saturados de 4 bits:** substituem `int relogio_global` do C; alcance 0–15, trava em 15 sem overflow
- **Blocos non-blocking (`<=`)** em `always @(posedge clk)` e blocking (`=`) em `always @(*)`
