# Guia do Projeto — ProjetoCache_Verilog

Este documento explica, arquivo por arquivo, o que existe nas pastas `rtl/`,
`tb/` e `sim/` do projeto. A ideia é servir de material de apoio para a
apresentação ao professor: cada módulo Verilog vem seguido do seu testbench,
com o resultado esperado ao rodar sozinho no Icarus Verilog e o comando exato
para reproduzir.

Todos os números de hit/miss citados aqui são os **corrigidos e validados**
(ver `sim/validation_report.md`) — não os números antigos que ainda aparecem
no `README.md` (mais detalhes na última seção deste guia).

Todos os comandos abaixo devem ser rodados **a partir da raiz do repositório**
(`ProjetoCache_Verilog/`), porque os testbenches de integração usam
`$readmemh` com caminho relativo à raiz.

---

## Parte 1 — Pasta `rtl/` (o hardware em si)

Esses são os arquivos que descrevem o circuito de verdade — o que, no fim,
seria gravado na FPGA. Nenhum deles usa `$display`, `#delay` ou `initial`,
porque essas construções não existem em hardware físico; elas só servem para
simulação.

------- address_decoder.v -------

Esse é o "separador de endereço". Todo acesso à cache começa com um endereço
de 32 bits (o número que o processador manda perguntando "eu quero o dado que
está guardado aqui"). Só que a cache não usa esse número inteiro de uma vez:
ela precisa quebrá-lo em três pedaços — o **offset** (posição dentro do
bloco, que a gente nem usa aqui porque não guardamos dado, só a etiqueta),
o **index** (em qual "gaveta"/conjunto da cache esse endereço deveria estar) e
a **tag** (a etiqueta que identifica exatamente qual endereço está guardado
naquela gaveta). Esse módulo faz esse corte com simples fatiamento de bits —
é puramente combinacional, ou seja, o resultado sai instantaneamente, sem
esperar nenhum pulso de clock. Ele é parametrizado, então o mesmo arquivo
serve tanto para a L1 (blocos de 32 bytes) quanto para a L2 (blocos de 64
bytes) — só muda o parâmetro de quantos bits são offset.

------- tb_address_decoder.v -------

Esse testbench aplica três endereços de exemplo (`0x0000`, `0x0800`,
`0x1000` — que são exatamente os endereços A, B e C usados nos traces de
validação) e confere se o decodificador extraiu o `set_index` e a `tag`
certos, tanto na configuração de L1 quanto na de L2. São 6 checagens no
total (3 para L1 + 3 para L2).

Resultado esperado ao rodar sozinho: 6 linhas "PASSOU" (`L1 PASSOU ...` ×3 e
`L2 PASSOU ...` ×3), nenhuma linha "FALHOU".

Por que esse resultado: os três endereços testados caem sempre no mesmo
conjunto (`set=0`), mas cada um tem uma tag diferente (0, 1, 2) — é
exatamente esse comportamento que faz a cache reconhecer A, B e C como blocos
distintos guardados no mesmo lugar.

Comando para rodar sozinho:
```
iverilog -o tb_dec rtl/address_decoder.v tb/tb_address_decoder.v && vvp tb_dec
```

---

------- saturating_counter_4bit.v -------

Esse é o "relógio global" da cache — o contador que substitui a variável
`int relogio_global` do simulador em C original. Só que, em vez de um inteiro
gigante, aqui ele é um contador de apenas 4 bits, então vai de 0 até 15. A
diferença importante é que ele **não estoura**: ao chegar em 15, ele trava
ali (satura) em vez de voltar para 0, porque um "relógio" que reseta sozinho
bagunçaria todo o cálculo de ETR do Mockingjay. Ele também aceita uma carga
forçada de valor (`load_val`/`load_en`), usada em testes, embora no projeto
real o `cache_controller` nunca use essa carga — só o incremento normal, um
tique por acesso à cache.

------- tb_saturating_counter.v -------

Esse testbench faz três verificações: (1) incrementa o contador 20 vezes
seguidas e confere que ele parou em 15 em vez de dar a volta; (2) testa a
carga forçada (`load_val=7`) e confere que o valor foi assumido; (3)
incrementa de novo a partir de 7 e confere que ele volta a saturar em 15.

Resultado esperado ao rodar sozinho: uma linha de progresso por ciclo
(`Ciclo 1: count=1` até `Ciclo 20: count=15`), seguida de três linhas
"PASSOU" (saturação em 15, load OK, re-saturação a partir de 7 OK).

Por que esse resultado: o contador é de 4 bits, então o valor máximo
representável é 15 (`4'b1111`) — o teste existe justamente para garantir que
o hardware nunca "vira" para 0 quando devia continuar em 15, o que quebraria
todos os cálculos de ETR feitos depois desse ponto.

Comando para rodar sozinho:
```
iverilog -o tb_sat rtl/saturating_counter_4bit.v tb/tb_saturating_counter.v && vvp tb_sat
```

---

------- etr_calculator.v -------

Esse é o coração matemático do algoritmo Mockingjay: o módulo que calcula o
ETR ("Estimated Time of Reuse" — tempo estimado até o bloco ser usado de
novo). A fórmula é simples: `ETR = (último_acesso + intervalo_previsto) −
tempo_atual`. Se o ETR for um número alto, quer dizer que o bloco só vai ser
reusado daqui a muito tempo — logo, é um bom candidato a ser expulso da
cache quando precisar de espaço. Um detalhe crucial (e que já causou um bug
real no projeto, ver `sim/validation_report.md`): se o ETR der **exatamente
zero**, o bloco **não** é considerado atrasado — ele continua protegido. Só
quando o ETR é **estritamente negativo** é que o bloco é tratado como
"máximo atraso possível" (valor 31) e vira candidato a despejo. Essa regra
espelha exatamente o `if (etr < 0)` do simulador em C original, que é a
referência oficial do projeto.

------- tb_etr_calculator.v -------

Esse testbench cobre os quatro casos importantes da fórmula: um ETR
estritamente negativo (deve ser sinalizado como negativo), um ETR positivo
normal, um ETR **igual a zero** (o caso delicado — não pode ser sinalizado
como negativo) e um caso com intervalo máximo (15) para checar que a soma
não estoura incorretamente nos 5 bits do resultado.

Resultado esperado ao rodar sozinho: 4 linhas "PASSOU", nenhuma "FALHOU".

Por que esse resultado: o terceiro caso (`last=3, interval=2, time=5`) dá
soma 5 e tempo atual 5, ou seja, ETR = 0 — o teste confere que
`etr_negative` fica em 0 (protegido) e não em 1. É exatamente esse
comportamento que, no trace de validação, salva o bloco A da expulsão no
acesso 5.

Comando para rodar sozinho:
```
iverilog -o tb_etr rtl/etr_calculator.v tb/tb_etr_calculator.v && vvp tb_etr
```

---

------- lru_l1_cache.v -------

Essa é a cache L1 (a "gaveta" mais próxima do processador) rodando com a
política **LRU** — o algoritmo clássico que sempre expulsa o bloco que não é
usado há mais tempo. Ela tem 2 vias (2 "slots" por conjunto), então o estado
de "quem é o menos recentemente usado" cabe em apenas 1 bit por conjunto:
`lru_bit=0` significa "a via 0 é a mais velha, expulse ela primeiro";
`lru_bit=1` significa o contrário. As duas vias são comparadas em paralelo,
usando `wire`s combinacionais em vez de um laço `for` — isso é uma exigência
do professor para que a lógica de comparação de vias vire hardware real (um
laço `for` em RTL descreveria replicação de circuito, não decisão em tempo de
execução). Essa cache existe principalmente como "baseline de comparação"
contra o Mockingjay: mesma interface, algoritmo mais simples.

------- tb_lru_l1.v -------

Esse testbench roda o `trace_validacao` inteiro (8 acessos: A B A B C A B C)
direto na cache LRU isolada, contando hits e misses.

Resultado esperado ao rodar sozinho: sequência `MISS MISS HIT HIT MISS MISS
MISS MISS`, terminando em "Hits: 2 | Misses: 6 | Hit Rate: 25.0%" e
"RESULTADO: CORRETO".

Por que esse resultado: no acesso 5, quando C chega e a cache (só 2 vias)
está cheia com A e B, o LRU expulsa A (que foi acessado por último no acesso
3, mais cedo que B no acesso 4). Isso significa que no acesso 6, quando A é
pedido de novo, ele já não está mais lá — vira MISS. É exatamente esse erro
de julgamento do LRU que o Mockingjay evita (compare com o próximo módulo).

Comando para rodar sozinho:
```
iverilog -o tb_lru rtl/lru_l1_cache.v tb/tb_lru_l1.v && vvp tb_lru
```

---

------- mockingjay_l1_cache.v -------

Essa é a cache L1 rodando com o algoritmo **Mockingjay**, desenvolvido pelo
grupo — a peça central do projeto. Em vez de olhar só "quem foi usado por
último" (como o LRU), ela tenta **prever o futuro**: para cada via, calcula o
ETR (usando o módulo `etr_calculator`, instanciado duas vezes em paralelo,
uma por via) e expulsa a via com o **maior** ETR — ou seja, a que a cache
acredita que vai demorar mais para ser reusada. Um MUX combinacional decide a
vítima entre as duas vias sem usar laço `for`. Quando dá HIT em um bloco, a
cache "aprende": calcula `intervalo = tempo_atual − último_acesso` e guarda
esse intervalo para usar no próximo cálculo de ETR — é assim que ela detecta
padrões repetidos. Quando um bloco é novo (acabou de entrar via MISS), o
intervalo é marcado como "desconhecido" (`4'hF`, o valor máximo em 4 bits),
o que faz esse bloco novo ter ETR alto e virar candidato a expulsão rápida
se não for reacessado logo.

------- tb_mockingjay_l1.v -------

Mesmo trace do teste anterior (`trace_validacao`: A B A B C A B C), mas agora
na cache Mockingjay, para comparar diretamente contra o resultado do LRU.

Resultado esperado ao rodar sozinho: sequência `MISS MISS HIT HIT MISS HIT
MISS MISS`, terminando em "Hits: 3 | Misses: 5 | Hit Rate: 37.5%" e
"RESULTADO: CORRETO - bate com o simulador C (e 3 > 2 do LRU)".

Por que esse resultado: no acesso 5 (C chega, cache cheia com A e B), o
Mockingjay calcula ETR_A=0 (protegido, porque ETR=0 não conta como negativo)
e ETR_B=1 — logo expulsa **B**, não A. Isso significa que no acesso 6, A
ainda está na cache → HIT, onde o LRU tinha dado MISS. É essa diferença (3
hits contra 2 hits do LRU, no mesmo trace) que demonstra a vantagem prática
do algoritmo do grupo.

Comando para rodar sozinho:
```
iverilog -o tb_mj rtl/etr_calculator.v rtl/mockingjay_l1_cache.v tb/tb_mockingjay_l1.v && vvp tb_mj
```

---

------- mockingjay_l2_cache.v -------

Essa é a cache L2 — maior (8 vias em vez de 2) e só acessada quando a L1 já
deu miss. Usa a mesma ideia do Mockingjay (ETR), só que agora com 8
calculadores de ETR rodando em paralelo, um por via. O desafio aqui é achar
"o maior ETR entre 8 valores" sem usar um laço `for` — a solução é uma
**árvore de comparadores de 3 níveis**: no primeiro nível, 4 comparações
acontecem ao mesmo tempo (via0 vs via1, via2 vs via3, via4 vs via5, via6 vs
via7); no segundo nível, os 4 vencedores viram 2 comparações; no terceiro
nível, sobra 1 comparação final que decide a vítima. Isso é literalmente como
um chaveamento de campeonato esportivo, só que todo em um único ciclo de
clock, porque é tudo lógica combinacional.

------- tb_mockingjay_l2.v -------

Esse testbench é independente dos traces A/B/C — ele testa a L2 isoladamente
com um cenário controlado: enche as 8 vias de um conjunto (tags 0 a 7, nos
tempos 1 a 8), confere um HIT que "ensina" um intervalo, depois força um
MISS com a cache cheia e verifica que a vítima escolhida é exatamente a via
com maior ETR calculado à mão nos comentários do arquivo. Também confere que
conjuntos diferentes são independentes entre si.

Resultado esperado ao rodar sozinho: uma sequência de linhas "PASSOU" (uma
por etapa: 8 preenchimentos, 1 hit com intervalo aprendido, 1 miss com
expulsão da via correta, confirmações de que a via expulsa virou miss e a
que ficou continua hit, e o teste do conjunto independente), terminando em
"=== TB_MOCKINGJAY_L2: 0 erro(s) ===" e "RESULTADO: CORRETO".

Por que esse resultado: depois de preencher as 8 vias e fazer um HIT na via 0
(que aprende intervalo=8), a via 7 é a que tem o maior ETR calculado (13,
porque foi a última a ser tocada e ainda tem intervalo "desconhecido"=15) —
por isso é ela que a árvore de comparadores escolhe para expulsão quando um
9º bloco (tag 8) chega.

Comando para rodar sozinho:
```
iverilog -o tb_l2 rtl/etr_calculator.v rtl/mockingjay_l2_cache.v tb/tb_mockingjay_l2.v && vvp tb_l2
```

---

------- cache_controller.v -------

Esse é o "maestro" do projeto — a máquina de estados finitos (FSM) que
orquestra tudo: recebe um endereço, decide se consulta a L1 com LRU ou
Mockingjay (via o sinal `policy_sel`: 0 = LRU, 1 = Mockingjay), aciona a L2
só se a L1 der miss, e no final sinaliza o resultado (`l1_hit_out`,
`l2_hit_out`, `full_miss_out`) por exatamente 1 ciclo de clock através do
sinal `result_valid`. Por dentro, ele instancia todos os outros módulos:
os dois decodificadores de endereço (um para L1, um para L2), o relógio
global, a cache L1 Mockingjay, a cache L1 LRU e a cache L2 — e usa MUXes para
escolher, a cada acesso, se os resultados vêm da via LRU ou da via
Mockingjay. Um detalhe de projeto sutil e importante: os sinais que "ligam"
cada cache (`mj_l1_en`, `lru_l1_en`, etc.) são pulsos de **um único ciclo**,
disparados só na entrada de cada estado — sem essa proteção, a cache
executaria cada acesso duas vezes e o relógio global andaria dois tiques por
acesso em vez de um só (esse foi, inclusive, um bug real encontrado e
corrigido durante a validação, documentado em `sim/validation_report.md`).

Fluxo de estados: `IDLE → L1_CHECK → (hit? L1_HIT : L1_MISS_L2_CHECK →
(hit? L2_HIT : L2_MISS)) → OUTPUT → IDLE`.

------- tb_cache_top.v -------

Esse é o testbench de integração completa — o mais importante para
demonstrar o projeto funcionando de ponta a ponta. Ele carrega os arquivos de
trace (`sim/traces_hex/*.mem`) usando `$readmemh`, injeta um endereço de
cada vez no `cache_controller` (esperando o `result_valid` subir a cada
acesso, exatamente como um processador real faria) e no final imprime as
estatísticas de hit/miss de L1 e L2, para comparar diretamente com o
gabarito do simulador C. Ele roda três cenários seguidos: `trace_validacao`
com Mockingjay, `trace_validacao` com LRU, e `trace_mixed_hotset` com
Mockingjay.

Resultado esperado ao rodar sozinho: uma linha por acesso (ex.: `[1]
0x00000000 → L1 MISS | L2 MISS`, `[3] 0x00000000 → L1 HIT`), seguida de um
resumo por cenário:

| Cenário | L1 Hits/Misses | Taxa L1 | L2 Hits/Misses | Taxa L2 |
|---|---|---|---|---|
| trace_validacao — MOCKINGJAY | 3 / 5 | 37.5% | 2 / 3 | 40.0% |
| trace_validacao — LRU | 2 / 6 | 25.0% | 3 / 3 | 100.0% |
| trace_mixed_hotset — MOCKINGJAY | 4 / 4 | 50.0% | 1 / 3 | 25.0% |

Por que esse resultado: esses números batem exatamente com o simulador em C
de referência (a fonte de verdade do projeto) — é essa correspondência exata
que comprova que o hardware Verilog reproduz fielmente o comportamento do
algoritmo original, e não apenas "parece certo".

Comando para rodar sozinho:
```
iverilog -o sim_out rtl/address_decoder.v rtl/saturating_counter_4bit.v \
  rtl/etr_calculator.v rtl/mockingjay_l1_cache.v rtl/lru_l1_cache.v \
  rtl/mockingjay_l2_cache.v rtl/cache_controller.v tb/tb_cache_top.v
vvp sim_out
```

------- tb_edge_cases.v -------

Esse testbench não segue nenhum trace — ele existe para cobrir situações
"raras" que os traces curtos de 8 acessos não exercitam sozinhos: por
exemplo, garantir que uma via com a flag `valid=0` nunca dá um hit
"fantasma" mesmo se a tag coincidir por acaso com zero; garantir que dois
acessos seguidos ao mesmo endereço dão miss-depois-hit corretamente; garantir
que um reset no meio de uma operação limpa tudo (nenhum estado "preso" pela
metade); garantir que sem `access_en` o sinal `done` nunca sobe sozinho; e
garantir que o relógio de 4 bits, mesmo saturado em 15, continua funcionando
sem causar hits ou misses incorretos. A segunda metade do arquivo testa o
`cache_controller` diretamente: confere que `result_valid` fica alto por
exatamente 1 ciclo, que a FSM sempre volta para `IDLE`, que o relógio global
incrementa exatamente uma vez por acesso, e que com `policy_sel=0` a via
Mockingjay realmente fica desligada (`mj_l1_en` nunca sobe).

Resultado esperado ao rodar sozinho: uma sequência de linhas "PASSOU"
(nenhuma "FALHOU"), terminando em "=== TB_EDGE_CASES: 0 erro(s) ===" e
"RESULTADO: CORRETO".

Por que esse resultado: cada verificação aqui corresponde a um bug em
potencial que já foi caçado deliberadamente (dois deles — o ETR=0 e o pulso
duplo de enable — eram bugs reais encontrados durante a validação); o
testbench passar limpo é a evidência de que essas classes de erro foram
eliminadas do RTL.

Comando para rodar sozinho:
```
iverilog -o tb_edge rtl/*.v tb/tb_edge_cases.v && vvp tb_edge
```

---

------- cache_hierarchy_top.v -------

Esse arquivo não tem testbench próprio — ele não é sobre lógica de cache
nova, é um **wrapper** (uma "casca" de adaptação) construído especificamente
para ser o módulo top-level entregue ao Quartus (a ferramenta que sintetiza
o design para a FPGA de verdade). O `cache_controller` foi desenhado com uma
interface simples de simulação (`start`/`address`/`result_valid`), mas uma
ferramenta de síntese real geralmente espera um protocolo do tipo
requisição/resposta (`req_valid`/`busy`/`done`). Esse wrapper faz três
coisas: (1) converte o reset de ativo-alto (`rst`, comum em fluxos de
síntese) para o ativo-baixo (`rst_n`) que o `cache_controller` espera; (2)
detecta a borda de subida em `req_valid` e gera o pulso de `start` de exatamente
1 ciclo que o controller precisa; (3) acumula contadores de 32 bits de
hits/misses de L1 e L2 ao longo do tempo, para poder ler as estatísticas
depois de rodar vários acessos na FPGA (via SignalTap, por exemplo). Foi
justamente esse módulo, ao ser sintetizado, que revelou o problema de área
documentado em `sim/quartus_flow_report.md`: o Quartus tentou implementar os
arrays de tags/estado das caches como flip-flops individuais em vez de
blocos de memória (BRAM) do chip, estourando 110% dos elementos lógicos
disponíveis na Cyclone III EP3C25F324C6. Ou seja — a lógica está correta (a
simulação prova isso), mas a estratégia de mapear a memória da cache ainda
precisa de ajuste (o relatório de síntese propõe usar a diretiva `(*
ramstyle="M9K" *)` para resolver).

---

## Parte 2 — Pasta `sim/` (traces e gabaritos)

Esses arquivos não são código — são os **dados de entrada** e os
**gabaritos de referência** usados pelos testbenches de integração. Nenhum
deles roda sozinho.

------- traces_hex/trace_validacao.mem -------

Uma lista de 8 endereços de 32 bits em hexadecimal puro (um por linha), lida
pelo `tb_cache_top.v` via `$readmemh`. Traduzindo os endereços para as
letras usadas nos comentários: `A B A B C A B C` (A=`0x0000`, B=`0x0800`,
C=`0x1000`). Esse é o trace principal de validação: ele repete A e B duas
vezes antes de introduzir C, forçando exatamente a decisão de despejo que
diferencia o Mockingjay do LRU (ver explicação em `tb_mockingjay_l1.v`
acima).

------- traces_hex/trace_mixed_hotset.mem -------

Também 8 endereços, com os 7 primeiros **idênticos** ao `trace_validacao`
(`A B A B C A B`), mas o 8º é `A` de novo em vez de `C`. Essa mudança sutil
no último acesso é o que faz o resultado da L2 mudar (1 hit / 3 misses em
vez de 2/3) e demonstra que o comportamento da cache depende genuinamente do
histórico completo, não só do endereço isolado.

------- expected_outputs/validacao_mj.txt -------

O gabarito oficial (Mockingjay), acesso por acesso, com a justificativa do
porquê de cada HIT/MISS — inclusive uma nota explicando que uma versão
anterior desse gabarito estava **errada** (alegava 4 hits/4 misses) porque
foi escrita "de trás para frente", olhando o 8º acesso antes de decidir o
que aconteceria no 5º — um erro de raciocínio impossível de reproduzir em
hardware real, que só reage ao que já aconteceu. O número correto, validado
rodando o simulador C de verdade, é 3 hits / 5 misses.

------- expected_outputs/validacao_lru.txt -------

O gabarito oficial do LRU no mesmo trace: 2 hits / 6 misses (25%). Serve de
comparação direta com o Mockingjay — mesmo trace, mesma cache, algoritmo de
substituição diferente, resultado pior.

------- validation_report.md -------

O relatório da rodada de validação do RTL. Documenta a descoberta do
"gabarito oráculo" (explicada acima), lista os dois bugs reais encontrados
no RTL — o `etr_negative` tratando ETR=0 como negativo por engano, e os
sinais de `enable` sendo reafirmados por 2 ciclos em vez de 1 — e mostra o
diff exato da correção de cada um. Termina com uma checklist completa (todos
os itens ✅) e uma lista do que ainda falta para integrar com o processador
RISC-V (sinais de dado, `write_en`, `dirty` bit, `stall`/`ready`).

------- quartus_flow_report.md -------

O relatório de síntese real, gerado ao tentar compilar `cache_hierarchy_top`
no Quartus para a FPGA Cyclone III EP3C25F324C6. O resultado foi "Flow
Failed" por estouro de Logic Elements (110% de uso) — não porque o design
esteja errado logicamente (a simulação já provou que está certo), mas porque
os arrays de tags/estado das caches foram sintetizados como flip-flops
individuais em vez de aproveitar os blocos de memória dedicados (BRAM) do
chip, que ficaram 0% utilizados. O relatório propõe três caminhos de
solução: adicionar a diretiva `ramstyle="M9K"` para forçar o uso de BRAM
(recomendado), reduzir o número de vias/conjuntos da cache, ou usar um chip
maior da mesma família.

---

## Parte 3 — Arquivos de apoio (fora de rtl/tb/sim)

Esses não fazem parte da entrega técnica, mas ajudam a entender o contexto
do projeto.

**`README.md`** — a apresentação do projeto para quem chega pela primeira
vez no repositório. Importante: ele ainda mostra a tabela de gabarito
**desatualizada**, com Mockingjay marcando 4 hits / 4 misses no
`trace_validacao`. Esse número foi corrigido depois (é o "gabarito oráculo"
mencionado acima) — o valor real e validado é **3 hits / 5 misses** (ver
`CLAUDE.md` §1.4 e `sim/validation_report.md`). Vale mencionar essa
divergência na apresentação: mostra que o grupo detectou e corrigiu o
próprio erro de validação, o que é justamente o tipo de rigor que se espera
demonstrar.

**`duvidas_projeto.md`** — um FAQ escrito para esclarecer decisões de
projeto que não são óbvias só de ler o código: por que a L2 só tem
Mockingjay (nunca LRU) — decisão deliberada, porque a L2 é o caminho mais
caro e vale a pena aplicar ali o algoritmo mais inteligente; por que o
offset da L2 é maior mas a tag é menor que a da L1 (é uma troca direta:
bloco maior consome mais bits de offset, sobrando menos para a tag); a
limitação conhecida do relógio global de 4 bits em benchmarks longos (acima
de ~15 acessos ele satura e o ETR perde a noção de tempo absoluto); e uma
análise de quantos ciclos de clock cada tipo de acesso custa hoje (~5 em
HIT de L1, ~7 em acesso à L2) e como isso poderia ser reduzido.

**`sim.tcl`** — não é um script que roda sozinho, é um arquivo de
referência com todos os comandos de simulação documentados em um só lugar
(Icarus Verilog, ModelSim/Questa e Vivado), para quem preferir copiar e
colar em vez de digitar os comandos completos.

**`CLAUDE.md`** — o documento de referência técnica mais completo do
projeto (arquitetura, gabaritos oficiais, restrições de RTL exigidas pelo
professor, armadilhas conhecidas). É a fonte de verdade usada para manter
este guia consistente — qualquer divergência entre este documento e o
`CLAUDE.md` deve ser resolvida a favor do `CLAUDE.md`.
