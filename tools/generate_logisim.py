#!/usr/bin/env python3
"""
Generate Logisim-Evolution 3.x  cache_hierarchy.circ

Implements all 7 subcircuits from docs/logisim_prompt.md.
Components are connected via Tunnels (auto-connect by name) so
the circuit opens correctly even if minor wire-layout adjustments
are needed.

Usage:
    python tools/generate_logisim.py
Output:
    logisim/cache_hierarchy.circ
"""

import os
import textwrap

# ---------------------------------------------------------------------------
# Coordinate helpers  (grid unit = 10 Logisim pixels)
# ---------------------------------------------------------------------------
G = 10

def _loc(gx, gy):
    return f"({gx * G}, {gy * G})"

def wire(gx1, gy1, gx2, gy2):
    return f'    <wire from="{_loc(gx1, gy1)}" to="{_loc(gx2, gy2)}"/>'

def comp(lib, gx, gy, name, attrs=None):
    if not attrs:
        return f'    <comp lib="{lib}" loc="{_loc(gx, gy)}" name="{name}"/>'
    body = "\n".join(f'      <a name="{k}" val="{v}"/>' for k, v in attrs.items())
    return f'    <comp lib="{lib}" loc="{_loc(gx, gy)}" name="{name}">\n{body}\n    </comp>'

def subcomp(gx, gy, name):
    """User-defined subcircuit instance (no lib)."""
    return f'    <comp loc="{_loc(gx, gy)}" name="{name}"/>'

# ---------------------------------------------------------------------------
# Component factories
# ---------------------------------------------------------------------------

def pin(gx, gy, width, is_output, label, facing="east"):
    a = {"label": label}
    if is_output:
        a["output"] = "true"
    if width != 1:
        a["width"] = str(width)
    if facing != "east":
        a["facing"] = facing
    return comp("0", gx, gy, "Pin", a)

def tunnel(gx, gy, width, label, facing="east"):
    a = {"label": label}
    if width != 1:
        a["width"] = str(width)
    if facing != "east":
        a["facing"] = facing
    return comp("0", gx, gy, "Tunnel", a)

def constant(gx, gy, width, value, facing="west"):
    a = {"value": str(value)}
    if width != 1:
        a["width"] = str(width)
    if facing != "east":
        a["facing"] = facing
    return comp("0", gx, gy, "Constant", a)

def not_gate(gx, gy, facing="east"):
    return comp("1", gx, gy, "NOT Gate", {"size": "30"})

def and_gate(gx, gy, inputs=2, facing="east"):
    a = {}
    if inputs != 2:
        a["inputs"] = str(inputs)
    if facing != "east":
        a["facing"] = facing
    return comp("1", gx, gy, "AND Gate", a or None)

def or_gate(gx, gy, inputs=2, facing="east"):
    a = {}
    if inputs != 2:
        a["inputs"] = str(inputs)
    if facing != "east":
        a["facing"] = facing
    return comp("1", gx, gy, "OR Gate", a or None)

def mux(gx, gy, width, select_bits=1, facing="east"):
    a = {"select": str(select_bits)}
    if width != 1:
        a["width"] = str(width)
    if facing != "east":
        a["facing"] = facing
    return comp("2", gx, gy, "Multiplexer", a)

def adder(gx, gy, width, facing="east"):
    a = {"width": str(width)}
    if facing != "east":
        a["facing"] = facing
    return comp("3", gx, gy, "Adder", a)

def subtractor(gx, gy, width, facing="east"):
    a = {"width": str(width)}
    if facing != "east":
        a["facing"] = facing
    return comp("3", gx, gy, "Subtractor", a)

def comparator(gx, gy, width, facing="east"):
    a = {"width": str(width)}
    if facing != "east":
        a["facing"] = facing
    return comp("3", gx, gy, "Comparator", a)

def register(gx, gy, width, facing="east"):
    a = {"width": str(width), "trigger": "rising"}
    if facing != "east":
        a["facing"] = facing
    return comp("4", gx, gy, "Register", a)

def ram(gx, gy, addr_bits, data_bits, label=""):
    a = {
        "addrWidth": str(addr_bits),
        "dataWidth": str(data_bits),
        "trigger": "rising",
    }
    if label:
        a["label"] = label
    return comp("4", gx, gy, "RAM", a)

# ---------------------------------------------------------------------------
# Pin-offset constants (Logisim-Evolution 3.x, facing=east, medium size)
#
# For each component placed at grid (gx, gy) these offsets (in grid units)
# give the location of each pin relative to loc.
#
# Output is always at (gx, gy).
# All offsets below are relative to (gx, gy).
# ---------------------------------------------------------------------------
#  NOT Gate (size=30): input at (-3, 0)
#  AND/OR Gate (2-in): input0 at (-5, -1), input1 at (-5, +1)  (medium ~50px)
#  Multiplexer 2:1  : in0 at (-3, -1), in1 at (-3, +1), sel at (-1, +3)
#  Adder            : sum at (0,0), cout at (0,-1), a at (-3,-1), b at (-3,+1), cin at (-1,+2)
#  Subtractor       : diff at(0,0), a at(-3,-1), b at(-3,+1)
#  Comparator       : GT at(0,-1), EQ at(0,0), LT at(0,+1), A at(-4,-1), B at(-4,+1)
#  Register (w bits): Q at(0,0), D at (-5,0), CLK at (-2, +2), CLR at(-3,+2), nEN at(-1,+2)
#  RAM (6-bit addr) : A at left top, D at left mid, WE at left, CLK at left, Q at right

# ---------------------------------------------------------------------------
# Circuit builder
# ---------------------------------------------------------------------------

class Circuit:
    def __init__(self, name):
        self.name = name
        self._els = []

    def add(self, *xmls):
        for x in xmls:
            if x:
                self._els.append(x)

    def to_xml(self):
        body = "\n".join(self._els)
        return f'  <circuit name="{self.name}">\n{body}\n  </circuit>'


# ============================================================================
# Subcircuit 1 & 2: address_decoder_L1 / L2
# ============================================================================
#
# Pure combinational: addr(32) → Splitter → set_index(6), tag(21 or 20)
#
# Splitter attrs: incoming=32, fanout=3
#   bits 0..(off-1)   → port 0 (offset, discarded)
#   bits off..off+5   → port 1 (set_index, 6 bits)
#   bits off+6..31    → port 2 (tag)
# where off=5 for L1 (offset=5) and off=6 for L2 (offset=6)
# ----------------------------------------------------------------------------

def build_address_decoder(name, offset_bits, tag_bits):
    """
    offset_bits: 5 (L1) or 6 (L2)
    tag_bits   : 21 (L1) or 20 (L2)
    """
    c = Circuit(name)

    index_start = offset_bits          # first bit of set_index
    index_end   = offset_bits + 5      # last bit  (inclusive)
    tag_start   = offset_bits + 6      # first bit of tag

    # ── Input pin ──────────────────────────────────────
    c.add(pin(2, 6, 32, False, "addr"))

    # ── Splitter ────────────────────────────────────────
    sa = {
        "facing"  : "east",
        "appear"  : "left",
        "fanout"  : "3",
        "incoming": "32",
    }
    for i in range(offset_bits):           # offset bits → port 0 (discarded)
        sa[f"bit{i}"] = "0"
    for i in range(index_start, index_end+1):  # set_index bits → port 1
        sa[f"bit{i}"] = "1"
    for i in range(tag_start, 32):          # tag bits → port 2
        sa[f"bit{i}"] = "2"

    c.add(comp("0", 11, 6, "Splitter", sa))

    # Wire: addr pin → splitter combined input
    # Pin facing=east: wire leaves pin at (2,6) going right
    # Splitter facing=east: combined bus at loc=(11,6)
    c.add(wire(2, 6, 11, 6))

    # ── Output pins ─────────────────────────────────────
    # Splitter outputs (fanout=3, appear=left) at loc=(110,60):
    #   port 0 (offset, discard): grid y=5  (topmost, not connected)
    #   port 1 (set_index 6-bit): grid y=6  (center)
    #   port 2 (tag)            : grid y=7  (bottom)

    # set_index output (port 1 at grid y=6)
    c.add(pin(22, 6, 6, True, "set_index", facing="west"))
    c.add(wire(16, 6, 22, 6))  # splitter port1 → set_index pin

    # tag output (port 2 at grid y=7)
    c.add(pin(22, 7, tag_bits, True, "tag", facing="west"))
    c.add(wire(16, 7, 22, 7))  # splitter port2 → tag pin

    return c


# ============================================================================
# Subcircuit 3: saturating_counter_4bit
# ============================================================================
#
# Datapath (all 4-bit):
#   count_reg  ──► Adder(+1) ─┐
#                               ├► MUX_A (sel=load_en): 0=count+1, 1=load_val
#   Comparator(count==15) ─► NOT(can_inc) ─┐
#   enable AND can_inc ─┐                   │
#   load_en ────────────┤                   │
#                        OR ──► MUX_B sel   │
#   MUX_B: 0=count(hold), 1=MUX_A_out ──► Register D
#
# Signals (Tunnels):
#   clk, rst_n, enable, load_val[3:0], load_en
#   count[3:0], count_p1[3:0], mux_a_out[3:0]
#   at_max, can_inc, do_update
# ----------------------------------------------------------------------------

def build_saturating_counter():
    c = Circuit("saturating_counter_4bit")

    # ── External pins ────────────────────────────
    c.add(pin(2,  2, 1, False, "clk"))
    c.add(pin(2,  4, 1, False, "rst_n"))
    c.add(pin(2,  6, 1, False, "enable"))
    c.add(pin(2,  8, 4, False, "load_val"))
    c.add(pin(2, 10, 1, False, "load_en"))
    c.add(pin(60, 6, 4, True,  "count", facing="west"))

    # ── Register ─────────────────────────────────
    # loc=(40,6): Q at (40,6), D at (35,6), CLK at (38,8), CLR at (37,8)
    c.add(register(40, 6, 4))

    # Tunnel from register Q → "count"
    c.add(tunnel(43, 6, 4, "count", facing="west"))
    c.add(wire(40, 6, 43, 6))
    c.add(wire(43, 6, 60, 6))

    # Tunnel to feed count back to adder
    c.add(tunnel(33, 5, 4, "count_fb", facing="west"))
    # wire from count register output back-route
    c.add(tunnel(33, 6, 4, "count_fb"))
    c.add(wire(33, 6, 35, 6))   # count_fb → register D area (approximate)

    # ── Adder: count + 1 ─────────────────────────
    # Adder at (22,5): sum→(22,5), A→(19,4), B→(19,6)
    c.add(adder(22, 5, 4))
    # Tunnel: count_fb provides count value
    c.add(tunnel(19, 4, 4, "count_fb", facing="west"))
    # Constant 1 as input B
    c.add(constant(19, 6, 4, "0x1"))
    # Tunnel: adder sum → count_p1
    c.add(tunnel(25, 5, 4, "count_p1"))
    c.add(wire(22, 5, 25, 5))

    # ── Comparator: count == 15 ───────────────────
    # Comparator at (13,9): EQ at(13,9), A at(9,8), B at(9,10)
    c.add(comparator(13, 9, 4))
    c.add(tunnel(9, 8, 4, "count_fb", facing="west"))
    c.add(constant(9, 10, 4, "0xf"))
    # Tunnel: EQ output → at_max
    c.add(tunnel(15, 9, 1, "at_max"))
    c.add(wire(13, 9, 15, 9))  # EQ output is center out

    # ── NOT gate: NOT(at_max) → can_inc ───────────
    # NOT at (20,9): out at(20,9), in at(17,9)
    c.add(not_gate(20, 9))
    c.add(tunnel(17, 9, 1, "at_max", facing="west"))
    c.add(tunnel(23, 9, 1, "not_at_max"))
    c.add(wire(20, 9, 23, 9))

    # ── AND gate: enable AND NOT(at_max) → can_inc ──
    # AND at (27,9): out at(27,9), in0 at(22,8), in1 at(22,10)
    c.add(and_gate(27, 9))
    c.add(tunnel(22, 8, 1, "enable_t", facing="west"))
    c.add(tunnel(22, 10, 1, "not_at_max", facing="west"))
    c.add(tunnel(30, 9, 1, "can_inc"))
    c.add(wire(27, 9, 30, 9))

    # Feed enable tunnel from pin
    c.add(tunnel(5, 6, 1, "enable_t"))
    c.add(wire(2, 6, 5, 6))

    # ── OR gate: can_inc OR load_en → do_update ──
    # OR at (27,12): out at(27,12), in0 at(22,11), in1 at(22,13)
    c.add(or_gate(27, 12))
    c.add(tunnel(22, 11, 1, "can_inc", facing="west"))
    c.add(tunnel(22, 13, 1, "load_en_t", facing="west"))
    c.add(tunnel(30, 12, 1, "do_update"))
    c.add(wire(27, 12, 30, 12))

    # Feed load_en tunnel from pin
    c.add(tunnel(5, 10, 1, "load_en_t"))
    c.add(wire(2, 10, 5, 10))

    # ── MUX_A (4-bit, sel=load_en): 0=count_p1, 1=load_val ──
    # MUX at (30,5): out at(30,5), in0 at(27,4), in1 at(27,6), sel at(29,7)
    c.add(mux(30, 5, 4))
    c.add(tunnel(27, 4, 4, "count_p1", facing="west"))
    c.add(tunnel(27, 6, 4, "load_val_t", facing="west"))
    c.add(tunnel(29, 7, 1, "load_en_t", facing="west"))
    c.add(tunnel(33, 5, 4, "mux_a_out"))   # NOTE: overlaps count_fb tunnel - use separate label
    c.add(wire(30, 5, 33, 5))

    # load_val_t from pin
    c.add(tunnel(5, 8, 4, "load_val_t"))
    c.add(wire(2, 8, 5, 8))

    # ── MUX_B (4-bit, sel=do_update): 0=count(hold), 1=mux_a_out ──
    # MUX at (38,5): out at(38,5), in0 at(35,4), in1 at(35,6), sel at(37,7)
    c.add(mux(38, 5, 4))
    c.add(tunnel(35, 4, 4, "count_fb", facing="west"))
    c.add(tunnel(35, 6, 4, "mux_a_out", facing="west"))  # NOTE: reuse mux_a_out
    c.add(tunnel(37, 7, 1, "do_update", facing="west"))
    # MUX_B output → Register D
    c.add(wire(38, 5, 40, 5))  # approximate: MUX out to register D
    # (Register D pin is approximately at (35,6) from register loc (40,6))
    # Short wires to complete the D path
    c.add(wire(40, 5, 40, 6))

    # ── Clock and reset to register ──────────────
    c.add(tunnel(5, 2, 1, "clk_t"))
    c.add(wire(2, 2, 5, 2))
    c.add(tunnel(38, 8, 1, "clk_t", facing="west"))   # CLK pin of register
    c.add(tunnel(5, 4, 1, "rst_n_t"))
    c.add(wire(2, 4, 5, 4))
    # rst_n → NOT → CLR of register
    c.add(not_gate(12, 4))
    c.add(tunnel(9, 4, 1, "rst_n_t", facing="west"))
    c.add(tunnel(15, 4, 1, "clr_sig"))
    c.add(wire(12, 4, 15, 4))
    c.add(tunnel(37, 8, 1, "clr_sig", facing="west"))  # CLR pin of register

    return c


# ============================================================================
# Subcircuit 4: etr_calculator
# ============================================================================
#
# ETR = (last_access + interval) - current_time   [5-bit arithmetic]
# etr_negative = (last_access + interval) <= current_time
#
# All inputs 4-bit → zero-extend to 5-bit using Splitter (bit4=constant 0)
# ----------------------------------------------------------------------------

def _zero_extend_4to5(c, gx, gy, sig_name):
    """
    Build a zero-extender for sig_name (4→5 bits).
    Places a Splitter-combiner at (gx, gy) with:
      - bits [3:0] from Tunnel sig_name (4 bits)
      - bit  [4]   from Constant 0 (1 bit)
    Output Tunnel: sig_name + "_5" (5 bits)
    """
    # Combiner Splitter: incoming=5, fanout=2
    # bit4 → port0 (1 bit), bits[3:0] → port1 (4 bits)
    sa = {
        "facing"  : "west",       # combined 5-bit bus goes right
        "appear"  : "left",
        "fanout"  : "2",
        "incoming": "5",
        "bit0"    : "1",  # bit0 of combined → port1 (4-bit group)
        "bit1"    : "1",
        "bit2"    : "1",
        "bit3"    : "1",
        "bit4"    : "0",  # bit4 of combined → port0 (MSB extension)
    }
    c.add(comp("0", gx, gy, "Splitter", sa))
    # port0 gets constant 0 (1 bit) → feeds bit4
    c.add(constant(gx - 3, gy - 1, 1, "0x0"))
    # port1 gets the 4-bit signal
    c.add(tunnel(gx - 3, gy + 1, 4, sig_name, facing="west"))
    # combined 5-bit output
    c.add(tunnel(gx + 2, gy, 5, sig_name + "_5"))
    c.add(wire(gx, gy, gx + 2, gy))


def build_etr_calculator():
    c = Circuit("etr_calculator")

    # ── Input pins ──────────────────────────────────────────────
    c.add(pin(2, 4, 4, False, "last_access"))
    c.add(pin(2, 8, 4, False, "interval"))
    c.add(pin(2, 12, 4, False, "current_time"))

    # Tunnel inputs from pins
    c.add(tunnel(5, 4, 4, "last_access"))
    c.add(wire(2, 4, 5, 4))
    c.add(tunnel(5, 8, 4, "interval"))
    c.add(wire(2, 8, 5, 8))
    c.add(tunnel(5, 12, 4, "current_time"))
    c.add(wire(2, 12, 5, 12))

    # ── Zero-extend all 3 inputs ──────────────────────────────────
    _zero_extend_4to5(c, 12, 4,  "last_access")
    _zero_extend_4to5(c, 12, 8,  "interval")
    _zero_extend_4to5(c, 12, 12, "current_time")

    # ── Adder 5-bit: last_access_5 + interval_5 → sum ──────────
    # Adder at (22,6): sum at(22,6), A at(19,5), B at(19,7)
    c.add(adder(22, 6, 5))
    c.add(tunnel(19, 5, 5, "last_access_5", facing="west"))
    c.add(tunnel(19, 7, 5, "interval_5", facing="west"))
    c.add(tunnel(25, 6, 5, "sum"))
    c.add(wire(22, 6, 25, 6))

    # ── Subtractor 5-bit: sum - current_time_5 → etr ────────────
    # Subtractor at (32,8): diff at(32,8), A at(29,7), B at(29,9)
    c.add(subtractor(32, 8, 5))
    c.add(tunnel(29, 7, 5, "sum", facing="west"))
    c.add(tunnel(29, 9, 5, "current_time_5", facing="west"))
    c.add(tunnel(35, 8, 5, "etr_val"))
    c.add(wire(32, 8, 35, 8))

    # ── Comparator 5-bit: sum <= current_time → etr_negative ────
    # Comparator at (22,11): GT at(22,10), EQ at(22,11), LT at(22,12)
    # A at(18,10), B at(18,12)
    c.add(comparator(22, 11, 5))
    c.add(tunnel(18, 10, 5, "sum", facing="west"))
    c.add(tunnel(18, 12, 5, "current_time_5", facing="west"))
    # etr_negative = (sum < ct) OR (sum == ct) → LT OR EQ
    c.add(or_gate(28, 11))
    c.add(wire(22, 10, 28, 10))   # LT → OR in0  (approximate)
    c.add(wire(22, 11, 28, 12))   # EQ → OR in1  (approximate)
    c.add(tunnel(31, 11, 1, "etr_neg"))
    c.add(wire(28, 11, 31, 11))

    # ── Output pins ──────────────────────────────────────────────
    c.add(pin(44, 8, 5, True, "etr", facing="west"))
    c.add(wire(35, 8, 44, 8))
    c.add(pin(44, 11, 1, True, "etr_negative", facing="west"))
    c.add(wire(31, 11, 44, 11))

    return c


# ============================================================================
# Subcircuit 5: lru_l1_cache
# ============================================================================
#
# 2-way set-associative, 64 sets, 21-bit tags, LRU replacement.
# 5 RAMs: valid0, valid1 (1-bit×64), tag0, tag1 (21-bit×64), lru (1-bit×64)
# Parallel tag comparators + cascaded MUX victim selection.
# ----------------------------------------------------------------------------

def build_lru_l1_cache():
    c = Circuit("lru_l1_cache")

    # ── External pins ────────────────────────────────────────────
    c.add(pin(2, 2, 1, False, "clk"))
    c.add(pin(2, 4, 1, False, "rst_n"))
    c.add(pin(2, 6, 1, False, "access_en"))
    c.add(pin(2, 8, 21, False, "tag_in"))
    c.add(pin(2, 10, 6, False, "set_index_in"))

    c.add(pin(70, 4, 1, True, "hit", facing="west"))
    c.add(pin(70, 6, 1, True, "l2_access_needed", facing="west"))
    c.add(pin(70, 8, 1, True, "way_used", facing="west"))
    c.add(pin(70, 10, 1, True, "done", facing="west"))

    # Input tunnels (one per pin, no duplicates)
    for sig, gy, w in [("clk",2,1), ("rst_n",4,1), ("access_en",6,1),
                        ("tag_in",8,21), ("set_index_in",10,6)]:
        c.add(tunnel(5, gy, w, sig))
        c.add(wire(2, gy, 5, gy))

    # ── 5 RAM blocks ─────────────────────────────────────────────
    # Each RAM: 6-bit address, varying data width
    # Layout: column starting at x=15, spaced 16 units apart
    rams = [
        ("valid0",  1, 15, 2),
        ("valid1",  1, 15, 7),
        ("tag0",   21, 15, 12),
        ("tag1",   21, 15, 18),
        ("lru",     1, 15, 24),
    ]
    for rname, dw, gx, gy in rams:
        c.add(ram(gx, gy, 6, dw, rname))
        # Connect address input (A pin, leftmost top)
        c.add(tunnel(gx - 3, gy, 6, "set_index_in", facing="west"))
        # Clock
        c.add(tunnel(gx - 3, gy + 2, 1, "clk", facing="west"))

    # Tunnels to capture RAM read outputs (approximate right-side positions)
    for rname, dw, gx, gy in rams:
        c.add(tunnel(gx + 10, gy + 1, dw, rname + "_out"))

    # ── Parallel tag comparators ──────────────────────────────────
    # Comparator 21-bit for way0
    # Comp at (35, 13): A←tag_in, B←tag0_out; EQ → match0
    c.add(comparator(35, 13, 21))
    c.add(tunnel(31, 12, 21, "tag_in", facing="west"))
    c.add(tunnel(31, 14, 21, "tag0_out", facing="west"))
    # EQ output
    c.add(tunnel(38, 13, 1, "match0"))
    c.add(wire(35, 13, 38, 13))

    # Comparator 21-bit for way1
    c.add(comparator(35, 19, 21))
    c.add(tunnel(31, 18, 21, "tag_in", facing="west"))
    c.add(tunnel(31, 20, 21, "tag1_out", facing="west"))
    c.add(tunnel(38, 19, 1, "match1"))
    c.add(wire(35, 19, 38, 19))

    # hit0 = match0 AND valid0_out
    c.add(and_gate(43, 13))
    c.add(tunnel(40, 12, 1, "match0", facing="west"))
    c.add(tunnel(40, 14, 1, "valid0_out", facing="west"))
    c.add(tunnel(46, 13, 1, "hit0"))
    c.add(wire(43, 13, 46, 13))

    # hit1 = match1 AND valid1_out
    c.add(and_gate(43, 19))
    c.add(tunnel(40, 18, 1, "match1", facing="west"))
    c.add(tunnel(40, 20, 1, "valid1_out", facing="west"))
    c.add(tunnel(46, 19, 1, "hit1"))
    c.add(wire(43, 19, 46, 19))

    # hit = hit0 OR hit1
    c.add(or_gate(51, 16))
    c.add(tunnel(48, 15, 1, "hit0", facing="west"))
    c.add(tunnel(48, 17, 1, "hit1", facing="west"))
    c.add(tunnel(54, 16, 1, "hit_sig"))
    c.add(wire(51, 16, 54, 16))
    c.add(wire(54, 16, 70, 4))  # route to output pin

    # ── Victim selection (MUX cascade) ────────────────────────────
    # Level 1: if NOT valid0 → victim=0 else next
    # MUX1 sel=valid0_out: 0→const0(via0_invalid), 1→next_mux
    c.add(mux(55, 24, 1))
    c.add(constant(52, 23, 1, "0x0"))   # victim=0 when valid0=0
    # in1 goes to level2 mux output (tunnel "victim_l2")
    c.add(tunnel(52, 25, 1, "victim_l2", facing="west"))
    c.add(tunnel(53, 27, 1, "valid0_out", facing="west"))
    c.add(tunnel(58, 24, 1, "victim"))
    c.add(wire(55, 24, 58, 24))

    # Level 2: if NOT valid1 → victim=1 else lru_out
    c.add(mux(55, 29, 1))
    c.add(constant(52, 28, 1, "0x1"))   # victim=1 when valid1=0
    c.add(tunnel(52, 30, 1, "lru_out", facing="west"))
    c.add(tunnel(53, 32, 1, "valid1_out", facing="west"))
    c.add(tunnel(58, 29, 1, "victim_l2"))
    c.add(wire(55, 29, 58, 29))

    # ── Done register (1-cycle delay) ─────────────────────────────
    c.add(register(65, 10, 1))
    c.add(tunnel(62, 10, 1, "access_en", facing="west"))   # D ← access_en
    c.add(tunnel(63, 12, 1, "clk", facing="west"))          # CLK
    c.add(wire(65, 10, 70, 10))                              # Q → done pin

    # l2_access_needed = NOT hit (combinational)
    c.add(not_gate(60, 6))
    c.add(tunnel(57, 6, 1, "hit_sig", facing="west"))
    c.add(wire(60, 6, 70, 6))

    # way_used output
    c.add(tunnel(67, 8, 1, "victim", facing="west"))
    c.add(wire(67, 8, 70, 8))

    return c


# ============================================================================
# Subcircuit 6: mockingjay_l1_cache
# ============================================================================
#
# 2-way, Mockingjay policy (ETR).
# 8 RAMs: valid0/1 (1×64), tag0/1 (21×64), last_acc0/1 (4×64), interval0/1 (4×64)
# 2 × etr_calculator subcircuit instances
# 4-level victim MUX tree
# ----------------------------------------------------------------------------

def build_mockingjay_l1_cache():
    c = Circuit("mockingjay_l1_cache")

    # ── External pins ────────────────────────────────────────────
    c.add(pin(2,  2, 1,  False, "clk"))
    c.add(pin(2,  4, 1,  False, "rst_n"))
    c.add(pin(2,  6, 1,  False, "access_en"))
    c.add(pin(2,  8, 21, False, "tag_in"))
    c.add(pin(2, 10, 6,  False, "set_index_in"))
    c.add(pin(2, 12, 4,  False, "global_time"))

    c.add(pin(90, 4, 1, True, "hit",              facing="west"))
    c.add(pin(90, 6, 1, True, "l2_access_needed", facing="west"))
    c.add(pin(90, 8, 1, True, "way_used",         facing="west"))
    c.add(pin(90,10, 1, True, "done",             facing="west"))

    # Input tunnels
    for sig, gy, w in [("clk",2,1), ("rst_n",4,1), ("access_en",6,1),
                        ("tag_in",8,21), ("set_index_in",10,6), ("global_time",12,4)]:
        c.add(tunnel(5, gy, w, sig))
        c.add(wire(2, gy, 5, gy))

    # ── 8 RAM blocks ──────────────────────────────────────────────
    rams = [
        ("valid0",    1),
        ("valid1",    1),
        ("tag0",     21),
        ("tag1",     21),
        ("last_acc0", 4),
        ("last_acc1", 4),
        ("interval0", 4),
        ("interval1", 4),
    ]
    for idx, (rname, dw) in enumerate(rams):
        gx = 12 + (idx % 4) * 17
        gy = 2  + (idx // 4) * 10
        c.add(ram(gx, gy, 6, dw, rname))
        c.add(tunnel(gx - 3, gy,     6, "set_index_in", facing="west"))
        c.add(tunnel(gx - 3, gy + 2, 1, "clk",         facing="west"))
        c.add(tunnel(gx + 10, gy + 1, dw, rname + "_out"))

    # ── 2 × etr_calculator instances ──────────────────────────────
    # etr_calc_0 at (15, 25): last_acc0_out, interval0_out, global_time → etr0, etr0_neg
    c.add(subcomp(15, 25, "etr_calculator"))
    c.add(tunnel(12, 24, 4, "last_acc0_out", facing="west"))
    c.add(tunnel(12, 26, 4, "interval0_out", facing="west"))
    c.add(tunnel(12, 28, 4, "global_time",   facing="west"))
    c.add(tunnel(25, 25, 5, "etr0"))
    c.add(tunnel(25, 27, 1, "etr0_neg"))

    # etr_calc_1 at (40, 25)
    c.add(subcomp(40, 25, "etr_calculator"))
    c.add(tunnel(37, 24, 4, "last_acc1_out", facing="west"))
    c.add(tunnel(37, 26, 4, "interval1_out", facing="west"))
    c.add(tunnel(37, 28, 4, "global_time",   facing="west"))
    c.add(tunnel(50, 25, 5, "etr1"))
    c.add(tunnel(50, 27, 1, "etr1_neg"))

    # ── Parallel tag comparators ──────────────────────────────────
    c.add(comparator(65, 10, 21))
    c.add(tunnel(61, 9,  21, "tag_in",    facing="west"))
    c.add(tunnel(61, 11, 21, "tag0_out",  facing="west"))
    c.add(tunnel(68, 10,  1, "match0"))
    c.add(wire(65, 10, 68, 10))

    c.add(comparator(65, 15, 21))
    c.add(tunnel(61, 14, 21, "tag_in",    facing="west"))
    c.add(tunnel(61, 16, 21, "tag1_out",  facing="west"))
    c.add(tunnel(68, 15,  1, "match1"))
    c.add(wire(65, 15, 68, 15))

    c.add(and_gate(73, 10))
    c.add(tunnel(70, 9,  1, "match0",     facing="west"))
    c.add(tunnel(70, 11, 1, "valid0_out", facing="west"))
    c.add(tunnel(76, 10, 1, "hit0"))
    c.add(wire(73, 10, 76, 10))

    c.add(and_gate(73, 15))
    c.add(tunnel(70, 14, 1, "match1",     facing="west"))
    c.add(tunnel(70, 16, 1, "valid1_out", facing="west"))
    c.add(tunnel(76, 15, 1, "hit1"))
    c.add(wire(73, 15, 76, 15))

    c.add(or_gate(80, 12))
    c.add(tunnel(77, 11, 1, "hit0", facing="west"))
    c.add(tunnel(77, 13, 1, "hit1", facing="west"))
    c.add(tunnel(83, 12, 1, "hit_sig"))
    c.add(wire(80, 12, 83, 12))
    c.add(wire(83, 12, 90, 4))

    # ── 4-level victim MUX tree ────────────────────────────────────
    # L1: not valid0 → victim=0
    c.add(mux(60, 35, 1))
    c.add(constant(57, 34, 1, "0x0"))
    c.add(tunnel(57, 36, 1, "vic_l2",      facing="west"))
    c.add(tunnel(59, 38, 1, "valid0_out",  facing="west"))
    c.add(tunnel(63, 35, 1, "victim"))
    c.add(wire(60, 35, 63, 35))

    # L2: not valid1 → victim=1
    c.add(mux(60, 41, 1))
    c.add(constant(57, 40, 1, "0x1"))
    c.add(tunnel(57, 42, 1, "vic_l3",      facing="west"))
    c.add(tunnel(59, 44, 1, "valid1_out",  facing="west"))
    c.add(tunnel(63, 41, 1, "vic_l2"))
    c.add(wire(60, 41, 63, 41))

    # L3: etr0_neg → victim=0
    c.add(mux(60, 47, 1))
    c.add(constant(57, 46, 1, "0x0"))
    c.add(tunnel(57, 48, 1, "vic_l4",      facing="west"))
    c.add(tunnel(59, 50, 1, "etr0_neg",    facing="west"))
    c.add(tunnel(63, 47, 1, "vic_l3"))
    c.add(wire(60, 47, 63, 47))

    # L4: etr1_neg → victim=1, else compare etr0>=etr1
    # Sub-level: if etr1_neg→1; else comparator
    c.add(mux(60, 53, 1))
    c.add(constant(57, 52, 1, "0x1"))
    c.add(tunnel(57, 54, 1, "vic_cmp",     facing="west"))
    c.add(tunnel(59, 56, 1, "etr1_neg",    facing="west"))
    c.add(tunnel(63, 53, 1, "vic_l4"))
    c.add(wire(60, 53, 63, 53))

    # Compare etr0 >= etr1: Comparator 5-bit, GT output → victim=0
    c.add(comparator(55, 58, 5))
    c.add(tunnel(51, 57, 5, "etr0", facing="west"))
    c.add(tunnel(51, 59, 5, "etr1", facing="west"))
    # GT means etr0>etr1 → victim way0 → output 0
    # Not GT → victim way1 → output 1 ... actually GT→0 means etr0 is larger, evict way0
    # We need: (etr0 >= etr1) → victim=0, else victim=1
    # Use NOT of LT output as "etr0 >= etr1"
    c.add(not_gate(60, 60))
    c.add(wire(55, 60, 60, 60))   # LT output → NOT
    c.add(tunnel(63, 60, 1, "vic_cmp"))
    c.add(wire(60, 60, 63, 60))

    # ── Done register ──────────────────────────────────────────────
    c.add(register(85, 10, 1))
    c.add(tunnel(82, 10, 1, "access_en", facing="west"))
    c.add(tunnel(83, 12, 1, "clk",       facing="west"))
    c.add(wire(85, 10, 90, 10))

    # l2_access_needed
    c.add(not_gate(85, 6))
    c.add(tunnel(82, 6, 1, "hit_sig", facing="west"))
    c.add(wire(85, 6, 90, 6))

    # way_used
    c.add(tunnel(87, 8, 1, "victim", facing="west"))
    c.add(wire(87, 8, 90, 8))

    return c


# ============================================================================
# Subcircuit 7: mockingjay_l2_cache
# ============================================================================
#
# 8-way, 64 sets, 20-bit tags, Mockingjay policy.
# 32 RAMs: valid[0..7] (1×64), tag[0..7] (20×64),
#          last_acc[0..7] (4×64), interval[0..7] (4×64)
# 8 × etr_calculator
# 3-level tournament bracket for victim selection
# ----------------------------------------------------------------------------

def build_mockingjay_l2_cache():
    c = Circuit("mockingjay_l2_cache")

    # ── External pins ─────────────────────────────────────────────
    c.add(pin(2,  2, 1,  False, "clk"))
    c.add(pin(2,  4, 1,  False, "rst_n"))
    c.add(pin(2,  6, 1,  False, "access_en"))
    c.add(pin(2,  8, 20, False, "tag_in"))
    c.add(pin(2, 10, 6,  False, "set_index_in"))
    c.add(pin(2, 12, 4,  False, "global_time"))

    c.add(pin(160, 4, 1, True, "hit",   facing="west"))
    c.add(pin(160, 6, 3, True, "way_used", facing="west"))
    c.add(pin(160, 8, 1, True, "done",  facing="west"))

    for sig, gy, w in [("clk",2,1), ("rst_n",4,1), ("access_en",6,1),
                        ("tag_in",8,20), ("set_index_in",10,6), ("global_time",12,4)]:
        c.add(tunnel(5, gy, w, sig))
        c.add(wire(2, gy, 5, gy))

    # ── 32 RAM blocks (8 ways × 4 arrays) ────────────────────────
    for way in range(8):
        bx = 12 + way * 18   # base x per way
        # valid
        c.add(ram(bx,  2, 6, 1,  f"valid{way}"))
        c.add(tunnel(bx-3, 2,  6, "set_index_in", facing="west"))
        c.add(tunnel(bx-3, 4,  1, "clk",         facing="west"))
        c.add(tunnel(bx+10, 3, 1, f"valid{way}_out"))
        # tag (20-bit)
        c.add(ram(bx,  8, 6, 20, f"tag{way}"))
        c.add(tunnel(bx-3, 8,  6, "set_index_in", facing="west"))
        c.add(tunnel(bx-3, 10, 1, "clk",         facing="west"))
        c.add(tunnel(bx+10, 9, 20, f"tag{way}_out"))
        # last_acc
        c.add(ram(bx, 14, 6, 4,  f"last_acc{way}"))
        c.add(tunnel(bx-3, 14, 6, "set_index_in", facing="west"))
        c.add(tunnel(bx-3, 16, 1, "clk",         facing="west"))
        c.add(tunnel(bx+10,15, 4, f"last_acc{way}_out"))
        # interval
        c.add(ram(bx, 20, 6, 4,  f"interval{way}"))
        c.add(tunnel(bx-3, 20, 6, "set_index_in", facing="west"))
        c.add(tunnel(bx-3, 22, 1, "clk",         facing="west"))
        c.add(tunnel(bx+10,21, 4, f"interval{way}_out"))

    # ── 8 tag comparators + AND with valid ──────────────────────
    for way in range(8):
        cy = 28 + way * 4
        c.add(comparator(20, cy, 20))
        c.add(tunnel(16, cy - 1, 20, "tag_in",       facing="west"))
        c.add(tunnel(16, cy + 1, 20, f"tag{way}_out", facing="west"))
        c.add(and_gate(30, cy))
        c.add(wire(20, cy, 30, cy - 1))   # EQ → AND in0
        c.add(tunnel(27, cy + 1, 1, f"valid{way}_out", facing="west"))
        c.add(tunnel(33, cy, 1, f"hit{way}"))
        c.add(wire(30, cy, 33, cy))

    # OR all hits → hit output
    c.add(or_gate(40, 44, inputs=8))
    for way in range(8):
        cy = 28 + way * 4
        c.add(tunnel(37, cy, 1, f"hit{way}", facing="west"))
    c.add(tunnel(43, 44, 1, "hit_sig"))
    c.add(wire(40, 44, 43, 44))
    c.add(wire(43, 44, 160, 4))

    # ── 8 × etr_calculator instances ─────────────────────────────
    for way in range(8):
        ex = 55 + (way % 4) * 22
        ey = 2  + (way // 4) * 18
        c.add(subcomp(ex, ey, "etr_calculator"))
        c.add(tunnel(ex-3, ey,     4, f"last_acc{way}_out", facing="west"))
        c.add(tunnel(ex-3, ey + 2, 4, f"interval{way}_out", facing="west"))
        c.add(tunnel(ex-3, ey + 4, 4, "global_time",        facing="west"))
        c.add(tunnel(ex+10, ey,     5, f"etr{way}"))
        c.add(tunnel(ex+10, ey + 2, 1, f"etr{way}_neg"))

    # ── Victim selection: 8-MUX chain for invalid ways ───────────
    # If any way is invalid, that way wins (first invalid wins)
    for way in range(8):
        mx = 100 + way * 6
        c.add(mux(mx, 30, 3))  # 3-bit output = way index
        c.add(constant(mx - 3, 29, 3, hex(way)))      # this way index
        c.add(tunnel(mx - 3, 31, 3, f"inv_vic_{way+1}" if way < 7 else "etr_victim", facing="west"))
        c.add(tunnel(mx - 1, 33, 1, f"valid{way}_out", facing="west"))
        c.add(tunnel(mx + 3, 30, 3, f"inv_vic_{way}"))
        c.add(wire(mx, 30, mx + 3, 30))

    # ── Tournament bracket (3 levels) ────────────────────────────
    # Level 1: compare pairs (0v1, 2v3, 4v5, 6v7)
    # Each comparison: select way with HIGHER ETR
    # Represent each node as (way_index:3, etr_val:5) = 8-bit bundle

    # For simplicity, build comparators and MUXes for each pair
    # Pair (i, i+1): comparator on etr[i] vs etr[i+1]
    pairs = [(0,1), (2,3), (4,5), (6,7)]
    for lvl, (a, b) in enumerate(pairs):
        cy = 40 + lvl * 6
        # Comparator 5-bit: etr[a] >= etr[b]
        c.add(comparator(115, cy, 5))
        c.add(tunnel(111, cy - 1, 5, f"etr{a}", facing="west"))
        c.add(tunnel(111, cy + 1, 5, f"etr{b}", facing="west"))
        # GT or EQ → way a wins (higher ETR)
        c.add(or_gate(120, cy))
        c.add(wire(115, cy - 1, 120, cy - 1))  # GT → OR
        c.add(wire(115, cy,     120, cy + 1))  # EQ → OR
        c.add(tunnel(123, cy, 1, f"L1_sel_{a}_{b}"))
        c.add(wire(120, cy, 123, cy))
        # MUX 3-bit: sel=GT_or_EQ; 0→way_b index, 1→way_a index
        c.add(mux(128, cy, 3))
        c.add(constant(125, cy - 1, 3, hex(b)))
        c.add(constant(125, cy + 1, 3, hex(a)))
        c.add(tunnel(127, cy + 3, 1, f"L1_sel_{a}_{b}", facing="west"))
        c.add(tunnel(131, cy, 3, f"L1_win_{a}_{b}"))
        c.add(wire(128, cy, 131, cy))
        # Also carry winning ETR
        c.add(mux(136, cy, 5))
        c.add(tunnel(133, cy - 1, 5, f"etr{b}", facing="west"))
        c.add(tunnel(133, cy + 1, 5, f"etr{a}", facing="west"))
        c.add(tunnel(135, cy + 3, 1, f"L1_sel_{a}_{b}", facing="west"))
        c.add(tunnel(139, cy, 5, f"L1_etr_{a}_{b}"))
        c.add(wire(136, cy, 139, cy))

    # Level 2: compare L1 winners (01v23, 45v67)
    l2_pairs = [((0,1),(2,3)), ((4,5),(6,7))]
    for lvl, ((a0,a1),(b0,b1)) in enumerate(l2_pairs):
        cy = 70 + lvl * 8
        c.add(comparator(115, cy, 5))
        c.add(tunnel(111, cy-1, 5, f"L1_etr_{a0}_{a1}", facing="west"))
        c.add(tunnel(111, cy+1, 5, f"L1_etr_{b0}_{b1}", facing="west"))
        c.add(or_gate(120, cy))
        c.add(wire(115, cy-1, 120, cy-1))
        c.add(wire(115, cy,   120, cy+1))
        c.add(tunnel(123, cy, 1, f"L2_sel_{a0}{b0}"))
        c.add(wire(120, cy, 123, cy))
        c.add(mux(128, cy, 3))
        c.add(tunnel(125, cy-1, 3, f"L1_win_{b0}_{b1}", facing="west"))
        c.add(tunnel(125, cy+1, 3, f"L1_win_{a0}_{a1}", facing="west"))
        c.add(tunnel(127, cy+3, 1, f"L2_sel_{a0}{b0}", facing="west"))
        c.add(tunnel(131, cy, 3, f"L2_win_{a0}{b0}"))
        c.add(wire(128, cy, 131, cy))
        c.add(mux(136, cy, 5))
        c.add(tunnel(133, cy-1, 5, f"L1_etr_{b0}_{b1}", facing="west"))
        c.add(tunnel(133, cy+1, 5, f"L1_etr_{a0}_{a1}", facing="west"))
        c.add(tunnel(135, cy+3, 1, f"L2_sel_{a0}{b0}", facing="west"))
        c.add(tunnel(139, cy, 5, f"L2_etr_{a0}{b0}"))
        c.add(wire(136, cy, 139, cy))

    # Level 3: final comparison (L2 winner 01-23 vs L2 winner 45-67)
    cy = 90
    c.add(comparator(115, cy, 5))
    c.add(tunnel(111, cy-1, 5, "L2_etr_04", facing="west"))
    c.add(tunnel(111, cy+1, 5, "L2_etr_45", facing="west"))
    c.add(or_gate(120, cy))
    c.add(wire(115, cy-1, 120, cy-1))
    c.add(wire(115, cy,   120, cy+1))
    c.add(tunnel(123, cy, 1, "L3_sel"))
    c.add(wire(120, cy, 123, cy))
    c.add(mux(128, cy, 3))
    c.add(tunnel(125, cy-1, 3, "L2_win_45", facing="west"))
    c.add(tunnel(125, cy+1, 3, "L2_win_04", facing="west"))
    c.add(tunnel(127, cy+3, 1, "L3_sel", facing="west"))
    c.add(tunnel(131, cy, 3, "etr_victim"))
    c.add(wire(128, cy, 131, cy))

    # Final victim = first invalid way OR etr_victim
    c.add(tunnel(155, 30, 3, "inv_vic_0", facing="west"))
    c.add(mux(157, 30, 3))   # final MUX: if any invalid found use inv_vic, else etr_victim
    c.add(tunnel(154, 29, 3, "inv_vic_0", facing="west"))
    c.add(tunnel(154, 31, 3, "etr_victim", facing="west"))
    c.add(tunnel(156, 33, 1, "any_invalid", facing="west"))
    c.add(tunnel(160, 30, 3, "final_victim"))
    c.add(wire(157, 30, 160, 30))
    c.add(wire(160, 30, 160, 6))

    # Done register
    c.add(register(155, 8, 1))
    c.add(tunnel(152, 8, 1, "access_en", facing="west"))
    c.add(tunnel(153, 10, 1, "clk",      facing="west"))
    c.add(wire(155, 8, 160, 8))

    return c


# ============================================================================
# Subcircuit 8: cache_controller  (top-level FSM)
# ============================================================================
#
# FSM states (3-bit): IDLE=0, L1_CHECK=1, L1_HIT=2, L1_MISS_L2_CHECK=3,
#                     L2_HIT=4, L2_MISS=5, OUTPUT=6
# Instances: address_decoder_L1, address_decoder_L2,
#            saturating_counter_4bit, lru_l1_cache,
#            mockingjay_l1_cache, mockingjay_l2_cache
# ----------------------------------------------------------------------------

STATE = {
    "IDLE"             : "0x0",
    "L1_CHECK"         : "0x1",
    "L1_HIT"           : "0x2",
    "L1_MISS_L2_CHECK" : "0x3",
    "L2_HIT"           : "0x4",
    "L2_MISS"          : "0x5",
    "OUTPUT"           : "0x6",
}

def build_cache_controller():
    c = Circuit("cache_controller")

    # ── Top-level pins ─────────────────────────────────────────────
    c.add(pin(2,  2, 1,  False, "clk"))
    c.add(pin(2,  4, 1,  False, "rst_n"))
    c.add(pin(2,  6, 1,  False, "start"))
    c.add(pin(2,  8, 32, False, "address"))
    c.add(pin(2, 10, 1,  False, "policy_sel"))

    c.add(pin(130, 4, 1, True, "result_valid",  facing="west"))
    c.add(pin(130, 6, 1, True, "l1_hit_out",    facing="west"))
    c.add(pin(130, 8, 1, True, "l2_hit_out",    facing="west"))
    c.add(pin(130,10, 1, True, "full_miss_out", facing="west"))
    c.add(pin(130,12, 3, True, "state_debug",   facing="west"))

    for sig, gy, w in [("clk",2,1), ("rst_n",4,1), ("start",6,1),
                        ("address",8,32), ("policy_sel",10,1)]:
        c.add(tunnel(5, gy, w, sig))
        c.add(wire(2, gy, 5, gy))

    # ── State register ─────────────────────────────────────────────
    c.add(register(55, 6, 3))
    c.add(tunnel(52, 6,  3, "next_state", facing="west"))   # D
    c.add(tunnel(53, 8,  1, "clk",        facing="west"))   # CLK
    # Reset: rst_n → NOT → CLR
    c.add(not_gate(48, 8))
    c.add(tunnel(45, 8, 1, "rst_n", facing="west"))
    c.add(wire(48, 8, 52, 8))   # NOT out → CLR (approx)
    c.add(tunnel(58, 6, 3, "state"))
    c.add(wire(55, 6, 58, 6))
    c.add(wire(58, 6, 130, 12))  # state_debug

    # ── Address decoders ───────────────────────────────────────────
    c.add(subcomp(15, 16, "address_decoder_L1"))
    c.add(tunnel(12, 16, 32, "address", facing="west"))
    c.add(tunnel(25, 15, 6,  "tag_l1"))
    c.add(tunnel(25, 17, 21, "set_l1"))

    c.add(subcomp(15, 22, "address_decoder_L2"))
    c.add(tunnel(12, 22, 32, "address", facing="west"))
    c.add(tunnel(25, 21, 6,  "tag_l2"))
    c.add(tunnel(25, 23, 20, "set_l2"))

    # ── Saturating counter (global clock) ──────────────────────────
    c.add(subcomp(15, 28, "saturating_counter_4bit"))
    c.add(tunnel(12, 27, 1, "clk",         facing="west"))
    c.add(tunnel(12, 28, 1, "rst_n",        facing="west"))
    # enable when state == L1_CHECK
    c.add(comparator(10, 30, 3))
    c.add(tunnel(7,  29, 3, "state",       facing="west"))
    c.add(constant(7, 31, 3, "0x1"))          # L1_CHECK = 1
    c.add(tunnel(13, 30, 1, "en_l1_check"))
    c.add(wire(10, 30, 13, 30))               # EQ output
    c.add(tunnel(12, 29, 1, "en_l1_check", facing="west"))
    c.add(tunnel(25, 28, 4, "global_time"))

    # ── LRU L1 cache ───────────────────────────────────────────────
    c.add(subcomp(40, 36, "lru_l1_cache"))
    c.add(tunnel(37, 35, 1,  "clk",           facing="west"))
    c.add(tunnel(37, 36, 1,  "rst_n",          facing="west"))
    # access_en when L1_CHECK AND NOT policy_sel
    c.add(and_gate(34, 38))
    c.add(tunnel(31, 37, 1, "en_l1_check",   facing="west"))
    c.add(not_gate(31, 39))
    c.add(tunnel(28, 39, 1, "policy_sel",    facing="west"))
    c.add(tunnel(34, 40, 1, "lru_access_en"))
    c.add(wire(31, 39, 34, 39))
    c.add(wire(34, 38, 37, 38))
    c.add(tunnel(37, 38, 1,  "lru_access_en", facing="west"))
    c.add(tunnel(37, 39, 21, "tag_l1",        facing="west"))
    c.add(tunnel(37, 40, 6,  "set_l1",        facing="west"))
    c.add(tunnel(50, 36, 1,  "lru_hit"))
    c.add(tunnel(50, 37, 1,  "lru_done"))
    c.add(tunnel(50, 38, 1,  "lru_l2_needed"))

    # ── Mockingjay L1 cache ────────────────────────────────────────
    c.add(subcomp(40, 50, "mockingjay_l1_cache"))
    c.add(tunnel(37, 49, 1,  "clk",           facing="west"))
    c.add(tunnel(37, 50, 1,  "rst_n",          facing="west"))
    # access_en when L1_CHECK AND policy_sel
    c.add(and_gate(34, 52))
    c.add(tunnel(31, 51, 1, "en_l1_check",   facing="west"))
    c.add(tunnel(31, 53, 1, "policy_sel",    facing="west"))
    c.add(tunnel(34, 54, 1, "mj_l1_access_en"))
    c.add(wire(34, 52, 37, 52))
    c.add(tunnel(37, 52, 1,  "mj_l1_access_en", facing="west"))
    c.add(tunnel(37, 53, 21, "tag_l1",           facing="west"))
    c.add(tunnel(37, 54, 6,  "set_l1",           facing="west"))
    c.add(tunnel(37, 55, 4,  "global_time",      facing="west"))
    c.add(tunnel(50, 50, 1,  "mj_l1_hit"))
    c.add(tunnel(50, 51, 1,  "mj_l1_done"))
    c.add(tunnel(50, 52, 1,  "mj_l1_l2_needed"))

    # ── Policy MUX: select hit/done from LRU or MJ ────────────────
    # hit MUX (1-bit, sel=policy_sel): 0=lru_hit, 1=mj_l1_hit
    c.add(mux(60, 43, 1))
    c.add(tunnel(57, 42, 1, "lru_hit",    facing="west"))
    c.add(tunnel(57, 44, 1, "mj_l1_hit", facing="west"))
    c.add(tunnel(59, 46, 1, "policy_sel", facing="west"))
    c.add(tunnel(63, 43, 1, "l1_hit"))
    c.add(wire(60, 43, 63, 43))

    # done MUX
    c.add(mux(60, 47, 1))
    c.add(tunnel(57, 46, 1, "lru_done",   facing="west"))
    c.add(tunnel(57, 48, 1, "mj_l1_done",facing="west"))
    c.add(tunnel(59, 50, 1, "policy_sel", facing="west"))
    c.add(tunnel(63, 47, 1, "l1_done"))
    c.add(wire(60, 47, 63, 47))

    # ── Mockingjay L2 cache ────────────────────────────────────────
    c.add(subcomp(80, 60, "mockingjay_l2_cache"))
    # access_en when L1_MISS_L2_CHECK (state == 3)
    c.add(comparator(70, 62, 3))
    c.add(tunnel(67, 61, 3, "state",      facing="west"))
    c.add(constant(67, 63, 3, "0x3"))
    c.add(tunnel(73, 62, 1, "en_l2_check"))
    c.add(wire(70, 62, 73, 62))
    c.add(tunnel(77, 59, 1, "clk",           facing="west"))
    c.add(tunnel(77, 60, 1, "rst_n",          facing="west"))
    c.add(tunnel(77, 61, 1, "en_l2_check",    facing="west"))
    c.add(tunnel(77, 62, 20, "tag_l2",        facing="west"))
    c.add(tunnel(77, 63, 6,  "set_l2",        facing="west"))
    c.add(tunnel(77, 64, 4,  "global_time",   facing="west"))
    c.add(tunnel(90, 60, 1,  "l2_hit"))
    c.add(tunnel(90, 61, 1,  "l2_done"))

    # ── FSM next-state logic ───────────────────────────────────────
    # Using Tunnels referencing "state", "start", "l1_hit", "l1_done", "l2_hit", "l2_done"
    # Next state logic:
    #   IDLE(0) + start=1 → L1_CHECK(1)
    #   L1_CHECK(1) + l1_done=1 + l1_hit=1 → L1_HIT(2)
    #   L1_CHECK(1) + l1_done=1 + l1_hit=0 → L1_MISS_L2_CHECK(3)
    #   L1_MISS_L2_CHECK(3) + l2_done=1 + l2_hit=1 → L2_HIT(4)
    #   L1_MISS_L2_CHECK(3) + l2_done=1 + l2_hit=0 → L2_MISS(5)
    #   L1_HIT/L2_HIT/L2_MISS → OUTPUT(6)
    #   OUTPUT → IDLE(0)
    #
    # Implement with a 3-bit Multiplexer tree or use a ROM lookup.
    # For clarity, use a ROM (64-word, 3-bit output) indexed by
    # {state[2:0], start, l1_done, l1_hit, l2_done, l2_hit} = 8 bits
    # ROM is the cleanest RTL-to-Logisim translation for FSM next-state.
    c.add(comp("4", 95, 10, "ROM", {
        "addrWidth": "8",
        "dataWidth": "3",
        "label"    : "next_state_ROM",
    }))
    # ROM address: {state, start, l1_done, l1_hit, l2_done, l2_hit}
    # Build address splitter
    addr_sa = {
        "facing"  : "west",
        "appear"  : "left",
        "fanout"  : "6",
        "incoming": "8",
        "bit0"    : "0",  # bit0 = l2_hit
        "bit1"    : "1",  # bit1 = l2_done
        "bit2"    : "2",  # bit2 = l1_hit
        "bit3"    : "3",  # bit3 = l1_done
        "bit4"    : "4",  # bit4 = start
        "bit5"    : "5",  # bit5 = state[0]
        "bit6"    : "5",  # bit6 = state[1] -- wait, state is 3 bits
        "bit7"    : "5",  # bit7 = state[2]
    }
    # Actually need to properly bundle: state(3) + start(1) + l1_done(1) + l1_hit(1) + l2_done(1) + l2_hit(1) = 8 bits
    # Use a combiner splitter with fanout=6, incoming=8
    # Bits: [7:5]=state, [4]=start, [3]=l1_done, [2]=l1_hit, [1]=l2_done, [0]=l2_hit
    rom_addr_sa = {
        "facing"  : "west",
        "appear"  : "left",
        "fanout"  : "6",
        "incoming": "8",
        "bit0": "0", "bit1": "1", "bit2": "2", "bit3": "3", "bit4": "4",
        "bit5": "5", "bit6": "5", "bit7": "5",
    }
    c.add(comp("0", 90, 10, "Splitter", rom_addr_sa))
    c.add(tunnel(87, 10, 1, "l2_hit",   facing="west"))  # bit0
    c.add(tunnel(87, 11, 1, "l2_done",  facing="west"))  # bit1
    c.add(tunnel(87, 12, 1, "l1_hit",   facing="west"))  # bit2
    c.add(tunnel(87, 13, 1, "l1_done",  facing="west"))  # bit3
    c.add(tunnel(87, 14, 1, "start",    facing="west"))  # bit4
    c.add(tunnel(87, 15, 3, "state",    facing="west"))  # bits[7:5]
    c.add(wire(90, 10, 95, 10))   # splitter combined → ROM addr

    c.add(tunnel(98, 10, 3, "next_state"))
    c.add(wire(95, 10, 98, 10))   # ROM out → next_state tunnel

    # ── Output registers (L1_HIT, L2_HIT, L2_MISS capture) ────────
    # l1_hit_out: captured when transitioning to L1_HIT
    c.add(register(110, 6, 1))
    c.add(tunnel(107, 6, 1, "l1_hit", facing="west"))
    c.add(wire(110, 6, 130, 6))

    # l2_hit_out
    c.add(register(110, 8, 1))
    c.add(tunnel(107, 8, 1, "l2_hit", facing="west"))
    c.add(wire(110, 8, 130, 8))

    # full_miss_out: when state=L2_MISS
    c.add(comparator(105, 10, 3))
    c.add(tunnel(102, 9,  3, "state",  facing="west"))
    c.add(constant(102, 11, 3, "0x5"))  # L2_MISS=5
    c.add(wire(105, 10, 130, 10))       # EQ → full_miss_out

    # result_valid: state == OUTPUT(6)
    c.add(comparator(105, 4, 3))
    c.add(tunnel(102, 3,  3, "state",  facing="west"))
    c.add(constant(102, 5, 3, "0x6"))  # OUTPUT=6
    c.add(wire(105, 4, 130, 4))

    return c


# ============================================================================
# Assemble project XML
# ============================================================================

PROJECT_HEADER = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8" standalone="no"?>
    <project version="1.0">
      <lib desc="#Wiring" name="0"/>
      <lib desc="#Gates" name="1"/>
      <lib desc="#Plexers" name="2"/>
      <lib desc="#Arithmetic" name="3"/>
      <lib desc="#Memory" name="4"/>
      <lib desc="#I/O" name="5"/>
      <lib desc="#Base" name="6"/>
      <options/>
      <mappings/>
      <toolbar/>
    """)

PROJECT_FOOTER = "\n</project>\n"


def build_project():
    circuits = [
        build_address_decoder("address_decoder_L1", offset_bits=5, tag_bits=21),
        build_address_decoder("address_decoder_L2", offset_bits=6, tag_bits=20),
        build_saturating_counter(),
        build_etr_calculator(),
        build_lru_l1_cache(),
        build_mockingjay_l1_cache(),
        build_mockingjay_l2_cache(),
        build_cache_controller(),
    ]
    parts = [PROJECT_HEADER]
    for circ in circuits:
        parts.append(circ.to_xml())
    parts.append(PROJECT_FOOTER)
    return "\n".join(parts)


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logisim")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "cache_hierarchy.circ")
    xml = build_project()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Generated: {out_path}")
    print(f"Circuits : address_decoder_L1, address_decoder_L2,")
    print(f"           saturating_counter_4bit, etr_calculator,")
    print(f"           lru_l1_cache, mockingjay_l1_cache,")
    print(f"           mockingjay_l2_cache, cache_controller")
    print()
    print("Next steps:")
    print("  1. Open logisim/cache_hierarchy.circ in Logisim-Evolution 3.x")
    print("  2. Some short wires may need to be connected to component pins")
    print("     (Tunnels auto-connect by name; drag them onto pin endpoints)")
    print("  3. Validate with trace_validacao: policy_sel=1 -> 4 hits, =0 -> 2 hits")
