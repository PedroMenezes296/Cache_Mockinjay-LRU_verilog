# Relatório de Validação RTL — ProjetoCache_Verilog

- **Data da execução:** 2026-06-14
- **Ferramenta de simulação:** Icarus Verilog 12.0 (devel) (`iverilog` / `vvp`)
- **Referência autoritativa (golden):** simulador C `../Projetocache_atualizado/` (`simulador_cache.exe`,
  `src/algoritmos/mockingjay.c`), executado para fixar os números corretos.
- **Status final:** ✅ **PRONTO PARA VALIDAÇÃO FUNCIONAL / RTL** — todos os testes passam e o RTL reproduz
  o simulador C exatamente. ⚠️ **REQUER ADIÇÕES antes da integração no RV32I** (caminho de dados / sinais de
  pipeline — ver §5).

---

## 1. Descoberta principal (motiva as correções)

Os gabaritos escritos à mão estavam **inconsistentes com o próprio simulador C**:

- `trace_validacao` e `trace_mixed_hotset` têm os **7 primeiros acessos idênticos** (`A B A B C A B`),
  diferindo só no 8º. Mesmo assim as narrativas pediam decisões de despejo **opostas** no acesso 7
  (validacao "expulsa A"; mixed "expulsa C") a partir do **mesmo estado** — impossível para hardware causal.
  As narrativas foram racionalizadas de trás pra frente (conhecimento oráculo do 8º acesso).
- Rodando o simulador C real, `trace_validacao` com Mockingjay produz **3 Hits / 5 Misses** (não 4/4).
  O `mixed_hotset` produz 4/4 (consistente). **Decisão:** o simulador C é a referência; o RTL e os
  gabaritos/TBs foram alinhados a ele.

### Ground truth capturado do simulador C
| Trace | Política | L1 H/M | L2 H/M |
|---|---|---|---|
| validacao | Mockingjay | 3 / 5 | 2 / 3 |
| validacao | LRU | 2 / 6 | 3 / 3 |
| mixed_hotset | Mockingjay | 4 / 4 | 1 / 3 |
| mixed_hotset | LRU | 3 / 5 | 2 / 3 |

O RTL (`tb_cache_top`) reproduz **100%** destes valores.

---

## 2. Resultado por item do checklist

| Item | Verificação | Resultado |
|---|---|---|
| 2.1 | Sintaxe/compilação dos 7 RTLs (`-t null` com dependências) | ✅ 0 erros |
| 2.2 | `tb_saturating_counter` (incremento, saturação 15, load, reset) | ✅ 3/3 PASSOU |
| 2.3 | `tb_address_decoder` (L1 e L2, todos os endereços) | ✅ 6/6 PASSOU |
| 2.4 | `tb_etr_calculator` (ETR>0, ETR=0 protegido, negativo→MAX, saturação) | ✅ 4/4 PASSOU |
| 2.5 | `tb_lru_l1` (2 hits / 6 misses) | ✅ CORRETO |
| 2.6 | `tb_mockingjay_l1` (3 hits / 5 misses = ground truth C) | ✅ CORRETO |
| 2.7 | `tb_cache_top` (3 cenários; result_valid 1 ciclo; IDLE; global_time 1×/acesso; L2 só em miss) | ✅ todos batem com o C |
| 2.8 | Sintetizabilidade (sem `#delay`/`$display`/`initial`; `for` só em reset; sem latch) | ✅ limpo |
| 2.9 | Interface p/ RISC-V (sinais presentes / faltantes) | ⚠️ ver §5 |
| 2.10 | Casos de borda (`tb_edge_cases`) + unit TB da L2 (`tb_mockingjay_l2`) | ✅ CORRETO (0 erros) |
| 2.11 | Arquivos de trace `.mem` (conteúdo e última linha) | ✅ conferidos |

**2.7 detalhado (via `tb_edge_cases`):** `result_valid` alto por exatamente 1 ciclo ✅; FSM retorna a IDLE ✅;
`global_time` incrementa exatamente 1× por acesso ✅; com `policy_sel=0` o `mj_l1_en` permanece 0 ✅.

**2.10 casos cobertos:** flag `valid` checada antes da tag; mesmo endereço consecutivo → HIT; reset no meio da
operação limpa o estado; `access_en=0` mantém `done=0`; saturação do relógio em 15 sem overflow; preenchimento
das 8 vias da L2 e seleção de vítima pela árvore de comparadores.

---

## 3. Bugs encontrados

| # | Local | Descrição | Severidade |
|---|---|---|---|
| 1 | `rtl/etr_calculator.v:17` | `etr_negative = (sum <= current_time)` tratava **ETR = 0 como negativo** → `eff=31` (MAX) → a via era despejada por engano. O C usa `if (etr < 0)`. No acesso 5 do validacao isso expulsava **A** em vez de **B**, quebrando a sequência. | Alta (lógica) |
| 2 | `rtl/cache_controller.v` (case `L1_CHECK`/`L1_MISS_L2_CHECK`) | Os enables (`mj_l1_en`, `lru_l1_en`, `clk_enable`, `mj_l2_en`) eram reassertos a **cada ciclo** em que o estado persistia (chave em `next_state`). Como `L1_CHECK` dura 2 ciclos, a cache executava **cada acesso 2×** e `global_time` incrementava **2×/acesso** → contagens erradas (ex.: acesso 6 virava MISS) e violação do requisito "1 incremento por acesso". | Alta (timing) |
| 3 | Documentação/TBs | `validacao_mj.txt`, `tb_mockingjay_l1.v` e comentários de `tb_cache_top.v` codificavam o gabarito oráculo **4/4** (inalcançável por algoritmo causal). | Média (gabarito) |
| 4 | `rtl/cache_controller.v` | `way_used` dos submódulos fica desconectado (`.way_used()`) — sem visibilidade para SignalTap. | Baixa (debug) — não corrigido |

---

## 4. Correções aplicadas

```diff
# rtl/etr_calculator.v
- assign etr_negative = (sum <= {1'b0, current_time});
+ assign etr_negative = (sum <  {1'b0, current_time});   // ETR=0 protegido (espelha if(etr<0) do C)

# rtl/cache_controller.v  (enables viram PULSO ÚNICO na entrada do estado)
- L1_CHECK: begin            clk_enable<=1; mj_l1_en<=policy_sel; lru_l1_en<=~policy_sel; end
+ L1_CHECK: if (state==IDLE) begin clk_enable<=1; mj_l1_en<=policy_sel; lru_l1_en<=~policy_sel; end
- L1_MISS_L2_CHECK: begin               mj_l2_en<=1; end
+ L1_MISS_L2_CHECK: if (state==L1_CHECK) begin mj_l2_en<=1; end
```

Reconciliação de gabaritos/TBs com o C:
- `sim/expected_outputs/validacao_mj.txt` — reescrito para 3/5 (L1) + 2/3 (L2), com nota sobre o erro oráculo.
- `tb/tb_mockingjay_l1.v` — auto-checagem e comentários ajustados para 3 hits / 5 misses.
- `tb/tb_etr_calculator.v` — expectativas alinhadas ao novo `etr_negative` (ETR=0 → `neg=0`).
- `tb/tb_cache_top.v` — comentários "Esperado" atualizados para os valores reais do C.

Novos testbenches criados:
- `tb/tb_mockingjay_l2.v` — unit TB da L2 (8 vias, vítima pela árvore de comparadores). ✅
- `tb/tb_edge_cases.v` — casos de borda 2.10 + checagens de timing do controller. ✅

> Observação: o RTL de `mockingjay_l1/l2`, `lru_l1`, `address_decoder` e `saturating_counter` **não** precisou
> de mudança própria — ficaram corretos com a correção #1 (ETR) e #2 (controller).

---

## 5. Interface para integração com RISC-V RV32I (item 2.9)

**Presentes em `cache_controller`:** `clk`, `rst_n` (síncrono, ativo-baixo), `start`, `address[31:0]`,
`policy_sel`, `result_valid`, `l1_hit_out`, `l2_hit_out`, `full_miss_out`, `state_debug[2:0]`. ✅

**Faltantes (provável exigência do professor na integração):**
- `write_en` (distinção leitura/escrita) e **dados de bloco** (`wdata`/`rdata`) — hoje a cache só rastreia tags.
- `dirty` bit (política write-back real).
- **`stall`/`ready`** para o pipeline — o acesso é multi-ciclo; o core precisa de handshake de parada.
- Expor `way_used` no topo para depuração (SignalTap).

---

## 6. Status final

✅ **RTL funcionalmente validado contra o simulador C** (referência autoritativa): LRU e Mockingjay, L1 e L2,
todos os cenários batem exatamente. Sintetizabilidade verificada (sem construções não-sintetizáveis em `rtl/`).

⚠️ **Antes da integração no RV32I:** adicionar caminho de dados (wdata/rdata), `write_en`, `dirty`, e
`stall/ready`, conforme a especificação da interface do core (§5).

### Limitações conhecidas
1. Caches rastreiam **tags/estado**, não dados; write-allocate / write-back **implícito** sem dirty bit.
2. `interval` em 4 bits (`4'hF`) vs `999999` no C — idêntico nos traces curtos; revisar largura para traces longos.
