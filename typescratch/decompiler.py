"""TypeScratch Decompiler - converts .sb3 files back to .tysh source.

Usage:
    typescratch decompile <file.sb3> [--out <file.tysh>]
    python -m typescratch decompile <file.sb3>

Reads a .sb3 file (Scratch 3.0 project), walks the block graph,
and outputs equivalent TypeScratch source code.
"""

import json
import zipfile
import os
from typing import Dict, List, Optional, Tuple, Any

from . import blocks as B


# Reverse lookup: opcode -> TypeScratch syntax
# Build from the STACK_BLOCKS and REPORTERS tables
_OPCODE_TO_TS = {}  # opcode -> (ts_key, spec)

def _build_reverse_lookup():
    """Build a reverse lookup from Scratch opcode to TypeScratch syntax."""
    for key, spec in B.STACK_BLOCKS.items():
        opcode = spec["opcode"]
        _OPCODE_TO_TS[opcode] = (key, spec)
    for key, spec in B.REPORTERS.items():
        opcode = spec["opcode"]
        if opcode not in _OPCODE_TO_TS:
            _OPCODE_TO_TS[opcode] = (key, spec)
    for kind, spec in B.HAT_BLOCKS.items():
        opcode = spec["opcode"]
        _OPCODE_TO_TS[opcode] = (kind, spec)

_build_reverse_lookup()


class Decompiler:
    def __init__(self, project: dict, assets: Dict[str, bytes]):
        self.project = project
        self.assets = assets
        self.output: List[str] = []
        self.extensions: List[str] = []
        self.indent_level = 0

    def decompile(self) -> str:
        """Decompile the project and return .tysh source."""
        # Extensions
        exts = self.project.get("extensions", [])
        ext_map_reverse = {
            "pen": "Pen", "music": "Music", "text2speech": "Text to Speech",
            "speech2text": "Speech to Text", "translate": "Translate",
            "video_sensing": "Video Sensing", "makeymakey": "Makey Makey",
            "microbit": "micro:bit", "boost": "LEGO BOOST",
            "ev3": "LEGO EV3", "wedov2": "LEGO WeDo 2",
            "gdxfor": "Go Direct Force",
        }
        for ext in exts:
            name = ext_map_reverse.get(ext, ext)
            self.output.append(f"extension {name}")
        if exts:
            self.output.append("")

        # Targets
        for target in self.project.get("targets", []):
            if target.get("isStage"):
                # Stage - emit backdrops
                costumes = target.get("costumes", [])
                for c in costumes:
                    self.output.append(f'b "{c["name"]}"')
                if costumes:
                    self.output.append("")
            else:
                self._decompile_target(target)

        return "\n".join(self.output)

    def _decompile_target(self, target: dict):
        """Decompile a sprite target."""
        name = target.get("name", "Sprite")
        attrs = []
        if target.get("x", 0) != 0 or target.get("y", 0) != 0:
            attrs.append(f'xy={target.get("x", 0)}, {target.get("y", 0)}')
        if target.get("direction", 90) != 90:
            attrs.append(f'dir={target.get("direction", 90)}')
        if target.get("size", 100) != 100:
            attrs.append(f'size={target.get("size", 100)}')
        if not target.get("visible", True):
            attrs.append("visible=false")
        rot = target.get("rotationStyle", "all around")
        if rot != "all around":
            attrs.append(f"rot={rot}")

        attr_str = " ".join(attrs)
        if attr_str:
            self.output.append(f's "{name}" {attr_str}')
        else:
            self.output.append(f's "{name}"')

        # Variables
        for vid, vinfo in target.get("variables", {}).items():
            if isinstance(vinfo, list) and len(vinfo) >= 2:
                vname, vval = vinfo[0], vinfo[1]
                if isinstance(vval, str):
                    self.output.append(f"  {vname} = \"{vval}\"")
                elif isinstance(vval, (int, float)):
                    self.output.append(f"  {vname} = {vval}")

        # Lists
        for lid, linfo in target.get("lists", {}).items():
            if isinstance(linfo, list) and len(linfo) >= 2:
                lname, lval = linfo[0], linfo[1]
                if isinstance(lval, list) and lval:
                    items = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in lval)
                    self.output.append(f"  list {lname} = [{items}]")
                else:
                    self.output.append(f"  list {lname}")

        # Custom blocks
        blocks = target.get("blocks", {})
        for bid, block in blocks.items():
            if not isinstance(block, dict):
                continue
            if block.get("opcode") == "procedures_definition":
                self._decompile_custom_block_def(blocks, bid, target)

        # Scripts (hats)
        for bid, block in blocks.items():
            if not isinstance(block, dict):
                continue
            if self._is_hat(block):
                self.output.append("")
                self._decompile_script(blocks, bid)

        self.output.append("")

    def _is_hat(self, block: dict) -> bool:
        op = block.get("opcode", "")
        return (op.startswith("event_when") or
                op.startswith("control_start_as_clone") or
                op.startswith("videoSensing_when") or
                op.startswith("speech2text_when") or
                op.startswith("makeymakey_when") or
                op.startswith("microbit_when") or
                op.startswith("boost_when") or
                op.startswith("ev3_when") or
                op.startswith("wedo2_when") or
                op.startswith("gdxfor_when"))

    def _decompile_custom_block_def(self, blocks: dict, def_id: str, target: dict):
        """Decompile a procedures_definition."""
        def_block = blocks[def_id]
        # Get the prototype
        cb_input = def_block.get("inputs", {}).get("custom_block", [])
        if len(cb_input) < 2:
            return
        proto_id = cb_input[1]
        if proto_id not in blocks:
            return
        proto = blocks[proto_id]
        mutation = proto.get("mutation", {})
        proccode = mutation.get("proccode", "")
        arg_names = json.loads(mutation.get("argumentnames", "[]"))
        warp = mutation.get("warp", "false") == "true"

        # Parse the proccode to get the block name
        # proccode is like "Add %s %s" or "Greet %s"
        parts = proccode.split(" ")
        block_name_parts = []
        for p in parts:
            if p.startswith("%"):
                break
            block_name_parts.append(p)
        block_name = " ".join(block_name_parts) if block_name_parts else proccode.split(" ")[0]

        # Build the def line
        args_str = ""
        if arg_names:
            args_str = "(" + ", ".join(arg_names) + ")"
        warp_str = " warp=true" if warp else ""
        self.output.append(f"def {block_name}{args_str}{warp_str} {{")

        # Decompile the body
        body_start = def_block.get("next")
        if body_start and body_start in blocks:
            self.indent_level = 1
            self._decompile_chain(blocks, body_start)
            self.indent_level = 0

        self.output.append("}")

    def _decompile_script(self, blocks: dict, hat_id: str):
        """Decompile a hat + its body."""
        hat_block = blocks[hat_id]
        op = hat_block.get("opcode", "")

        # Find the hat kind
        hat_kind = None
        hat_args = []
        for kind, spec in B.HAT_BLOCKS.items():
            if spec["opcode"] == op:
                hat_kind = kind
                # Extract field values
                for fname, arg_idx in spec.get("fields", []):
                    fields = hat_block.get("fields", {})
                    if fname in fields:
                        hat_args.append(fields[fname][0])
                    elif fname == "BROADCAST_OPTION" and "BROADCAST_OPTION" in fields:
                        hat_args.append(fields["BROADCAST_OPTION"][0])
                break

        if hat_kind is None:
            # Unknown hat - try to make something
            hat_kind = op.replace("event_when", "").replace("_", " ")

        # Build the hat line
        if hat_kind == "gf":
            self.output.append("when gf clicked {")
        elif hat_kind == "spr":
            self.output.append("when spr clicked {")
        elif hat_kind == "stage_clicked":
            self.output.append("when stage clicked {")
        elif hat_kind == "cloned":
            self.output.append("when cloned {")
        elif hat_kind == "key" and hat_args:
            self.output.append(f'when key [{hat_args[0]}] pressed {{')
        elif hat_kind == "backdrop" and hat_args:
            self.output.append(f'when backdrop switches to [{hat_args[0]}] {{')
        elif hat_kind == "receive" and hat_args:
            self.output.append(f'when I receive [{hat_args[0]}] {{')
        elif hat_kind == "greater_than" and hat_args:
            self.output.append(f'when [{hat_args[0]}] > [{hat_args[1] if len(hat_args) > 1 else ""}] {{')
        else:
            self.output.append(f"when {hat_kind} {{")

        # Body
        body_start = hat_block.get("next")
        if body_start and body_start in blocks:
            self.indent_level = 1
            self._decompile_chain(blocks, body_start)
            self.indent_level = 0

        self.output.append("}")

    def _decompile_chain(self, blocks: dict, start_id: str):
        """Decompile a chain of blocks linked by next/parent."""
        cur = start_id
        seen = set()
        while cur and cur in blocks and cur not in seen:
            seen.add(cur)
            block = blocks[cur]
            if not isinstance(block, dict):
                break
            self._decompile_block(blocks, block)
            cur = block.get("next")

    def _decompile_block(self, blocks: dict, block: dict):
        """Decompile a single block."""
        op = block.get("opcode", "")
        indent = "  " * self.indent_level

        # Control flow blocks
        if op == "control_if":
            cond = self._decompile_input(blocks, block, "CONDITION")
            self.output.append(f"{indent}if {cond} {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_if_else":
            cond = self._decompile_input(blocks, block, "CONDITION")
            self.output.append(f"{indent}if {cond} {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}} else {{")
            ss2 = block.get("inputs", {}).get("SUBSTACK2", [])
            if len(ss2) >= 2 and ss2[1] and ss2[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss2[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_repeat":
            times = self._decompile_input(blocks, block, "TIMES")
            self.output.append(f"{indent}repeat({times}) {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_repeat_until":
            cond = self._decompile_input(blocks, block, "CONDITION")
            self.output.append(f"{indent}repeatUntil {cond} {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_forever":
            self.output.append(f"{indent}forever {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_wait":
            dur = self._decompile_input(blocks, block, "DURATION")
            self.output.append(f"{indent}wait({dur})")
            return

        if op == "control_wait_until":
            cond = self._decompile_input(blocks, block, "CONDITION")
            self.output.append(f"{indent}waitUntil {cond}")
            return

        if op == "control_stop":
            stop_opt = block.get("fields", {}).get("STOP_OPTION", ["all"])[0]
            self.output.append(f"{indent}stop({stop_opt})")
            return

        if op == "control_create_clone_of":
            clone_opt = block.get("fields", {}).get("CLONE_OPTION", ["myself"])[0]
            self.output.append(f"{indent}createCloneOf({clone_opt})")
            return

        if op == "control_delete_this_clone":
            self.output.append(f"{indent}deleteThisClone")
            return

        if op == "control_for_each":
            val = self._decompile_input(blocks, block, "VALUE")
            var = block.get("fields", {}).get("VARIABLE", ["i"])[0]
            self.output.append(f"{indent}forEach ({var}) in ({val}) {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_all_at_once":
            self.output.append(f"{indent}allAtOnce {{")
            ss = block.get("inputs", {}).get("SUBSTACK", [])
            if len(ss) >= 2 and ss[1] and ss[1] in blocks:
                self.indent_level += 1
                self._decompile_chain(blocks, ss[1])
                self.indent_level -= 1
            self.output.append(f"{indent}}}")
            return

        if op == "control_incr_counter":
            self.output.append(f"{indent}incrementCounter")
            return

        if op == "control_clear_counter":
            self.output.append(f"{indent}resetCounter")
            return

        # Variable blocks
        if op == "data_setvariableto":
            var = block.get("fields", {}).get("VARIABLE", ["X"])[0]
            val = self._decompile_input(blocks, block, "VALUE")
            self.output.append(f"{indent}{var} = {val}")
            return

        if op == "data_changevariableby":
            var = block.get("fields", {}).get("VARIABLE", ["X"])[0]
            val = self._decompile_input(blocks, block, "VALUE")
            self.output.append(f"{indent}{var} += {val}")
            return

        if op == "data_showvariable":
            var = block.get("fields", {}).get("VARIABLE", ["X"])[0]
            self.output.append(f"{indent}showVariable({var})")
            return

        if op == "data_hidevariable":
            var = block.get("fields", {}).get("VARIABLE", ["X"])[0]
            self.output.append(f"{indent}hideVariable({var})")
            return

        # List blocks
        if op == "data_addtolist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            item = self._decompile_input(blocks, block, "ITEM")
            self.output.append(f"{indent}{lname}.add({item})")
            return

        if op == "data_deleteoflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            idx = self._decompile_input(blocks, block, "INDEX")
            self.output.append(f"{indent}{lname}.delete({idx})")
            return

        if op == "data_deletealloflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            self.output.append(f"{indent}{lname}.delete(all)")
            return

        if op == "data_insertatlist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            item = self._decompile_input(blocks, block, "ITEM")
            idx = self._decompile_input(blocks, block, "INDEX")
            self.output.append(f"{indent}{lname}.insert({item}, {idx})")
            return

        if op == "data_replaceitemoflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            idx = self._decompile_input(blocks, block, "INDEX")
            item = self._decompile_input(blocks, block, "ITEM")
            self.output.append(f"{indent}{lname}.replace({idx}, {item})")
            return

        if op == "data_showlist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            self.output.append(f"{indent}{lname}.show")
            return

        if op == "data_hidelist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            self.output.append(f"{indent}{lname}.hide")
            return

        # Broadcast
        if op == "event_broadcast":
            msg = self._decompile_input(blocks, block, "BROADCAST_INPUT")
            self.output.append(f"{indent}broadcast({msg})")
            return

        if op == "event_broadcastandwait":
            msg = self._decompile_input(blocks, block, "BROADCAST_INPUT")
            self.output.append(f"{indent}broadcast({msg}) and wait")
            return

        # Procedures call
        if op == "procedures_call":
            mutation = block.get("mutation", {})
            proccode = mutation.get("proccode", "")
            arg_ids = json.loads(mutation.get("argumentids", "[]"))
            # Parse block name from proccode
            parts = proccode.split(" ")
            name_parts = []
            for p in parts:
                if p.startswith("%"):
                    break
                name_parts.append(p)
            name = " ".join(name_parts) if name_parts else "block"
            # Get args
            args = []
            for aid in arg_ids:
                args.append(self._decompile_input(blocks, block, aid))
            args_str = ", ".join(args) if args else ""
            self.output.append(f"{indent}{name}({args_str})")
            return

        # Try the generic lookup
        ts_key, spec = _OPCODE_TO_TS.get(op, (None, None))
        if ts_key and spec:
            self._decompile_generic_block(blocks, block, ts_key, spec, indent)
            return

        # Looks: go to front/back
        if op == "looks_gotofrontback":
            fb = block.get("fields", {}).get("FRONT_BACK", ["front"])[0]
            self.output.append(f"{indent}goTo{fb.capitalize()}")
            return

        # Looks: go forward/backward layers
        if op == "looks_goforwardbackwardlayers":
            fb = block.get("fields", {}).get("FRONTBACK", ["front"])[0]
            num = self._decompile_input(blocks, block, "NUM")
            if fb == "front":
                self.output.append(f"{indent}goForwardLayers({num})")
            else:
                self.output.append(f"{indent}goBackLayers({num})")
            return

        # Unknown block - output as comment
        self.output.append(f"{indent}// TODO: unknown block {op}")

    def _decompile_generic_block(self, blocks: dict, block: dict, ts_key: str, spec: dict, indent: str):
        """Decompile a block using the spec from the blocks table."""
        # Determine the TypeScratch syntax
        # If ts_key has a dot (namespace.method), use that
        if "." in ts_key:
            call = ts_key
        else:
            call = ts_key

        # Collect field values
        field_vals = []
        for fname, fval in spec.get("fields", []):
            if fval is None:
                # Value comes from args
                pass
            else:
                # Static field value
                pass

        # Collect field values from the actual block
        actual_fields = block.get("fields", {})
        for fname, fval in spec.get("fields", []):
            if fval is None and fname in actual_fields:
                field_vals.append(actual_fields[fname][0])

        # Collect input values
        input_vals = []
        actual_inputs = block.get("inputs", {})
        for spec_entry in spec.get("args", []):
            input_name = spec_entry[0]
            if input_name in actual_inputs:
                input_vals.append(self._decompile_input(blocks, block, input_name))

        # Build the call
        all_args = field_vals + input_vals
        args_str = ", ".join(str(a) for a in all_args)

        # Check for post args (like say(text)(secs))
        post_args = []
        for spec_entry in spec.get("args", []):
            if len(spec_entry) > 2 and spec_entry[2] == "post":
                input_name = spec_entry[0]
                if input_name in actual_inputs:
                    post_args.append(self._decompile_input(blocks, block, input_name))

        # Handle say/think specially
        if ts_key in ("say", "think") and not post_args:
            ts_key = ts_key + "_"

        if post_args:
            post_str = ")(" + ", ".join(str(a) for a in post_args)
            self.output.append(f"{indent}{call}({args_str}{post_str})")
        elif all_args:
            self.output.append(f"{indent}{call}({args_str})")
        else:
            self.output.append(f"{indent}{call}")

    def _decompile_input(self, blocks: dict, block: dict, input_name: str) -> str:
        """Decompile an input value to a TypeScratch expression string."""
        inputs = block.get("inputs", {})
        if input_name not in inputs:
            return ""

        ivalue = inputs[input_name]
        if not isinstance(ivalue, list) or len(ivalue) < 2:
            return ""

        # The value is either a shadow (literal) or a block reference
        shadow_type = ivalue[0]

        # Get the actual value (could be block ref or shadow)
        val = ivalue[1] if len(ivalue) == 2 else ivalue[1]
        shadow = ivalue[-1] if len(ivalue) == 3 else None

        # If val is a string (block ID), decompile the block
        if isinstance(val, str) and val in blocks:
            return self._decompile_reporter(blocks, val)

        # If val is a list, it's a shadow primitive
        if isinstance(val, list) and len(val) >= 2:
            return self._decompile_shadow(val)

        # Check shadow
        if shadow is not None:
            if isinstance(shadow, str) and shadow in blocks:
                return self._decompile_reporter(blocks, shadow)
            if isinstance(shadow, list) and len(shadow) >= 2:
                return self._decompile_shadow(shadow)

        return ""

    def _decompile_shadow(self, shadow: list) -> str:
        """Decompile a shadow primitive [type, value] to a string."""
        prim_type = shadow[0]
        value = shadow[1] if len(shadow) >= 2 else ""

        if prim_type == 4:  # number
            return str(value)
        if prim_type == 10:  # string
            val = str(value)
            if val and val[0].isalpha() and " " not in val:
                return val
            return f'"{val}"'
        if prim_type == 9:  # color
            return str(value)
        if prim_type == 11:  # broadcast
            return str(value)
        if prim_type == 12:  # variable
            return str(value)
        if prim_type == 13:  # list
            return str(value)
        return str(value)

    def _decompile_reporter(self, blocks: dict, block_id: str) -> str:
        """Decompile a reporter block to a TypeScratch expression string."""
        block = blocks[block_id]
        if not isinstance(block, dict):
            return ""

        op = block.get("opcode", "")

        # Operators
        if op == "operator_add":
            l = self._decompile_input(blocks, block, "NUM1")
            r = self._decompile_input(blocks, block, "NUM2")
            return f"({l} + {r})"
        if op == "operator_subtract":
            l = self._decompile_input(blocks, block, "NUM1")
            r = self._decompile_input(blocks, block, "NUM2")
            return f"({l} - {r})"
        if op == "operator_multiply":
            l = self._decompile_input(blocks, block, "NUM1")
            r = self._decompile_input(blocks, block, "NUM2")
            return f"({l} * {r})"
        if op == "operator_divide":
            l = self._decompile_input(blocks, block, "NUM1")
            r = self._decompile_input(blocks, block, "NUM2")
            return f"({l} / {r})"
        if op == "operator_mod":
            l = self._decompile_input(blocks, block, "NUM1")
            r = self._decompile_input(blocks, block, "NUM2")
            return f"({l} mod {r})"
        if op == "operator_gt":
            l = self._decompile_input(blocks, block, "OPERAND1")
            r = self._decompile_input(blocks, block, "OPERAND2")
            return f"({l} > {r})"
        if op == "operator_lt":
            l = self._decompile_input(blocks, block, "OPERAND1")
            r = self._decompile_input(blocks, block, "OPERAND2")
            return f"({l} < {r})"
        if op == "operator_equals":
            l = self._decompile_input(blocks, block, "OPERAND1")
            r = self._decompile_input(blocks, block, "OPERAND2")
            return f"({l} = {r})"
        if op == "operator_and":
            l = self._decompile_input(blocks, block, "OPERAND1")
            r = self._decompile_input(blocks, block, "OPERAND2")
            return f"({l}) and ({r})"
        if op == "operator_or":
            l = self._decompile_input(blocks, block, "OPERAND1")
            r = self._decompile_input(blocks, block, "OPERAND2")
            return f"({l}) or ({r})"
        if op == "operator_not":
            operand = self._decompile_input(blocks, block, "OPERAND")
            return f"not ({operand})"
        if op == "operator_random":
            l = self._decompile_input(blocks, block, "FROM")
            r = self._decompile_input(blocks, block, "TO")
            return f"pickRandom({l}, {r})"
        if op == "operator_join":
            l = self._decompile_input(blocks, block, "STRING1")
            r = self._decompile_input(blocks, block, "STRING2")
            return f"join({l}, {r})"
        if op == "operator_length":
            s = self._decompile_input(blocks, block, "STRING")
            return f"lengthOf({s})"
        if op == "operator_letter_of":
            n = self._decompile_input(blocks, block, "LETTER")
            s = self._decompile_input(blocks, block, "STRING")
            return f"letterOf({n}, {s})"
        if op == "operator_contains":
            s1 = self._decompile_input(blocks, block, "STRING1")
            s2 = self._decompile_input(blocks, block, "STRING2")
            return f"contains({s1}, {s2})"
        if op == "operator_round":
            n = self._decompile_input(blocks, block, "NUM")
            return f"round({n})"
        if op == "operator_mathop":
            math_op = block.get("fields", {}).get("OPERATOR", [""])[0]
            n = self._decompile_input(blocks, block, "NUM")
            return f"{math_op}({n})"

        # Sensing
        if op == "sensing_answer":
            return "answer"
        if op == "sensing_mousex":
            return "mouseX"
        if op == "sensing_mousey":
            return "mouseY"
        if op == "sensing_mousedown":
            return "mouseDown"
        if op == "sensing_loudness":
            return "loudness"
        if op == "sensing_timer":
            return "timer"
        if op == "sensing_dayssince2000":
            return "daysSince2000"
        if op == "sensing_username":
            return "username"
        if op == "sensing_keypressed":
            key = block.get("fields", {}).get("KEY_OPTION", [""])[0]
            return f"keyPressed({key})"
        if op == "sensing_touchingobject":
            target = block.get("fields", {}).get("TOUCHINGOBJECTMENU", [""])[0]
            return f"touching({target})"
        if op == "sensing_touchingcolor":
            color = self._decompile_input(blocks, block, "COLOR")
            return f"touchingColor({color})"
        if op == "sensing_distanceto":
            target = block.get("fields", {}).get("DISTANCETOMENU", [""])[0]
            return f"distanceTo({target})"
        if op == "sensing_of":
            prop = block.get("fields", {}).get("PROPERTY", [""])[0]
            target = block.get("fields", {}).get("TARGET", [""])[0]
            return f"attribute({prop}, {target})"
        if op == "sensing_current":
            menu = block.get("fields", {}).get("CURRENTMENU", [""])[0]
            return f"current({menu})"

        # Motion
        if op == "motion_xposition":
            return "xPosition"
        if op == "motion_yposition":
            return "yPosition"
        if op == "motion_direction":
            return "direction"

        # Looks
        if op == "looks_size":
            return "size"
        if op == "looks_costumename":
            return "costumeName"
        if op == "looks_costumenumber":
            return "costumeNumber"
        if op == "looks_costumenumbername":
            field = block.get("fields", {}).get("NUMBER_NAME", [""])[0]
            return f"costumeNumberName({field})"
        if op == "looks_backdropnumbername":
            field = block.get("fields", {}).get("NUMBER_NAME", [""])[0]
            return f"backdropNumberName({field})"

        # Sound
        if op == "sound_volume":
            return "volume"

        # Data (list reporters)
        if op == "data_itemoflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            idx = self._decompile_input(blocks, block, "INDEX")
            return f"{lname}.item({idx})"
        if op == "data_lengthoflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            return f"{lname}.length"
        if op == "data_listcontainsitem":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            item = self._decompile_input(blocks, block, "ITEM")
            return f"{lname}.contains({item})"
        if op == "data_itemnumoflist":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            item = self._decompile_input(blocks, block, "ITEM")
            return f"{lname}.itemNum({item})"
        if op == "data_listcontents":
            lname = block.get("fields", {}).get("LIST", ["list"])[0]
            return f"{lname}.contents"

        # Control
        if op == "control_get_counter":
            return "counter"

        # Argument reporter
        if op in ("argument_reporter_string_number", "argument_reporter_boolean"):
            val = block.get("fields", {}).get("VALUE", [""])[0]
            return val

        # Variable reference (data_variable)
        if op == "data_variable":
            val = block.get("fields", {}).get("VARIABLE", [""])[0]
            return val

        # TurboWarp
        if op == "tw_isTurboWarp":
            return "isTurboWarp"
        if op == "tw_isCompiled":
            return "isCompiled"
        if op == "tw_isForked":
            return "isForked"

        # Try generic lookup
        ts_key, spec = _OPCODE_TO_TS.get(op, (None, None))
        if ts_key:
            # Reporter with fields
            field_vals = []
            actual_fields = block.get("fields", {})
            for fname, fval in spec.get("fields", []):
                if fval is None and fname in actual_fields:
                    field_vals.append(actual_fields[fname][0])

            input_vals = []
            actual_inputs = block.get("inputs", {})
            for spec_entry in spec.get("args", []):
                input_name = spec_entry[0]
                if input_name in actual_inputs:
                    input_vals.append(self._decompile_input(blocks, block, input_name))

            all_args = field_vals + input_vals
            args_str = ", ".join(str(a) for a in all_args)
            return f"{ts_key}({args_str})" if all_args else ts_key

        # Menu shadow blocks (used as field values in dropdowns)
        if op == "motion_goto_menu":
            return block.get("fields", {}).get("TO", [""])[0]
        if op == "motion_pointtowards_menu":
            return block.get("fields", {}).get("TOWARDS", [""])[0]
        if op == "motion_glideto_menu":
            return block.get("fields", {}).get("TO", [""])[0]
        if op == "sensing_of_object_menu":
            return block.get("fields", {}).get("OBJECT", [""])[0]
        if op == "sensing_touchingobjectmenu":
            return block.get("fields", {}).get("TOUCHINGOBJECTMENU", [""])[0]
        if op == "sensing_distancetomenu":
            return block.get("fields", {}).get("DISTANCETOMENU", [""])[0]
        if op == "sensing_keyoptions":
            return block.get("fields", {}).get("KEY_OPTION", [""])[0]
        if op == "control_create_clone_of_menu":
            return block.get("fields", {}).get("CLONE_OPTION", [""])[0]
        if op == "looks_backdrops":
            return block.get("fields", {}).get("BACKDROP", [""])[0]
        if op == "looks_costume":
            return block.get("fields", {}).get("COSTUME", [""])[0]
        if op == "sound_sounds_menu":
            return block.get("fields", {}).get("SOUND_MENU", [""])[0]
        if op == "sound_beats_menu":
            return block.get("fields", {}).get("BEAT", [""])[0]
        if op == "sound_effects_menu":
            return block.get("fields", {}).get("EFFECT", [""])[0]

        # Unknown reporter
        return f"/* {op} */"


def decompile_sb3(path: str) -> str:
    """Decompile a .sb3 file and return .tysh source code."""
    with zipfile.ZipFile(path, "r") as zf:
        project = json.loads(zf.read("project.json"))
        assets = {}
        for name in zf.namelist():
            if name != "project.json":
                assets[name] = zf.read(name)

    dc = Decompiler(project, assets)
    return dc.decompile()


def decompile_to_file(sb3_path: str, out_path: Optional[str] = None) -> str:
    """Decompile a .sb3 file and write to .tysh file."""
    source = decompile_sb3(sb3_path)
    if out_path is None:
        base, _ = os.path.splitext(sb3_path)
        out_path = base + ".tysh"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(source)
    return out_path
