# Guia Técnico do Projeto — ProjetoCache_Verilog

Este documento é o **complemento técnico** do `GUIA_PROJETO.md`. Enquanto
aquele explica cada arquivo em linguagem didática/narrativa, este aqui assume
que você já leu o `GUIA_PROJETO.md` e entende a visão geral (o que é L1/L2, o
que é LRU, o que é Mockingjay/ETR) e entra no nível de **sinal e função**: para
cada módulo `rtl/*.v`, mostra os parâmetros e portas, as estruturas de
armazenamento internas, separa explicitamente o **estágio combinacional**
(`assign`/lógica sem clock) do **estágio sequencial** (`always @(posedge
clk)`) e explica como cada módulo se conecta aos outros.

Os números de hit/miss e o fluxo da FSM citados aqui seguem exatamente o
`CLAUDE.md` (§1.2–§1.4), que é a fonte de verdade arquitetural do projeto —
este guia não repete esses números, só a mecânica de como o hardware chega
neles.

---

## Parte 1 — Módulos de apoio (sem estado ou com 1 registrador)

------- address_decoder.v -------

### Parâmetros e portas

```verilog
module address_decoder #(
    parameter OFFSET_BITS = 5,   // L1: 5 (bloco 32B), L2: 6 (bloco 64B)
    parameter INDEX_BITS  = 6,   // sempre 6 (64 conjuntos)
    parameter TAG_BITS    = 21   // L1: 21, L2: 20
)(
    input  wire [31:0]            addr,
    output wire [INDEX_BITS-1:0]  set_index,
    output wire [TAG_BITS-1:0]    tag
);
```

- `OFFSET_BITS`, `INDEX_BITS`, `TAG_BITS` são parâmetros de elaboração (não
  sinais de runtime): o mesmo arquivo é instanciado duas vezes dentro do
  `cache_controller` com valores diferentes — uma vez para a L1
  (`OFFSET_BITS=5, TAG_BITS=21`) e outra para a L2 (`OFFSET_BITS=6,
  TAG_BITS=20`). O módulo **não** valida que `OFFSET_BITS + INDEX_BITS +
  TAG_BITS = 32`; é responsabilidade de quem instancia manter essa soma
  correta — se não bater, os slices de `addr` ultrapassam os 32 bits
  disponíveis.
- `addr` é o único dado de entrada; `set_index` e `tag` são as duas saídas
  fatiadas.

### Estruturas internas

Nenhuma — não há `reg` nem array. O módulo não guarda estado.

### Estágio combinacional

Duas atribuições contínuas (`assign`), sem `always` em lugar nenhum do
arquivo:

```verilog
assign set_index = addr[OFFSET_BITS + INDEX_BITS - 1 : OFFSET_BITS];
assign tag       = addr[31 : OFFSET_BITS + INDEX_BITS];
```

- `set_index` pega a fatia de bits logo acima do offset — com os valores da
  L1 isso é `addr[10:5]`; com os da L2, `addr[11:6]`.
- `tag` pega tudo que sobra acima do índice — `addr[31:11]` na L1 (21 bits),
  `addr[31:12]` na L2 (20 bits).
- Não há extração do campo de offset em si (`addr[OFFSET_BITS-1:0]`) — este
  módulo não precisa dele, porque nenhuma cache do projeto guarda dado de
  bloco (ver Limitação Conhecida #1 do `CLAUDE.md`), só tag/estado.

### Estágio sequencial

Não existe. É puramente combinacional — a saída muda instantaneamente (dentro
de 1 delta-cycle de simulação) sempre que `addr` muda.

### Relação com outros módulos

Instanciado 2× dentro de `cache_controller.v`: `u_dec_l1` (parâmetros de L1)
e `u_dec_l2` (parâmetros de L2), ambos alimentados pelo mesmo `address[31:0]`
de entrada do controller. As saídas `set_index`/`tag` de cada instância
alimentam, respectivamente, `mockingjay_l1_cache`/`lru_l1_cache` e
`mockingjay_l2_cache`.

Validado por `tb_address_decoder.v`.

---

------- saturating_counter_4bit.v -------

### Parâmetros e portas

Não há `parameter` — a largura de 4 bits é fixa no nome e nas portas.

```verilog
module saturating_counter_4bit (
    input  wire       clk,
    input  wire       rst_n,      // reset síncrono ativo-baixo
    input  wire       enable,     // incrementa quando alto
    input  wire [3:0] load_val,   // valor a carregar
    input  wire       load_en,    // força carga (prioridade sobre incremento)
    output reg  [3:0] count
);
```

`count` é ao mesmo tempo a porta de saída e o único registrador de estado do
módulo — não existe um `reg` interno separado, o próprio `count` é o estado.

### Estruturas internas

Nenhuma além de `count`. É a contrapartida em hardware do `int
relogio_global` do simulador C, só que limitada a 4 bits com saturação em vez
de overflow de inteiro (comentário do próprio arquivo).

### Estágio combinacional

Não há lógica combinacional neste módulo — as saídas dependem só do clock.

### Estágio sequencial

Um único `always @(posedge clk)`, com prioridade em cascata (`if`/`else if`):

```verilog
always @(posedge clk) begin
    if (!rst_n)
        count <= 4'd0;
    else if (load_en)
        count <= load_val;
    else if (enable && count < 4'd15)
        count <= count + 4'd1;
    // else: count mantém o valor (enable=0, ou count==15 saturado)
end
```

Ordem de prioridade: **reset (síncrono) > carga externa > incremento >
manutenção**. Dois pontos importantes:
- O reset é **síncrono** (`rst_n` é testado dentro de `always @(posedge
  clk)`, não numa lista de sensibilidade `negedge rst_n` separada).
- A saturação não é um `if (count == 15) count <= 0` disfarçado — é a
  ausência de qualquer atribuição quando `count == 15` e `enable=1`: a
  condição de guarda `count < 4'd15` simplesmente falha, então nenhum `<=`
  dispara e o registrador retém 15 no próximo ciclo. Não há wraparound para
  0.

### Relação com outros módulos

Instanciado uma vez em `cache_controller.v` como `u_global_clk`. O `enable`
dele é o sinal `clk_enable`, que o controller pulsa **exatamente 1 vez por
acesso completo** (na transição `IDLE → L1_CHECK`) — não uma vez por ciclo de
FSM. `load_en` está fixo em `1'b0` no projeto real; a porta de carga só é
exercitada pelo testbench (`tb_saturating_counter.v`), nunca pelo
`cache_controller`. A saída `count` vira o `global_time` distribuído para
`mockingjay_l1_cache` e `mockingjay_l2_cache`.

Validado por `tb_saturating_counter.v`.

---

------- etr_calculator.v -------

### Parâmetros e portas

Sem `parameter` — larguras fixas (entradas de 4 bits, saídas de 5 bits, para
acomodar o carry da soma).

```verilog
module etr_calculator (
    input  wire [3:0] last_access,
    input  wire [3:0] interval,
    input  wire [3:0] current_time,
    output wire [4:0] etr,
    output wire       etr_negative
);
```

### Estruturas internas

Um único `wire` intermediário: `sum`.

### Estágio combinacional

Todo o módulo é isto (nenhum `always`, só `assign`/`wire`):

```verilog
wire [4:0] sum = {1'b0, last_access} + {1'b0, interval};

assign etr          = sum - {1'b0, current_time};
assign etr_negative = (sum < {1'b0, current_time});
```

- `sum` zero-estende `last_access` e `interval` de 4 para 5 bits antes de
  somar — a soma de dois valores de 4 bits pode chegar a 30, que não cabe em
  4 bits, então precisa do bit extra. `sum` representa o "instante absoluto
  em que o bloco deveria ser reusado" (fórmula do cabeçalho: `ETR =
  (ultimo_acesso + intervalo_previsto) - relogio_atual`).
- `etr` é `sum - current_time`, calculado em unsigned de 5 bits. Se
  matematicamente o resultado fosse negativo, ele "enrola" para um valor
  grande em complemento de dois interpretado como unsigned — por isso `etr`
  sozinho **não** é confiável para decidir se o bloco está atrasado; é para
  isso que existe `etr_negative`.
- `etr_negative = (sum < current_time)` é a comparação que realmente decide
  "esse ETR é negativo". É **estritamente `<`**, não `<=`. Esse é o detalhe
  mais crítico do arquivo inteiro, documentado em maiúsculas no cabeçalho do
  código-fonte:

  > `IMPORTANTE: ETR == 0 NÃO é negativo — fica protegido (eff=0). Isso
  > espelha exatamente o if (tempo_estimado_reuso < 0) do simulador C de
  > referência.`

  Quando `sum == current_time` (ETR exatamente 0), `etr_negative` fica em 0
  — o bloco é tratado como **protegido**, não como atrasado/candidato a
  despejo. Trocar esse `<` por `<=` quebraria a paridade com o simulador C de
  referência (foi, de fato, um bug real já encontrado e corrigido nesta
  sprint — ver `sim/validation_report.md`).

### Estágio sequencial

Não existe — módulo 100% combinacional.

### Relação com outros módulos

Não é instanciado sozinho em produção — é o bloco reutilizável de cálculo de
ETR, instanciado **2×** dentro de `mockingjay_l1_cache.v` (uma por via) e
**8×** dentro de `mockingjay_l2_cache.v` (uma por via). O contrato de uso
documentado no próprio cabeçalho é: *quando `etr_negative=1`, o módulo
chamador deve substituir o valor bruto de `etr` por `5'b11111` (31) antes de
usá-lo em qualquer comparação de vítima* — é exatamente o que os dois
módulos de cache fazem através do sinal intermediário `eff` (ver seções
seguintes).

Validado por `tb_etr_calculator.v`.

---

## Parte 2 — Caches L1 (2 vias)

------- lru_l1_cache.v -------

### Parâmetros e portas

Sem `parameter` — dimensões fixas no código: **2 vias**, **64 conjuntos**,
**tag de 21 bits**.

```verilog
module lru_l1_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [20:0] tag_in,
    input  wire [5:0]  set_index_in,
    output reg          hit,
    output reg          l2_access_needed,
    output reg          way_used,
    output reg          done
);
```

Comentário do cabeçalho é explícito sobre a intenção: *"Mesma interface do
`mockingjay_l1_cache` para facilitar comparação no testbench"* — os dois
módulos foram desenhados para serem intercambiáveis por trás de um MUX
(exatamente o que `cache_controller` faz via `policy_sel`).

### Estruturas internas

```verilog
reg        valid    [0:1][0:63];   // validade por via/conjunto
reg [20:0] tag_store[0:1][0:63];   // tag armazenada por via/conjunto
reg        lru_bit  [0:63];        // 1 bit de LRU por CONJUNTO
integer i, j;                       // só usados no reset
```

O ponto central deste módulo: o estado de "quem é o LRU" cabe em **1 bit por
conjunto**, não em contadores de idade por via. Com apenas 2 vias, basta
saber qual delas foi acessada por último — a outra é, por definição, a LRU.
Isso substitui o `uint32_t idade` do simulador C por um único bit
(comentário do cabeçalho do arquivo).

### Estágio combinacional

```verilog
wire hit_way0 = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
wire hit_way1 = valid[1][set_index_in] && (tag_store[1][set_index_in] == tag_in);
wire l1_hit   = hit_way0 | hit_way1;
wire hit_way_sel = hit_way1;
```

- `hit_way0`/`hit_way1` são **dois comparadores físicos distintos**, um por
  via, avaliados no mesmo instante — não é um laço percorrendo as vias em
  série, é hardware paralelo de fato (requisito do professor, ver
  `CLAUDE.md` §1.6).
- `hit_way_sel` é um atalho: como só existem 2 vias, basta saber se a via 1
  acertou. Se `l1_hit=1` e `hit_way1=0`, obrigatoriamente foi a via 0 — não
  precisa de um encoder de prioridade explícito como na L2 (8 vias).

```verilog
wire empty0 = !valid[0][set_index_in];
wire empty1 = !valid[1][set_index_in];

wire victim_way = empty0 ? 1'b0 :
                  empty1 ? 1'b1 :
                  lru_bit[set_index_in];
```

`victim_way` é um MUX combinacional (cadeia de operadores ternários,
equivalente a uma árvore de MUX 2:1, sem `for`): primeiro dá prioridade a uma
via vazia (preencher espaço livre antes de expulsar algo); só se as duas
vias estiverem ocupadas é que o `lru_bit[set_index_in]` decide — e decide
diretamente, sem comparação adicional, porque com 2 vias o próprio bit já
*é* o índice da via a expulsar.

### Estágio sequencial

Um `always @(posedge clk)`. No reset, `for` duplo estático (permitido dentro
de `if (!rst_n)`, sintetiza como inicialização paralela dos 2×64 registros,
não como replicação dinâmica de lógica):

```verilog
for (i = 0; i < 2; i = i + 1)
    for (j = 0; j < 64; j = j + 1) begin
        valid[i][j]     <= 1'b0;
        tag_store[i][j] <= 21'd0;
    end
for (j = 0; j < 64; j = j + 1)
    lru_bit[j] <= 1'b0;
```

Fora do reset, com `access_en=1`:
- `done <= 1` (o pulso de "resultado pronto" sobe neste ciclo).
- **Hit**: `hit<=1`, `l2_access_needed<=0`, `way_used<=hit_way_sel`, e
  `lru_bit[set_index_in] <= ~hit_way_sel` — a via que acabou de ser acessada
  vira MRU, então o bit passa a apontar para a via **oposta** como nova LRU.
- **Miss**: `hit<=0`, `l2_access_needed<=1`, `way_used<=victim_way`; instala
  o bloco (`valid[victim_way][...]<=1`, `tag_store[victim_way][...]<=tag_in`)
  e também marca a via recém-instalada como MRU
  (`lru_bit[set_index_in]<=~victim_way`).

Com `access_en=0` (fora de reset): `done<=0` e `l2_access_needed<=0` —
essa queda incondicional a cada ciclo ocioso é o que garante que `done` dure
**exatamente 1 ciclo** por acesso (ver `access_en` como protocolo de pulso,
explicado na próxima seção, que é idêntico aqui).

### Relação com outros módulos

Não instancia nada (não usa `etr_calculator`). É instanciado como `u_lru_l1`
dentro de `cache_controller.v`, recebendo `tag_l1`/`set_l1` (saída do
`u_dec_l1`) e só é habilitado (`access_en = lru_l1_en`) quando
`policy_sel=0`.

Validado por `tb_lru_l1.v` (trace `A B A B C A B C` → 2 hits / 6 misses).

---

------- mockingjay_l1_cache.v -------

### Parâmetros e portas

Mesmas dimensões do LRU (2 vias, 64 conjuntos, tag 21 bits), mas com uma
porta a mais: `global_time`.

```verilog
module mockingjay_l1_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [20:0] tag_in,
    input  wire [5:0]  set_index_in,
    input  wire [3:0]  global_time,
    output reg          hit,
    output reg          l2_access_needed,
    output reg          way_used,
    output reg          done
);
```

O cabeçalho do arquivo documenta explicitamente o protocolo de uso (o mesmo
vale para o LRU, ainda que não repetido no comentário de lá):

```
// Protocolo de uso:
//   1. Apresente tag_in, set_index_in, global_time
//   2. Pulse access_en=1 por um ciclo
//   3. No próximo posedge: hit/l2_access_needed ficam válidos, done=1
//   4. No ciclo seguinte: done volta a 0
```

Se `access_en` ficasse em 1 por mais de 1 ciclo, o módulo reprocessaria o
**mesmo** acesso a cada `posedge` — no caso do Mockingjay isso é
particularmente destrutivo, porque um hit repetido re-"aprenderia" o
intervalo com `learned≈0` a cada ciclo, corrompendo a heurística de ETR. É
por isso que `cache_controller` cuida tão explicitamente de gerar `access_en`
como pulso de exatamente 1 ciclo (ver seção do controller).

### Estruturas internas

```verilog
reg        valid    [0:1][0:63];
reg [20:0] tag_store[0:1][0:63];
reg [3:0]  last_acc [0:1][0:63];   // timestamp do último acesso
reg [3:0]  interval [0:1][0:63];   // intervalo de reuso aprendido/previsto
integer i, j;
```

Em vez do `lru_bit` de 1 bit por conjunto, cada via/conjunto guarda **dois
campos de 4 bits**: quando foi acessado pela última vez (`last_acc`) e há
quanto tempo, historicamente, esse bloco costuma ser reacessado
(`interval`). É esse par que alimenta o `etr_calculator`.

### Estágio combinacional

**1. Comparadores de hit** — idênticos em estrutura ao LRU:

```verilog
wire hit_way0 = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
wire hit_way1 = valid[1][set_index_in] && (tag_store[1][set_index_in] == tag_in);
wire l1_hit   = hit_way0 | hit_way1;
wire hit_way_sel = hit_way1;
```

**2. Duas instâncias de `etr_calculator`, uma por via, em paralelo** —
requisito explícito do professor citado no próprio cabeçalho do arquivo
("REQUISITO DO PROFESSOR: comparadores paralelos... Dois módulos
etr_calculator rodam em paralelo no mesmo ciclo"):

```verilog
wire [4:0] etr0; wire neg0;
wire [4:0] etr1; wire neg1;

etr_calculator u_etr0(.last_access(last_acc[0][set_index_in]), .interval(interval[0][set_index_in]),
                       .current_time(global_time), .etr(etr0), .etr_negative(neg0));
etr_calculator u_etr1(.last_access(last_acc[1][set_index_in]), .interval(interval[1][set_index_in]),
                       .current_time(global_time), .etr(etr1), .etr_negative(neg1));
```

São duas instâncias físicas distintas — não um único `etr_calculator`
reaproveitado em série via `for`. Cada uma lê os metadados da sua própria via
no conjunto endereçado e o `global_time` comum.

**3. ETR efetivo (`eff`)** — aplica o contrato documentado em
`etr_calculator.v`: se o ETR calculado é negativo, força para o valor máximo
de 5 bits, tornando o bloco "atrasado" o candidato mais óbvio a expulsão:

```verilog
wire [4:0] eff0 = neg0 ? 5'b11111 : etr0;
wire [4:0] eff1 = neg1 ? 5'b11111 : etr1;
```

**4. Detecção de via vazia e MUX de vítima:**

```verilog
wire empty0 = !valid[0][set_index_in];
wire empty1 = !valid[1][set_index_in];

wire victim_way = empty0          ? 1'b0 :
                  empty1          ? 1'b1 :
                  (eff0 >= eff1)  ? 1'b0 : 1'b1;
```

Mesma prioridade do LRU (vaga livre antes de qualquer política), mas quando
as duas vias estão ocupadas, a decisão passa a ser **qual via tem o maior
ETR efetivo** — a que a heurística acredita que vai demorar mais para ser
reusada é a escolhida para sair. Em empate (`eff0 == eff1`), o `>=` favorece
a via 0.

**5. Cálculo do intervalo aprendido (`learned`)** — o "aprendizado" do
Mockingjay:

```verilog
wire [4:0] learned_full = {1'b0, global_time} - {1'b0, last_acc[hit_way_sel][set_index_in]};
wire [3:0] learned = (learned_full > 5'd15) ? 4'hF : learned_full[3:0];
```

`learned_full` mede quanto tempo se passou, em unidades de `global_time`,
desde o último acesso à via que **acertou** neste ciclo (`hit_way_sel`) —
essa distância observada vira a nova previsão de intervalo de reuso. Se
ultrapassar 15 (não cabe em 4 bits), é saturado em `4'hF` em vez de estourar.
Este `wire` é sempre calculado combinacionalmente, mas só é efetivamente
**capturado** (gravado em `interval`) no estágio sequencial, e só no ramo de
hit.

### Estágio sequencial

Reset com `for` duplo estático, mas agora inicializando 4 arrays em vez de
2 — nota o valor sentinela `4'hF` para `interval`:

```verilog
for (i = 0; i < 2; i = i + 1)
    for (j = 0; j < 64; j = j + 1) begin
        valid[i][j]     <= 1'b0;
        tag_store[i][j] <= 21'd0;
        last_acc[i][j]  <= 4'd0;
        interval[i][j]  <= 4'hF;   // MAX_INTERVALO — "desconhecido"
    end
```

Fora do reset, com `access_en=1`:
- `done <= 1`.
- **Hit** (comentário no código: *"HIT: aprende intervalo e atualiza
  timestamp"*):
  ```verilog
  hit <= 1'b1; l2_access_needed <= 1'b0; way_used <= hit_way_sel;
  interval[hit_way_sel][set_index_in] <= learned;
  last_acc[hit_way_sel][set_index_in] <= global_time;
  ```
- **Miss** (comentário: *"MISS: instala bloco na via vítima"*):
  ```verilog
  hit <= 1'b0; l2_access_needed <= 1'b1; way_used <= victim_way;
  valid[victim_way][set_index_in]     <= 1'b1;
  tag_store[victim_way][set_index_in] <= tag_in;
  last_acc[victim_way][set_index_in]  <= global_time;
  interval[victim_way][set_index_in]  <= 4'hF;
  ```
  Um bloco recém-instalado começa com `interval=4'hF` (o valor sentinela
  "desconhecido"/máximo) — sem histórico de reuso, o Mockingjay assume o
  pior caso, o que faz esse bloco ter ETR alto e virar candidato a expulsão
  rápida se não for reacessado logo.

Com `access_en=0` (fora de reset): `done<=0`, `l2_access_needed<=0` — mesmo
mecanismo de pulso de 1 ciclo do LRU.

### Relação com outros módulos

Instancia `etr_calculator` 2× (`u_etr0`, `u_etr1`). É instanciado como
`u_mj_l1` dentro de `cache_controller.v`, recebendo `tag_l1`/`set_l1`
(mesmas saídas do `u_dec_l1` usadas pelo LRU) e o `global_time` vindo de
`u_global_clk`; só é habilitado (`access_en = mj_l1_en`) quando
`policy_sel=1`.

Validado por `tb_mockingjay_l1.v` (mesmo trace do LRU → 3 hits / 5 misses).

---

## Parte 3 — Cache L2 (8 vias)

------- mockingjay_l2_cache.v -------

### Parâmetros e portas

Sem `parameter` — dimensões fixas: **8 vias**, **64 conjuntos**, **tag de 20
bits** (1 bit a menos que a L1, porque o bloco de 64 B consome 1 bit a mais
de offset).

```verilog
module mockingjay_l2_cache (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        access_en,
    input  wire [19:0] tag_in,
    input  wire [5:0]  set_index_in,
    input  wire [3:0]  global_time,
    output reg          hit,
    output reg  [2:0]   way_used,   // 3 bits: índice de via 0–7
    output reg          done
);
```

Diferença notável em relação à L1: **não existe `l2_access_needed`** — a L2 é
o último nível da hierarquia (não há L3 para onde escalar em caso de miss).

### Estruturas internas

```verilog
reg        valid    [0:7][0:63];
reg [19:0] tag_store[0:7][0:63];
reg [3:0]  last_acc [0:7][0:63];
reg [3:0]  interval [0:7][0:63];
integer i, j;
```

Mesmo padrão de campos do L1 Mockingjay (`last_acc`/`interval` de 4 bits por
via/conjunto), só que agora com 8 vias em vez de 2 — não há `lru_bit`
nenhum, a L2 só existe na variante Mockingjay (decisão deliberada do
projeto, ver `duvidas_projeto.md`: a L2 é o caminho mais caro, então vale a
pena aplicar ali só o algoritmo mais inteligente).

### Estágio combinacional

**1. Oito comparadores de hit em paralelo + encoder de prioridade:**

```verilog
wire hit_way [0:7];
assign hit_way[0] = valid[0][set_index_in] && (tag_store[0][set_index_in] == tag_in);
// ... hit_way[1] .. hit_way[7], mesmo padrão

wire l2_hit = |{hit_way[7],hit_way[6],hit_way[5],hit_way[4],
                hit_way[3],hit_way[2],hit_way[1],hit_way[0]};

wire [2:0] hit_way_sel = hit_way[1] ? 3'd1 :
                         hit_way[2] ? 3'd2 :
                         hit_way[3] ? 3'd3 :
                         hit_way[4] ? 3'd4 :
                         hit_way[5] ? 3'd5 :
                         hit_way[6] ? 3'd6 :
                         hit_way[7] ? 3'd7 : 3'd0;
```

As 8 comparações de tag acontecem simultaneamente (8 circuitos físicos
distintos). `l2_hit` é o OR reduzido de todas elas. Diferente da L1 (onde
`hit_way1` sozinho já bastava como índice), aqui é preciso um **encoder de
prioridade** explícito (`hit_way_sel`) para converter o vetor de 8 flags em
um índice de 3 bits.

**2. Oito instâncias de `etr_calculator` em paralelo**, uma por via, todas
lendo o mesmo `global_time` e seus próprios `last_acc`/`interval`:

```verilog
wire [4:0] etr [0:7];
wire       neg [0:7];
etr_calculator u_etr0(.last_access(last_acc[0][set_index_in]), .interval(interval[0][set_index_in]),
                       .current_time(global_time), .etr(etr[0]), .etr_negative(neg[0]));
// ... u_etr1 .. u_etr7, mesmo padrão para as vias 1–7
```

**3. ETR efetivo e detecção de vias vazias** (mesmo padrão do L1, só que ×8):

```verilog
wire [4:0] eff [0:7];
assign eff[0] = neg[0] ? 5'b11111 : etr[0];   // ... eff[1]..eff[7] análogo

wire empty [0:7];
assign empty[0] = !valid[0][set_index_in];    // ... empty[1]..empty[7] análogo
```

**4. Árvore de comparadores de 3 níveis** — este é o mecanismo central que
diferencia a L2 da L1: achar "o maior ETR entre 8 valores" sem usar `for`,
em profundidade lógica de apenas 3 comparações em cascata (não 7
comparações seriais):

```verilog
// Nível 1 — 4 comparações simultâneas, cada uma decide o vencedor de um par
wire [2:0] w01 = (eff[0] >= eff[1]) ? 3'd0 : 3'd1;
wire [2:0] w23 = (eff[2] >= eff[3]) ? 3'd2 : 3'd3;
wire [2:0] w45 = (eff[4] >= eff[5]) ? 3'd4 : 3'd5;
wire [2:0] w67 = (eff[6] >= eff[7]) ? 3'd6 : 3'd7;

// Nível 2 — 2 comparações, usando indexação indireta (eff[w01] etc.)
wire [2:0] w0123 = (eff[w01] >= eff[w23]) ? w01 : w23;
wire [2:0] w4567 = (eff[w45] >= eff[w67]) ? w45 : w67;

// Nível 3 — comparação final, decide a vítima
wire [2:0] etr_victim = (eff[w0123] >= eff[w4567]) ? w0123 : w4567;
```

Cada `wire` intermediário (`w01`, `w23`, ..., `w0123`, `w4567`) guarda o
**índice da via vencedora** daquele confronto, não o valor do ETR em si — o
nível seguinte usa esse índice para indexar `eff[]` de novo
(`eff[w01]`) e decidir o próximo vencedor. É literalmente um chaveamento de
campeonato esportivo (8 → 4 → 2 → 1), todo resolvido dentro do mesmo ciclo de
clock porque é 100% lógica combinacional. `etr_victim` ao final é o índice
(0–7) da via com maior ETR efetivo entre as 8.

**5. Seleção final — vaga livre tem prioridade sobre a árvore de ETR:**

```verilog
wire [2:0] victim_way = empty[0] ? 3'd0 :
                        empty[1] ? 3'd1 :
                        empty[2] ? 3'd2 :
                        empty[3] ? 3'd3 :
                        empty[4] ? 3'd4 :
                        empty[5] ? 3'd5 :
                        empty[6] ? 3'd6 :
                        empty[7] ? 3'd7 : etr_victim;
```

Mesmo princípio da L1: só usa o resultado da árvore de comparadores
(`etr_victim`) se todas as 8 vias já estiverem ocupadas; senão, preenche a
primeira vaga livre encontrada.

**6. Intervalo aprendido no hit** — idêntico em fórmula ao L1:

```verilog
wire [4:0] learned_full = {1'b0, global_time} - {1'b0, last_acc[hit_way_sel][set_index_in]};
wire [3:0] learned = (learned_full > 5'd15) ? 4'hF : learned_full[3:0];
```

### Estágio sequencial

```verilog
always @(posedge clk) begin
    if (!rst_n) begin
        done <= 1'b0; hit <= 1'b0; way_used <= 3'd0;
        for (i = 0; i < 8; i = i + 1)
            for (j = 0; j < 64; j = j + 1) begin
                valid[i][j]     <= 1'b0;
                tag_store[i][j] <= 20'd0;
                last_acc[i][j]  <= 4'd0;
                interval[i][j]  <= 4'hF;
            end
    end else if (access_en) begin
        done <= 1'b1;
        if (l2_hit) begin
            hit <= 1'b1; way_used <= hit_way_sel;
            interval[hit_way_sel][set_index_in] <= learned;
            last_acc[hit_way_sel][set_index_in] <= global_time;
        end else begin
            hit <= 1'b0; way_used <= victim_way;
            valid[victim_way][set_index_in]     <= 1'b1;
            tag_store[victim_way][set_index_in] <= tag_in;
            last_acc[victim_way][set_index_in]  <= global_time;
            interval[victim_way][set_index_in]  <= 4'hF;
        end
    end else begin
        done <= 1'b0;
    end
end
```

Estrutura idêntica ao L1 Mockingjay (reset com `for` duplo estático agora
8×64, hit atualiza só a via acertada, miss instala na via vítima com
`interval=4'hF`), só que a árvore de comparadores substitui o MUX simples de
2 entradas do L1. O pulso de `done`/`access_en` segue o mesmo protocolo de 1
ciclo já descrito para a L1.

### Relação com outros módulos

Instancia `etr_calculator` 8× (`u_etr0`..`u_etr7`). É instanciada como
`u_mj_l2` dentro de `cache_controller.v`, recebendo `tag_l2`/`set_l2` (saída
do `u_dec_l2`) e é acessada **apenas** quando a L1 (seja LRU ou Mockingjay)
sinaliza miss — não existe versão LRU da L2 no projeto.

Validado por `tb_mockingjay_l2.v` (cenário controlado: 8 preenchimentos, 1
hit que ensina intervalo, 1 miss com expulsão da via de maior ETR).

---

## Parte 4 — Orquestração (FSM e wrapper de síntese)

------- cache_controller.v -------

### Parâmetros e portas

Sem `parameter` de dimensão (esses ficam nos submódulos). Portas:

```verilog
module cache_controller (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,          // pulso para iniciar um acesso
    input  wire [31:0] address,
    input  wire        policy_sel,     // 0=LRU, 1=Mockingjay
    output reg         result_valid,
    output reg         l1_hit_out,
    output reg         l2_hit_out,
    output reg         full_miss_out,
    output reg  [2:0]  state_debug
);
```

### Estados da FSM

```verilog
localparam IDLE             = 3'd0;
localparam L1_CHECK         = 3'd1;
localparam L1_HIT           = 3'd2;
localparam L1_MISS_L2_CHECK = 3'd3;
localparam L2_HIT           = 3'd4;
localparam L2_MISS          = 3'd5;
localparam OUTPUT           = 3'd6;

reg [2:0] state, next_state;
```

7 estados usados de 8 possíveis em 3 bits (`state_debug` expõe `state`
diretamente para depuração/SignalTap).

### Estágio combinacional — lógica de próximo estado

Bloco `always @(*)` que decide `next_state` a partir de `state` e das
condições de `done`/`hit` vindas dos submódulos:

```
IDLE:             if (start)      next_state = L1_CHECK;
L1_CHECK:         if (l1_done)    next_state = l1_hit ? L1_HIT : L1_MISS_L2_CHECK;
L1_HIT:                           next_state = OUTPUT;
L1_MISS_L2_CHECK: if (mj_l2_done) next_state = mj_l2_hit ? L2_HIT : L2_MISS;
L2_HIT:                           next_state = OUTPUT;
L2_MISS:                          next_state = OUTPUT;
OUTPUT:                           next_state = IDLE;
default:                          next_state = IDLE;
```

Fluxo: `IDLE` espera `start`; `L1_CHECK` **permanece parado nesse mesmo
estado** enquanto `l1_done=0` (a cache L1 ativa leva ao menos 1 ciclo interno
para produzir `done`), só bifurcando quando `l1_done` sobe; o mesmo padrão de
espera se repete em `L1_MISS_L2_CHECK` aguardando `mj_l2_done`. `L1_HIT`,
`L2_HIT` e `L2_MISS` sempre seguem incondicionalmente para `OUTPUT`, que por
sua vez sempre volta para `IDLE`.

### Estágio combinacional — seleção de política (`policy_sel`)

```verilog
wire l1_hit       = policy_sel ? mj_l1_hit       : lru_l1_hit;
wire l1_l2_needed = policy_sel ? mj_l1_l2_needed : lru_l1_l2_needed;
wire l1_done      = policy_sel ? mj_l1_done      : lru_l1_done;
```

Três MUXes 2:1 combinacionais escolhem, entre as saídas de `u_mj_l1` e
`u_lru_l1`, qual conjunto alimenta a FSM. **As duas instâncias L1 recebem o
mesmo `tag_l1`/`set_l1` e existem em paralelo o tempo todo** — a diferença é
que só a que corresponde a `policy_sel` recebe um pulso de `access_en`; a
outra fica ociosa. A L2 é única (só existe em Mockingjay) e é sempre
acessada com essa mesma política quando necessário, independente de
`policy_sel`.

### Estágio sequencial — geração dos pulsos de enable (o ponto mais sutil do projeto)

```verilog
always @(posedge clk) begin
    state <= next_state;   // (registrador de estado da FSM)

    // valores padrão a cada ciclo — zerados antes do case
    result_valid <= 1'b0;
    clk_enable   <= 1'b0;
    mj_l1_en     <= 1'b0;
    lru_l1_en    <= 1'b0;
    mj_l2_en     <= 1'b0;

    case (next_state)
        L1_CHECK: if (state == IDLE) begin
            clk_enable <= 1'b1;
            mj_l1_en   <= policy_sel;
            lru_l1_en  <= ~policy_sel;
        end
        L1_MISS_L2_CHECK: if (state == L1_CHECK) begin
            mj_l2_en <= 1'b1;
        end
        OUTPUT: begin
            result_valid  <= 1'b1;
            l1_hit_out    <= (state == L1_HIT);
            l2_hit_out    <= (state == L2_HIT);
            full_miss_out <= (state == L2_MISS);
        end
    endcase
end
```

O truque que garante **exatamente 1 ciclo de pulso** por sinal: o `case`
observa `next_state` (para onde a FSM está indo), mas cada ramo só dispara
sob uma condição adicional sobre o `state` **atual** (`if (state==IDLE)` para
entrar em `L1_CHECK`; `if (state==L1_CHECK)` para entrar em
`L1_MISS_L2_CHECK`). Como `L1_CHECK` pode permanecer como `next_state` por
vários ciclos seguidos (enquanto espera `l1_done` subir), sem essa guarda o
enable seria reafirmado a cada um desses ciclos — fazendo a cache L1
processar o mesmo acesso **duas vezes** e o relógio global incrementar 2×
por acesso em vez de 1×. Esse foi, de fato, um bug real encontrado e
corrigido durante a validação (ver `sim/validation_report.md` e
`CLAUDE.md`, Armadilhas Comuns).

Como todos os `reg` de enable são zerados por padrão a cada ciclo e só
recebem `1` sob a condição de borda de entrada, o pulso dura sempre
exatamente 1 ciclo de clock.

Mesma lógica explica `result_valid`/`l1_hit_out`/`l2_hit_out`/
`full_miss_out`: só são setados quando `next_state == OUTPUT`, e como a FSM
passa incondicionalmente só 1 ciclo em `OUTPUT` antes de voltar a `IDLE`,
esses sinais também ficam ativos por exatamente 1 ciclo — o ciclo em que
`state == OUTPUT`. Note que `l1_hit_out`/`l2_hit_out`/`full_miss_out`
comparam contra `state` (não `next_state`), ou seja, capturam de **qual**
estado a FSM veio na transição para `OUTPUT`.

### Relógio global

```verilog
saturating_counter_4bit u_global_clk (
    .clk(clk), .rst_n(rst_n),
    .enable(clk_enable),
    .load_val(4'd0), .load_en(1'b0),
    .count(global_time)
);
```

`clk_enable` só é setado no mesmo pulso de entrada de `L1_CHECK` — portanto o
relógio global incrementa **1 vez por acesso completo**, não 1 vez por ciclo
de FSM. `load_en` está fixo em 0: em produção o contador nunca é recarregado
externamente, só incrementa.

### Instâncias de submódulos

1. `address_decoder #(.OFFSET_BITS(5), .INDEX_BITS(6), .TAG_BITS(21)) u_dec_l1` → `set_l1`/`tag_l1`.
2. `address_decoder #(.OFFSET_BITS(6), .INDEX_BITS(6), .TAG_BITS(20)) u_dec_l2` → `set_l2`/`tag_l2`.
3. `saturating_counter_4bit u_global_clk` → `global_time`.
4. `mockingjay_l1_cache u_mj_l1` (`access_en=mj_l1_en`) → `mj_l1_hit`, `mj_l1_l2_needed`, `mj_l1_done` (`way_used` deixado sem conexão — ver Limitação Conhecida #4 do `CLAUDE.md`).
5. `lru_l1_cache u_lru_l1` (`access_en=lru_l1_en`) → `lru_l1_hit`, `lru_l1_l2_needed`, `lru_l1_done` (`way_used` também sem conexão).
6. `mockingjay_l2_cache u_mj_l2` (`access_en=mj_l2_en`) → `mj_l2_hit`, `mj_l2_done` (`way_used` sem conexão).

Todas as três caches compartilham `clk`/`rst_n` do controller.

Validado por `tb_cache_top.v` (integração completa via `$readmemh`) e
`tb_edge_cases.v` (garante `result_valid` por exatamente 1 ciclo, FSM sempre
retorna a `IDLE`, relógio incrementa exatamente 1× por acesso, e
`policy_sel=0` mantém `mj_l1_en` sempre em 0).

---

------- cache_hierarchy_top.v -------

### Propósito

Comentário do próprio arquivo: *"Top sintetizável da hierarquia L1/L2 para
uso no Quartus. Wrapper sobre cache_controller com interface estilo
req_valid/done/busy."* Não é lógica de cache nova — é uma casca de adaptação
de protocolo, porque o `cache_controller` foi desenhado com uma interface
simples de simulação (`start`/`address`/`result_valid`), enquanto uma
ferramenta de síntese real costuma esperar um protocolo requisição/resposta.

### Conversão de reset

```verilog
wire rst_n;
assign rst_n = ~rst;
```

O wrapper recebe `rst` ativo-alto (convenção comum em fluxos Quartus) e
inverte para o `rst_n` ativo-baixo que todo o resto do design espera —
puramente combinacional.

### Geração do pulso `start` a partir de `req_valid`

```verilog
reg  req_valid_prev;
wire start;

always @(posedge clk) begin
    if (rst) req_valid_prev <= 1'b0;
    else     req_valid_prev <= req_valid;
end

assign start = req_valid & ~req_valid_prev;
```

Detector clássico de borda de subida: um registrador (`req_valid_prev`)
guarda o valor do ciclo anterior; `start` é `1` combinacionalmente só no
ciclo em que `req_valid` acabou de subir. Isso converte um sinal de nível
(`req_valid` pode ficar alto por vários ciclos, como em um handshake de
barramento típico) no pulso de exatamente 1 ciclo que `cache_controller.start`
exige (a FSM só reage a `start` estando em `IDLE`).

`req_pc` é recebido na porta mas **não é usado** em lugar nenhum do módulo —
comentário explícito no código: *"recebido mas não utilizado (Mockingjay não
usa PC)"*.

### Instância do controlador

```verilog
cache_controller u_ctrl (
    .clk(clk), .rst_n(rst_n), .start(start), .address(req_addr),
    .policy_sel(policy_sel), .result_valid(result_valid),
    .l1_hit_out(l1_hit_out), .l2_hit_out(l2_hit_out),
    .full_miss_out(full_miss_out), .state_debug(ctrl_state_debug)
);
```

### Estágio sequencial — `busy`/`done` e sinais de resposta

```verilog
always @(posedge clk) begin
    if (rst) begin
        done <= 0; busy <= 0;
        resp_l1_hit <= 0; resp_l1_miss <= 0;
        resp_l2_access <= 0; resp_l2_hit <= 0; resp_l2_miss <= 0;
    end else begin
        done <= 1'b0;                    // pulso de 1 ciclo
        if (start) busy <= 1'b1;
        if (result_valid) begin
            done <= 1'b1;
            busy <= 1'b0;
            resp_l1_hit    <= l1_hit_out;
            resp_l1_miss   <= ~l1_hit_out;
            resp_l2_access <= l2_hit_out | full_miss_out;
            resp_l2_hit    <= l2_hit_out;
            resp_l2_miss   <= full_miss_out;
        end
    end
end
```

`busy` sobe em `start` e desce quando `result_valid` chega, cobrindo toda a
janela em que um acesso está em andamento dentro da FSM interna. `done` é
zerado por padrão a cada ciclo e só sobe no ciclo em que `result_valid=1` —
outro pulso de 1 ciclo, alinhado ao do controller. `resp_l1_miss` é
simplesmente o complemento de `l1_hit_out` (não diferencia hit/miss de L2
depois); `resp_l2_access` sinaliza que a L2 foi de fato consultada.

### Estágio sequencial — acumuladores de estatísticas

```verilog
reg [31:0] r_l1_hit_count, r_l1_miss_count, r_l2_hit_count, r_l2_miss_count;

always @(posedge clk) begin
    if (rst) begin
        r_l1_hit_count <= 0; r_l1_miss_count <= 0;
        r_l2_hit_count <= 0; r_l2_miss_count <= 0;
    end else if (result_valid) begin
        if (l1_hit_out) r_l1_hit_count  <= r_l1_hit_count  + 32'd1;
        else            r_l1_miss_count <= r_l1_miss_count + 32'd1;

        if (l2_hit_out)         r_l2_hit_count  <= r_l2_hit_count  + 32'd1;
        else if (full_miss_out) r_l2_miss_count <= r_l2_miss_count + 32'd1;
    end
end
```

4 contadores de 32 bits, incrementados apenas quando `result_valid=1` (1
evento por acesso completo) — pensados para leitura posterior via
SignalTap depois de rodar vários acessos na FPGA. `l1_hit_count`/
`l1_miss_count` são mutuamente exclusivos e um dos dois sempre incrementa a
cada acesso. Já `l2_hit_count`/`l2_miss_count` só incrementam quando a L2 foi
de fato consultada (isto é, quando houve miss em L1) — um hit puro em L1 não
mexe em nenhum dos dois contadores de L2.

### Relação com outros módulos

Instancia `cache_controller` (`u_ctrl`), que por sua vez traz consigo toda a
hierarquia (decoders, contador, as 3 caches). É o único módulo do projeto
sem testbench próprio — foi validado indiretamente ao ser levado ao fluxo de
síntese do Quartus, o que revelou o problema de área documentado em
`sim/quartus_flow_report.md` (arrays de tags/estado sintetizados como
flip-flops individuais em vez de BRAM, estourando 110% dos Logic Elements da
Cyclone III EP3C25F324C6 — a lógica está correta, mas a estratégia de mapear
memória ainda precisa da diretiva `(* ramstyle="M9K" *)`).

---

## Nota final

Os gabaritos de hit/miss por trace, a árvore de decisão completa da FSM em
diagrama, as restrições de RTL exigidas pelo professor e as armadilhas
conhecidas já estão documentados com autoridade em `CLAUDE.md` (§1.2–§1.6) —
este guia não os repete, só explica a mecânica de sinal/ciclo que produz
esses resultados.
