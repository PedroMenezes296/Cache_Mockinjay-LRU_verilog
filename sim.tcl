# Script de simulação — compatível com Icarus Verilog, ModelSim e Vivado Simulator
#
# ICARUS VERILOG (grátis, instalar em https://bleyer.org/icarus/):
#   iverilog -o sim_out rtl/address_decoder.v rtl/saturating_counter_4bit.v \
#            rtl/etr_calculator.v rtl/mockingjay_l1_cache.v rtl/lru_l1_cache.v \
#            rtl/mockingjay_l2_cache.v rtl/cache_controller.v tb/tb_cache_top.v
#   vvp sim_out
#
# TESTES UNITÁRIOS (Icarus):
#   iverilog -o tb_sat rtl/saturating_counter_4bit.v tb/tb_saturating_counter.v && vvp tb_sat
#   iverilog -o tb_dec rtl/address_decoder.v tb/tb_address_decoder.v && vvp tb_dec
#   iverilog -o tb_etr rtl/etr_calculator.v tb/tb_etr_calculator.v && vvp tb_etr
#   iverilog -o tb_lru rtl/lru_l1_cache.v rtl/etr_calculator.v tb/tb_lru_l1.v && vvp tb_lru
#   iverilog -o tb_mj  rtl/mockingjay_l1_cache.v rtl/etr_calculator.v tb/tb_mockingjay_l1.v && vvp tb_mj
#
# MODELISM / QUESTA:
#   vlog rtl/*.v tb/tb_cache_top.v
#   vsim -c tb_cache_top -do "run -all; quit"
#
# VIVADO (GUI):
#   1. New Project → Add Sources: rtl/*.v
#   2. Add Simulation Sources: tb/tb_cache_top.v
#   3. Run Simulation → Behavioral Simulation
#   4. No console: run all
