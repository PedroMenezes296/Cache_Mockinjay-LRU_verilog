# Guia de Fluxo de Execução — ProjetoCache_Verilog

Os outros dois guias explicam o projeto de duas formas diferentes:
`GUIA_PROJETO.md` explica **o que cada arquivo faz**, em linguagem simples;
`GUIA_PROJETO_TECNICO.md` explica **como cada módulo funciona por dentro**,
sinal por sinal. Este documento aqui explica uma terceira coisa: **a linha do
tempo**. Não "o que o arquivo X faz", mas "o que acontece primeiro, o que
acontece depois, e o que acontece no ciclo de clock seguinte" — desde o
instante em que você manda rodar a simulação até o número final de
hits/misses aparecer na tela.

Vamos usar um exemplo real do projeto, com números reais (não inventados):
o trace `sim/traces_hex/trace_validacao.mem` rodando com a política
**Mockingjay**. No final deste documento os números batem exatamente com o
gabarito oficial do `CLAUDE.md` (§1.4): **L1: 3 hits / 5 misses**, **L2: 2
hits / 3 misses**.

---

## Parte 0 — De onde vêm os números "A", "B", "C"

O arquivo `sim/traces_hex/trace_validacao.mem` tem 8 linhas, cada uma um
endereço de memória de 32 bits em hexadecimal:

```
00000000
00000800
00000000
00000800
00001000
00000000
00000800
00001000
```

Para não ficar repetindo hexadecimal o tempo todo, vamos chamar
`0x00000000` de **A**, `0x00000800` de **B** e `0x00001000` de **C**. A
sequência do trace, então, é: **A B A B C A B C** (8 acessos).

---

## Parte 1 — Antes do primeiro ciclo de clock: como a simulação nasce

Isso tudo acontece **fora do hardware**, no mundo da simulação — é o
"palco" sendo montado antes da peça começar.

1. **Compilação.** Você roda `iverilog -o sim_out rtl/*.v tb/tb_cache_top.v`.
   O Icarus Verilog lê todos os arquivos `.v` e monta um único programa de
   simulação (`sim_out`). Nesse momento nada "roda" ainda — é só tradução de
   texto Verilog para um formato executável.

2. **Execução.** Você roda `vvp sim_out`. Agora a simulação começa de
   verdade, no "instante zero" do tempo simulado.

3. **O bloco `initial` do testbench dispara** (`tb/tb_cache_top.v`, dentro
   do módulo `tb_cache_top`). Um bloco `initial` em Verilog roda **uma única
   vez**, do começo ao fim, assim que a simulação começa — é o script mestre
   que comanda todo o teste. A primeira coisa que ele faz é `clk = 0`.

4. **O carregador de trace entra em ação** (`tb/tb_cache_top.v`, linhas 26 e 80):
   ```verilog
   reg [31:0] trace_mem [0:2047];
   ...
   $readmemh("sim/traces_hex/trace_validacao.mem", trace_mem);
   ```
   `$readmemh` é uma instrução **exclusiva de simulação** — ela não existe
   em hardware real, por isso só aparece em `tb/`, nunca em `rtl/`. Ela lê o
   arquivo de texto linha por linha e despeja cada valor hexadecimal dentro
   de um array `trace_mem` guardado na memória do simulador: `trace_mem[0] =
   A`, `trace_mem[1] = B`, `trace_mem[2] = A`, e assim por diante até
   `trace_mem[7] = C`. É o array de onde o testbench vai puxar cada endereço,
   um por vez.

5. **O gerador de clock começa a bater** (`tb/tb_cache_top.v`, linha 24):
   ```verilog
   always #5 clk = ~clk;
   ```
   Isso inverte `clk` a cada 5 unidades de tempo simulado — ou seja, um
   ciclo de clock completo dura 10 unidades (5 em nível baixo, 5 em nível
   alto). Daqui pra frente, tudo que descrevemos como "1 ciclo" corresponde a
   uma dessas subidas de `clk` (`posedge clk`).

6. **A task `run_trace` aplica o reset** (`tb/tb_cache_top.v`, linhas 36–38):
   ```verilog
   rst_n=0; start=0; policy_sel=pol;
   @(posedge clk); @(posedge clk); #1 rst_n=1;
   @(posedge clk);
   ```
   `rst_n=0` (reset ativo-baixo) fica sustentado por 2 ciclos de clock. Esse
   é o momento em que, **dentro do hardware de verdade**, todos os arrays de
   estado das 3 caches são zerados de uma vez: em `mockingjay_l1_cache`,
   `lru_l1_cache` e `mockingjay_l2_cache`, o bloco `if (!rst_n)` de cada um
   roda um `for` estático que zera `valid[]`, `tag_store[]`, `last_acc[]` e
   marca `interval[]` com o valor sentinela `4'hF` (15 — "intervalo
   desconhecido") em **todas** as posições, de uma só vez, no mesmo ciclo. A
   FSM do `cache_controller` também volta para `IDLE`. Depois disso,
   `rst_n=1` e a simulação está pronta para processar o primeiro acesso.

---

## Parte 2 — O ciclo de vida de UM acesso, ciclo por ciclo (mecanismo genérico)

Antes de entrar nos números do trace completo, vale entender o "esqueleto"
que se repete em **todo** acesso, sempre na mesma ordem. Vamos chamar o
ciclo em que a FSM está em `IDLE` esperando de **ciclo 0** (relativo àquele
acesso específico — cada acesso reinicia essa contagem).

**Ciclo 0 — `IDLE`, testbench prepara o pedido.** (`tb/tb_cache_top.v`, linhas 43–44)
```verilog
address = trace_mem[i];
@(posedge clk); #1 start=1;
```
O testbench escreve o endereço do trace na porta `address` do
`cache_controller` e, no ciclo seguinte, levanta `start=1` por exatamente 1
ciclo. Assim que `address` muda, **antes mesmo de qualquer clock**, os dois
`address_decoder` (um para L1, um para L2) já recalculam `set_l1`/`tag_l1` e
`set_l2`/`tag_l2` — são módulos puramente combinacionais (só `assign`, sem
`always @(posedge clk)`), então a resposta deles não espera ciclo nenhum,
só o tempo de propagação do sinal.

**Ciclo 1 — entrada em `L1_CHECK`.** No posedge em que `state==IDLE` e
`start==1`, a lógica de próximo estado decide `next_state = L1_CHECK`. No
mesmo posedge, o `cache_controller` dispara os pulsos de 1 ciclo (mecanismo
detalhado no `GUIA_PROJETO_TECNICO.md`, seção `cache_controller.v`) — trecho de
`rtl/cache_controller.v`, linhas 148–152:
```verilog
clk_enable <= 1'b1;
mj_l1_en   <= policy_sel;   // 1 se Mockingjay
lru_l1_en  <= ~policy_sel;  // 1 se LRU
```
A partir do início do ciclo 1: o `saturating_counter_4bit` (`global_time`)
recebe `enable=1` e vai incrementar no **próximo** posedge; a cache L1 ativa
(`mockingjay_l1_cache` ou `lru_l1_cache`, dependendo de `policy_sel`) recebe
`access_en=1` e começa a processar o acesso.

**Dentro do ciclo 1 — a cadeia combinacional da cache L1 resolve tudo antes
do próximo clock.** Isso é o coração do módulo: nenhuma dessas etapas espera
um `posedge` separado, é tudo lógica combinacional encadeada, resolvida
dentro do mesmo ciclo:
1. Os comparadores de tag da via 0 e via 1 rodam **em paralelo**
   (`hit_way0`, `hit_way1`) → decidem `l1_hit`.
2. Se for Mockingjay: os dois `etr_calculator` (um por via) também já
   calcularam `etr0`/`etr1`/`neg0`/`neg1` a partir do `last_acc`/`interval`
   armazenados e do `global_time` atual — em paralelo com os comparadores de
   tag, não depois.
3. `eff0`/`eff1` aplicam a regra do ETR negativo (satura em 31 se
   "atrasado").
4. O MUX de vítima (`victim_way`) já sabe, ainda dentro do mesmo ciclo, qual
   via seria expulsa **se** for miss — mesmo que o resultado final seja hit
   (o cálculo roda sempre, só é usado se precisar).

**Ciclo 2 — `done` sobe, FSM decide o próximo passo.** No posedge seguinte,
o `always @(posedge clk)` da cache L1 grava o resultado (`hit<=`,
`l2_access_needed<=`, e se Mockingjay também atualiza `interval`/`last_acc`)
e sobe `done<=1`. A FSM lê `l1_done=1` e bifurca:
- Se `l1_hit=1` → `next_state = L1_HIT` → ciclo seguinte vai direto para
  `OUTPUT`.
- Se `l1_hit=0` → `next_state = L1_MISS_L2_CHECK` → precisa consultar a L2.

**Se houve miss em L1 — mesma mecânica se repete para a L2.** Ao entrar em
`L1_MISS_L2_CHECK` (vindo de `L1_CHECK`), o controller pulsa `mj_l2_en=1`
por 1 ciclo. Dentro desse ciclo, a `mockingjay_l2_cache` roda os **8**
comparadores de tag em paralelo, os **8** `etr_calculator` em paralelo, e a
**árvore de comparadores de 3 níveis** (8→4→2→1) decide a vítima entre as 8
vias — tudo isso também resolvido dentro de um único ciclo de clock, porque
é lógica combinacional em cascata, não uma sequência de estados. No ciclo
seguinte, `mj_l2_done` sobe e a FSM bifurca entre `L2_HIT` e `L2_MISS`.

**Estado `OUTPUT` — o resultado fica visível por exatamente 1 ciclo.**
Não importa se veio de `L1_HIT`, `L2_HIT` ou `L2_MISS`, todos convergem
incondicionalmente para `OUTPUT`. Nesse ciclo (`rtl/cache_controller.v`,
linhas 157–161):
```verilog
result_valid  <= 1'b1;
l1_hit_out    <= (state == L1_HIT);
l2_hit_out    <= (state == L2_HIT);
full_miss_out <= (state == L2_MISS);
```
O testbench está literalmente parado num `wait(result_valid == 1'b1);`
esperando esse momento — assim que ele detecta `result_valid=1`, lê
`l1_hit_out`/`l2_hit_out` e imprime a linha de resultado daquele acesso
(`[N] 0xENDERECO → L1 HIT`, por exemplo).

**Volta a `IDLE`.** No próximo posedge, `next_state=IDLE` incondicionalmente,
e a FSM está pronta para o testbench escrever o próximo endereço e repetir
tudo — reiniciando a contagem de "ciclo 0" descrita acima.

Resumindo o número de ciclos: um **hit em L1** resolve em ~3 ciclos
(`IDLE→L1_CHECK→L1_HIT→OUTPUT`); um acesso que precisa ir até a L2 leva mais
ciclos (`IDLE→L1_CHECK→L1_MISS_L2_CHECK→L2_HIT/L2_MISS→OUTPUT`) — é
justamente essa diferença de latência que o `duvidas_projeto.md` estima em
"~5 ciclos" para hit de L1 e "~7 ciclos" para acesso à L2.

---

## Parte 3 — O trace completo, acesso por acesso, com os números reais

Agora vamos rodar o mecanismo da Parte 2 para os 8 acessos de verdade,
política **Mockingjay** (`policy_sel=1`). Lembre-se: o relógio global
(`global_time`) incrementa 1 vez por acesso completo, então o acesso número
`i` (contando a partir de 1) usa `global_time = i - 1`.

### Acesso 1 — endereço A (`0x00000000`), global_time = 0

**Decodificação de endereço.** `A` em binário é só zeros. O
`address_decoder` fatia:
- L1 (`addr[10:5]`=set, `addr[31:11]`=tag): **set=0, tag=0**.
- L2 (`addr[11:6]`=set, `addr[31:12]`=tag): **set=0, tag=0**.

**L1.** As duas vias do conjunto 0 estão vazias (`valid[0][0]=0`,
`valid[1][0]=0`, por causa do reset). `hit_way0=0`, `hit_way1=0` →
**MISS**. Como via 0 está vazia (`empty0=1`), o MUX de vítima escolhe a via
0 sem nem precisar calcular ETR. A cache instala: `valid[0][0]<=1`,
`tag_store[0][0]<=0`, `last_acc[0][0]<=0`, `interval[0][0]<=4'hF` (bloco
novo, intervalo "desconhecido").

**L2 (acionada, pois L1 deu miss).** Mesmo raciocínio: conjunto 0 todo
vazio → **MISS** → instala via 0 do conjunto 0 com `tag=0`,
`last_acc=0`, `interval=4'hF`.

**Resultado:** `[1] 0xA → L1 MISS | L2 MISS`

---

### Acesso 2 — endereço B (`0x00000800`), global_time = 1

**Decodificação de endereço.** `B = 0x800`, que em binário é só o bit 11
ligado. Aqui está um detalhe importante que diferencia L1 de L2:
- L1: o campo de índice é `addr[10:5]` — o bit 11 fica **fora** dessa
  janela, então **set=0** ainda. O campo de tag é `addr[31:11]`, e o bit 11
  é justamente o bit menos significativo dessa janela → **tag=1**.
- L2: o campo de índice é `addr[11:6]` — agora o bit 11 **entra** nessa
  janela (é o bit mais significativo dela) → **set=32**. O campo de tag é
  `addr[31:12]`, que não inclui o bit 11 → **tag=0**.

Ou seja: **na L1, A e B caem no mesmo conjunto** (só a tag diferencia);
**na L2, A e B caem em conjuntos diferentes** (set 0 vs. set 32) — porque o
bloco da L2 é maior (64 B em vez de 32 B), consumindo 1 bit a mais de
offset, o que empurra o bit 11 do campo de tag para o campo de índice. Essa
diferença vai ser importante lá no acesso 7.

**L1 (conjunto 0, mesmo conjunto de A).** Via 0 já tem A (tag=0); comparando
com `tag_in=1` (B) → `hit_way0=0`. Via 1 está vazia → `hit_way1=0` →
**MISS**. `empty1=1`, então a vítima é a via 1 (sem precisar de ETR).
Instala: `valid[1][0]<=1`, `tag_store[1][0]<=1`, `last_acc[1][0]<=1`,
`interval[1][0]<=4'hF`.

**L2 (conjunto 32 — vazio, primeira vez que esse conjunto é tocado).**
**MISS** → instala via 0 do conjunto 32: `tag=0`, `last_acc=1`,
`interval=4'hF`.

**Resultado:** `[2] 0xB → L1 MISS | L2 MISS`

---

### Acesso 3 — endereço A de novo, global_time = 2

**Decodificação:** L1 set=0/tag=0 (igual ao acesso 1).

**L1.** Via 0 tem `tag_store[0][0]=0`, bate com `tag_in=0` → `hit_way0=1` →
**HIT** na via 0. Isso dispara o "aprendizado" de intervalo:
```
learned_full = global_time(2) - last_acc[0][0](0) = 2
```
Como 2 não passa de 15, não satura: `learned=2`. No próximo posedge, a
cache grava `interval[0][0]<=2` e `last_acc[0][0]<=2` — agora a cache
"acredita" que blocos como A costumam ser reacessados a cada 2 tiques do
relógio.

**L2 não é acionada** (L1 já resolveu com hit).

**Resultado:** `[3] 0xA → L1 HIT`

---

### Acesso 4 — endereço B de novo, global_time = 3

**L1.** Via 1 tem `tag_store[1][0]=1`, bate com `tag_in=1` (B) →
`hit_way1=1` → **HIT** na via 1.
```
learned_full = global_time(3) - last_acc[1][0](1) = 2 → learned=2
```
Grava `interval[1][0]<=2`, `last_acc[1][0]<=3`.

**Resultado:** `[4] 0xB → L1 HIT`

Neste ponto o estado da L1 (conjunto 0) é: via 0 = A (`last_acc=2,
interval=2`), via 1 = B (`last_acc=3, interval=2`).

---

### Acesso 5 — endereço C (`0x00001000`), global_time = 4 — **a decisão que separa Mockingjay de LRU**

**Decodificação de endereço.** `C = 0x1000`, bit 12 ligado.
- L1: bit 12 cai dentro do campo de tag (`addr[31:11]`) → **set=0** (igual a
  A e B), **tag=2**.
- L2: bit 12 cai dentro do campo de tag da L2 também (`addr[31:12]` começa
  exatamente no bit 12) → **set=0**, **tag=1**.

**L1.** `tag_in=2` não bate com a via 0 (tag=0) nem com a via 1 (tag=1) →
**MISS**. As duas vias estão ocupadas (`empty0=0`, `empty1=0`), então agora
sim entra a comparação de ETR — este é o cálculo que decide quem sai:

*Via 0 (A):* `last_acc=2`, `interval=2`, `current_time=4`.
`sum = 2+2 = 4`. `etr = sum - current_time = 4-4 = 0`.
`etr_negative = (sum < current_time) = (4<4) = falso`.
→ `eff0 = etr0 = 0` (**não** vira 31, porque ETR=0 não conta como negativo —
essa é a regra "ETR=0 é protegido" documentada em `etr_calculator.v` e
`CLAUDE.md`).

*Via 1 (B):* `last_acc=3`, `interval=2`, `current_time=4`.
`sum = 3+2 = 5`. `etr = 5-4 = 1`. `etr_negative = (5<4) = falso`.
→ `eff1 = 1`.

**Comparação:** `victim = (eff0 >= eff1) ? via0 : via1` → `0 >= 1` é falso →
**vítima = via 1 (B)**. Em palavras simples: a cache acredita que A vai ser
reusado "agora mesmo" (ETR=0, protegido), enquanto B só deve ser reusado
daqui a 1 tique — como a cache precisa abrir espaço para C, ela escolhe
sacrificar o bloco que parece menos urgente (B), preservando A. **Um LRU
puro, nesse mesmo instante, expulsaria A** (porque A foi acessado por
último no acesso 3, mais cedo que B no acesso 4) — essa é exatamente a
diferença de comportamento que o projeto quer demonstrar.

Instala C na via 1: `valid[1][0]<=1`, `tag_store[1][0]<=2`,
`last_acc[1][0]<=4`, `interval[1][0]<=4'hF`.

**L2 (acionada, pois L1 deu miss).** `set=0, tag=1`. O conjunto 0 da L2 só
tem a via 0 ocupada (A, do acesso 1); `tag_in=1` não bate → **MISS**. Via 1
está vazia → instala ali: `tag_store[1][set0]<=1`, `last_acc<=4`,
`interval<=4'hF`.

**Resultado:** `[5] 0xC → L1 MISS | L2 MISS`

---

### Acesso 6 — endereço A de novo, global_time = 5 — **o resultado da decisão do acesso 5**

**L1.** Via 0 ainda guarda A (`tag=0`) — não foi tocada no acesso 5.
`hit_way0=1` → **HIT**. Se o vitimado no acesso 5 tivesse sido A (como um
LRU teria feito), este acesso seria um MISS. É este HIT que garante o 3º
acerto do Mockingjay no trace.
```
learned_full = global_time(5) - last_acc[0][0](2) = 3 → learned=3
```
Grava `interval[0][0]<=3`, `last_acc[0][0]<=5`.

**Resultado:** `[6] 0xA → L1 HIT`

---

### Acesso 7 — endereço B de novo, global_time = 6 — **segunda disputa de vítima**

**L1.** Estado atual do conjunto 0: via 0 = A (`tag=0`), via 1 = C
(`tag=2`, instalado no acesso 5). `tag_in=1` (B) não bate com nenhuma das
duas → **MISS**. Ambas ocupadas → decide por ETR:

*Via 0 (A):* `last_acc=5`, `interval=3`, `current_time=6`.
`sum=5+3=8`. `etr=8-6=2`. `etr_negative=(8<6)=falso` → `eff0=2`.

*Via 1 (C):* `last_acc=4`, `interval=4'hF (15, "desconhecido" — C nunca
teve um hit para aprender um intervalo real)`, `current_time=6`.
`sum=4+15=19`. `etr=19-6=13`. `etr_negative=(19<6)=falso` → `eff1=13`.

**Comparação:** `eff0(2) >= eff1(13)`? Não → **vítima = via 1 (C)**. Em
palavras simples: C nunca voltou a ser acessado desde que entrou (acesso 5),
então seu intervalo continua no valor "desconhecido" máximo, o que faz sua
estimativa de ETR disparar para 13 — um bloco novo que não é reacessado
rápido vira o primeiro candidato a sair. B expulsa C.

Instala B na via 1: `tag_store[1][0]<=1`, `last_acc[1][0]<=6`,
`interval[1][0]<=4'hF`.

**L2 (acionada).** `set=32, tag=0` — **o mesmo conjunto tocado no acesso 2**
(lembra do detalhe do bit 11?). A via 0 do conjunto 32 ainda guarda B
(`tag=0`, instalado no acesso 2, nunca mais mexido desde então). `tag_in=0`
bate → **HIT**! Isso só acontece porque a L2 usa 64 conjuntos endereçados de
forma diferente da L1 — o estado de B ficou "estacionado" ali desde o
acesso 2, intocado, esperando esse momento.
```
learned_full = global_time(6) - last_acc[0][set32](1) = 5 → learned=5
```
Grava `interval[0][set32]<=5`, `last_acc[0][set32]<=6`.

**Resultado:** `[7] 0xB → L1 MISS | L2 HIT`

---

### Acesso 8 — endereço C de novo, global_time = 7

**L1.** Conjunto 0 agora: via 0 = A (`tag=0`), via 1 = B (`tag=1`, acabou de
entrar no acesso 7). `tag_in=2` (C) não bate com nenhuma das duas →
**MISS** (nem precisa olhar ETR para saber que é miss — é a comparação de
tag que decide isso, o ETR só decide **qual via** sai, não **se** é hit).

**L2.** `set=0, tag=1`. O conjunto 0 da L2 tem: via 0 = A (`tag=0`, do
acesso 1), via 1 = C (`tag=1`, instalada no acesso 5, nunca mais tocada).
`tag_in=1` bate com a via 1 → **HIT**.

**Resultado:** `[8] 0xC → L1 MISS | L2 HIT`

---

## Parte 4 — Fechando as contas

| # | End. | L1 | L2 |
|---|------|----|----|
| 1 | A | MISS | MISS |
| 2 | B | MISS | MISS |
| 3 | A | HIT | — |
| 4 | B | HIT | — |
| 5 | C | MISS | MISS |
| 6 | A | HIT | — |
| 7 | B | MISS | HIT |
| 8 | C | MISS | HIT |

**L1: 3 hits (acessos 3, 4, 6) / 5 misses (1, 2, 5, 7, 8) → 37,5%.**
**L2: 2 hits (acessos 7, 8) / 3 misses (1, 2, 5) → 40%** (só entre os 5
acessos que efetivamente chegaram até a L2, já que L2 só é consultada
quando L1 erra).

Esses números batem exatamente com o gabarito oficial documentado em
`CLAUDE.md` (§1.4) e `sim/validation_report.md`, e com a sequência de
hit/miss `M M H H M H M M` citada lá.

O mesmo mecanismo — FSM, decodificação de bits, comparadores paralelos,
pulsos de 1 ciclo — vale para a política **LRU** (só muda a regra de
escolha da vítima: idade em vez de ETR) e para o trace
`trace_mixed_hotset.mem` (mesmos 7 primeiros acessos, 8º acesso diferente).
Para o detalhe sinal-a-sinal de cada módulo usado nesse fluxo, veja
`GUIA_PROJETO_TECNICO.md`; para a visão geral de cada arquivo, veja
`GUIA_PROJETO.md`.
