"""Code generator: AST -> Scratch 3.0 project.json.

Strategy
--------
Each TypeScratch sprite becomes a Scratch target.  Each script becomes
a hat block + a chain of stack blocks.  Substacks (if/repeat/forever)
become SUBSTACK inputs pointing at the first block of the inner chain.

Variables are resolved in two passes:
  1. Pre-scan the target for every `Name = ...` and `list Name` to
     collect declared variables/lists.
  2. During codegen, a BareRef node resolves to a VarRef if its name
     is in the declared set, otherwise to a StringLit (since "Scratch
     has no strings, only text").

Inputs use the canonical Scratch 3.0 format:
  * literal shadow  : [1, [primitive_type, value]]
  * block + shadow  : [2, block_id, [primitive_type, ""]]  (or null shadow)
  * variable input  : [3, [12, name, id], [12, name, id]]
  * substack        : [2, block_id]
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from . import ast_nodes as A
from . import blocks as B
from .errors import (
    CompileError, SyntaxOops, ForgotOops, ArgumentOops, TypeMismatchOops,
    Debug, did_you_mean,
)
from . import assets as ASSETS


def gen_id() -> str:
    return uuid.uuid4().hex[:20]


# Primitive shadow type codes
SHADOW_NUMBER = 4
SHADOW_COLOR = 9
SHADOW_STRING = 10
SHADOW_BROADCAST = 11
SHADOW_VAR = 12
SHADOW_LIST = 13


class Codegen:
    def __init__(self, program: A.Program, debug: Optional[Debug] = None,
                 asset_root: Optional[str] = None):
        self.program = program
        self.debug = debug or Debug(enabled=False)
        self.asset_root = asset_root  # base dir for resolving relative img paths
        # md5ext -> bytes (collected for SB3 packaging)
        self.assets: Dict[str, bytes] = {}
        # per-target state
        self.current_target: Optional[A.Target] = None
        self.current_blocks: Dict[str, dict] = {}
        self.current_vars: Dict[str, str] = {}      # name -> var_id
        self.current_var_values: Dict[str, Any] = {}  # name -> initial value
        self.current_lists: Dict[str, str] = {}     # name -> list_id
        self.current_list_values: Dict[str, list] = {}  # name -> initial list
        self.current_broadcasts: Dict[str, str] = {}  # msg -> msg (id = name)
        self.current_custom_blocks: Dict[str, dict] = {}  # name -> {proccode, argument_ids, warp}
        # Per-custom-block state (set when generating a def body)
        self.current_proc_params: Dict[str, str] = {}  # param name -> argument_id

    # =====================================================================
    # Top-level
    # =====================================================================
    def _collect_all_definitions(self) -> None:
        """Walk the entire AST and collect all defined names.

        This lets us raise ForgotOops errors when something undefined
        is used (variables, lists, custom blocks, broadcasts).
        """
        def walk_stmts(stmts, target):
            for s in stmts:
                if isinstance(s, A.VarAssign):
                    self._all_vars.add(s.name)
                elif isinstance(s, A.VarModify):
                    self._all_vars.add(s.name)
                elif isinstance(s, A.ListOp):
                    self._all_lists.add(s.list_name)
                elif isinstance(s, A.BroadcastStatement):
                    if isinstance(s.msg, A.StringLit):
                        self._all_broadcasts.add(s.msg.value)
                    elif isinstance(s.msg, A.BareRef):
                        self._all_broadcasts.add(s.msg.name)
                    elif isinstance(s.msg, A.NumberLit):
                        self._all_broadcasts.add(str(s.msg.value))
                elif isinstance(s, A.CustomBlockDef):
                    self._all_custom_blocks.add(s.name)
                    walk_stmts(s.body, target)
                elif isinstance(s, A.IfStatement):
                    walk_stmts(s.then_body, target)
                    if s.else_body:
                        walk_stmts(s.else_body, target)
                elif isinstance(s, (A.RepeatStatement, A.RepeatUntilStatement,
                                    A.ForeverStatement, A.WhileStatement,
                                    A.ForEachStatement, A.AllAtOnceStatement)):
                    walk_stmts(s.body, target)

        for target in self.program.targets:
            # List declarations
            for decl in getattr(target, "_list_decls", []):
                self._all_lists.add(decl["name"])
            # Scripts
            for script in target.scripts:
                # Hat broadcasts
                if script.hat.kind == "receive" and script.hat.args:
                    self._all_broadcasts.add(script.hat.args[0])
                walk_stmts(script.body, target)
            # Custom block defs
            for cb in target.custom_blocks:
                self._all_custom_blocks.add(cb.name)
                walk_stmts(cb.body, target)

    def generate(self) -> Tuple[dict, Dict[str, bytes]]:
        self.debug.section("Codegen")

        # Pre-scan: collect ALL definitions across ALL targets so we can
        # raise ForgotOops errors when something undefined is used.
        self._all_vars: set = set()
        self._all_lists: set = set()
        self._all_custom_blocks: set = set()
        self._all_broadcasts: set = set()
        self._collect_all_definitions()

        # Count createCloneOf calls for the clone limit warning
        self._clone_count: int = 0
        self._pending_stage_vars: list = []

        targets_json: List[dict] = []

        stage = next((t for t in self.program.targets if t.kind == "stage"), None)
        if stage is None:
            stage = A.Target(kind="stage", name="Stage")
            self.program.targets.insert(0, stage)

        # Generate sprites FIRST so we can collect stage vars ("a" scope)
        # Then generate the stage with the collected vars
        sprite_jsons: List[dict] = []
        layer = 1
        for tgt in self.program.targets:
            if tgt.kind == "sprite":
                sprite_jsons.append(self.gen_target(tgt, is_stage=False, layer_order=layer))
                layer += 1

        # Now generate the stage (it will pick up pending stage vars)
        stage_json = self.gen_target(stage, is_stage=True, layer_order=0)

        # Assemble: stage first, then sprites (correct layer order)
        targets_json.append(stage_json)
        targets_json.extend(sprite_jsons)

        # Collect ALL broadcasts from ALL sprites and merge them into the stage.
        # In Scratch 3, broadcasts are stored on the stage target.
        all_broadcasts = {}
        for tgt_json in targets_json:
            for bid, bname in tgt_json.get("broadcasts", {}).items():
                all_broadcasts[bid] = bname
        stage_json["broadcasts"] = all_broadcasts
        # Clear broadcasts from sprites (they belong on the stage)
        for tgt_json in targets_json:
            if not tgt_json["isStage"]:
                tgt_json["broadcasts"] = {}

        extensions = self._convert_extensions()

        project = {
            "targets": targets_json,
            "monitors": [],
            "extensions": extensions,
            "meta": {
                "semver": "3.0.0",
                "vm": "0.2.0",
                "agent": "TypeScratch/1.0"
            }
        }
        self.debug.dump("project.json", project)

        # Clone limit warning - check if any createCloneOf is inside a
        # repeat(N) with N > 300, or inside a forever/while loop.
        self._check_clone_limit()
        self._check_dead_code()

        return project, self.assets

    def _check_clone_limit(self) -> None:
        """Warn if the project might create more than 300 clones."""
        import sys

        def check_stmts(stmts, in_loop=False, loop_count=0, loop_type=""):
            for s in stmts:
                if isinstance(s, A.BlockCall):
                    if not s.namespace and s.method == "createCloneOf":
                        if in_loop:
                            if loop_type == "forever" or loop_type == "while" or loop_type == "repeatUntil":
                                count_str = " (in a loop that runs indefinitely)"
                            elif loop_count > 0:
                                count_str = f" (in a loop that runs {loop_count} times)"
                            else:
                                count_str = " (in a loop)"
                            print(
                                f"WARNING (line {s.line}): This project creates clones{count_str}. "
                                f"Scratch limits projects to 300 clones at a time. "
                                f"Make sure to delete clones with deleteThisClone, "
                                f"otherwise the project may hit the clone limit.",
                                file=sys.stderr
                            )
                            return
                elif isinstance(s, A.IfStatement):
                    check_stmts(s.then_body, in_loop, loop_count, loop_type)
                    if s.else_body:
                        check_stmts(s.else_body, in_loop, loop_count, loop_type)
                elif isinstance(s, A.RepeatStatement):
                    if isinstance(s.times, A.NumberLit):
                        count = int(s.times.value)
                    else:
                        count = 0
                    check_stmts(s.body, in_loop=True, loop_count=count, loop_type="repeat")
                elif isinstance(s, A.ForEachStatement):
                    if isinstance(s.count, A.NumberLit):
                        count = int(s.count.value)
                    else:
                        count = 0
                    check_stmts(s.body, in_loop=True, loop_count=count, loop_type="forEach")
                elif isinstance(s, A.ForeverStatement):
                    check_stmts(s.body, in_loop=True, loop_count=0, loop_type="forever")
                elif isinstance(s, (A.WhileStatement, A.RepeatUntilStatement)):
                    check_stmts(s.body, in_loop=True, loop_count=0, loop_type="while")
                elif isinstance(s, A.AllAtOnceStatement):
                    check_stmts(s.body, in_loop, loop_count, loop_type)
                elif isinstance(s, A.CustomBlockDef):
                    check_stmts(s.body, in_loop, loop_count, loop_type)

        for target in self.program.targets:
            for script in target.scripts:
                check_stmts(script.body)
            for cb in target.custom_blocks:
                check_stmts(cb.body)

    def _check_dead_code(self) -> None:
        """Warn about scripts that can never be triggered, and unused variables.

        Checks:
        1. when I receive [msg] where msg is never broadcast
        2. def MyBlock that is never called
        3. Variables that are assigned but never read
        4. Lists that are declared but never used
        """
        import sys

        # Find all broadcasts that are sent
        sent_broadcasts: set = set()
        # Find all custom blocks that are called
        called_blocks: set = set()
        # Find all variables that are READ (referenced in expressions)
        # A variable is "read" if it appears as a BareRef that resolves
        # to that variable, or in a VarModify (which reads + writes)
        read_vars: dict = {}  # name -> line where first read
        # Find all variables that are WRITTEN (assigned)
        written_vars: dict = {}  # name -> line where first written
        # Find all lists that are used
        used_lists: set = set()

        def walk_expr(expr):
            """Walk an expression tree to find variable reads."""
            if isinstance(expr, A.BareRef):
                # This could be a variable read (codegen resolves it)
                # We mark it as potentially read - codegen will decide
                read_vars[expr.name] = getattr(expr, 'line', 0)
            elif isinstance(expr, A.BinOp):
                walk_expr(expr.left)
                walk_expr(expr.right)
            elif isinstance(expr, A.UnaryOp):
                walk_expr(expr.operand)
            elif isinstance(expr, A.FuncCall):
                for arg in expr.args:
                    walk_expr(arg)
            elif isinstance(expr, A.VarRef):
                read_vars[expr.name] = expr.line
            elif isinstance(expr, A.TernaryExpr):
                walk_expr(expr.cond)
                walk_expr(expr.true_expr)
                walk_expr(expr.false_expr)
            elif isinstance(expr, A.ListReporterRef):
                used_lists.add(expr.list_name)

        def walk_for_usage(stmts):
            for s in stmts:
                if isinstance(s, A.BroadcastStatement):
                    if isinstance(s.msg, A.StringLit):
                        sent_broadcasts.add(s.msg.value)
                    elif isinstance(s.msg, A.BareRef):
                        sent_broadcasts.add(s.msg.name)
                elif isinstance(s, A.BlockCall):
                    if not s.namespace:
                        called_blocks.add(s.method)
                    # Walk args for variable reads
                    for arg in s.args:
                        walk_expr(arg)
                    if s.post:
                        for arg in s.post:
                            walk_expr(arg)
                elif isinstance(s, A.VarAssign):
                    written_vars[s.name] = s.line
                    walk_expr(s.value)
                elif isinstance(s, A.VarModify):
                    # VarModify reads AND writes the variable
                    read_vars[s.name] = s.line
                    written_vars[s.name] = s.line
                    walk_expr(s.value)
                elif isinstance(s, A.LocalVarDecl):
                    written_vars[s.name] = s.line
                    read_vars[s.name] = s.line
                    walk_expr(s.value)
                elif isinstance(s, A.ListOp):
                    used_lists.add(s.list_name)
                    for arg in s.args:
                        walk_expr(arg)
                elif isinstance(s, A.IfStatement):
                    walk_expr(s.cond)
                    walk_for_usage(s.then_body)
                    if s.else_body:
                        walk_for_usage(s.else_body)
                elif isinstance(s, (A.RepeatStatement, A.RepeatUntilStatement,
                                    A.WhileStatement)):
                    walk_expr(s.cond if hasattr(s, 'cond') else s.times)
                    walk_for_usage(s.body)
                elif isinstance(s, A.ForeverStatement):
                    walk_for_usage(s.body)
                elif isinstance(s, A.ForEachStatement):
                    read_vars[s.var_name] = s.line
                    written_vars[s.var_name] = s.line
                    walk_expr(s.count)
                    walk_for_usage(s.body)
                elif isinstance(s, A.AllAtOnceStatement):
                    walk_for_usage(s.body)
                elif isinstance(s, A.WaitUntilStatement):
                    walk_expr(s.cond)
                elif isinstance(s, A.CustomBlockDef):
                    walk_for_usage(s.body)
                elif isinstance(s, A.BroadcastStatement):
                    walk_expr(s.msg)

        for target in self.program.targets:
            # Collect scope vars
            for sv in getattr(target, "_scope_vars", []):
                written_vars[sv["name"]] = getattr(sv.get("value", None), 'line', 0)
                walk_expr(sv["value"])
            # Walk scripts
            for script in target.scripts:
                walk_for_usage(script.body)
            for cb in target.custom_blocks:
                walk_for_usage(cb.body)

        # Check for dead receive hats
        for target in self.program.targets:
            for script in target.scripts:
                hat = script.hat
                if hat.kind == "receive" and hat.args:
                    msg = hat.args[0]
                    if msg not in sent_broadcasts:
                        print(
                            f"WARNING (line {hat.line}): when I receive [{msg}] - "
                            f'this message is never broadcast anywhere. '
                            f'This script will never run.',
                            file=sys.stderr
                        )

        # Check for dead custom blocks (defined but never called)
        for target in self.program.targets:
            for cb in target.custom_blocks:
                if cb.name not in called_blocks:
                    print(
                        f"WARNING (line {cb.line}): def {cb.name} - "
                        f'this custom block is never called. '
                        f'It will exist in the project but never run.',
                        file=sys.stderr
                    )

        # Check for unused variables (written but never read)
        # A variable is "unused" if it's written (assigned) but never
        # read (referenced in an expression or modified with += etc.)
        # We skip variables that start with _ (internal/temp variables)
        for vname, vline in written_vars.items():
            if vname.startswith("_"):
                continue  # skip internal variables
            if vname not in read_vars:
                print(
                    f"WARNING (line {vline}): variable \"{vname}\" is assigned "
                    f'but never read. It will exist in the project but '
                    f'its value is never used.',
                    file=sys.stderr
                )

        # Check for unused lists
        for target in self.program.targets:
            for decl in getattr(target, "_list_decls", []):
                lname = decl["name"]
                if lname not in used_lists:
                    print(
                        f"WARNING: list \"{lname}\" is declared but never used. "
                        f'It will exist in the project but is never accessed.',
                        file=sys.stderr
                    )

    def _convert_extensions(self) -> List[str]:
        """Map TypeScratch extension names to Scratch extension IDs."""
        ext_map = {
            "pen": "pen",
            "music": "music",
            "video sensing": "video_sensing",
            "videosensing": "video_sensing",
            "text to speech": "text2speech",
            "text2speech": "text2speech",
            "tts": "text2speech",
            "speech to text": "speech2text",
            "speech2text": "speech2text",
            "listen": "speech2text",
            "translate": "translate",
            "makey makey": "makeymakey",
            "makeymakey": "makeymakey",
            "microbit": "microbit",
            "micro bit": "microbit",
            "micro:bit": "microbit",
            "micro :bit": "microbit",
            "micro : bit": "microbit",
            "mesh": "mesh",
            "ev3": "ev3",
            "lego ev3": "ev3",
            "lego mindstorms": "ev3",
            "boost": "boost",
            "lego boost": "boost",
            "wedo": "wedov2",
            "wedo2": "wedov2",
            "wedov2": "wedov2",
            "lego wedo": "wedov2",
            "lego wedo 2": "wedov2",
            "lego wedo2": "wedov2",
            "gdxfor": "gdxfor",
            "go direct force": "gdxfor",
            "go direct": "gdxfor",
            "force and acceleration": "gdxfor",
            "nfc": "nfc",
        }
        out = []
        for ext in self.program.extensions:
            key = ext.lower().strip()
            mapped = ext_map.get(key, key.replace(" ", "_"))
            if mapped not in out:
                out.append(mapped)
        return out

    # =====================================================================
    # Target
    # =====================================================================
    def gen_target(self, target: A.Target, is_stage: bool, layer_order: int) -> dict:
        self.debug.line(f"target: {target.name} (stage={is_stage})")
        self.current_target = target
        self.current_blocks = {}
        self.current_vars = {}
        self.current_var_values = {}
        self.current_lists = {}
        self.current_list_values = {}
        self.current_broadcasts = {}
        self.current_custom_blocks = {}
        self.current_proc_params = {}

        # Pre-scan for variables and lists
        self._scan_variables(target)
        self._scan_lists(target)

        # Handle scoped variable declarations (a/o syntax)
        # "a" vars go on the stage, "o" vars go on the sprite
        # We declare them here so they exist in the right target's variable dict
        for sv in getattr(target, "_scope_vars", []):
            vname = sv["name"]
            scope = sv["scope"]
            if scope == "a" and not is_stage:
                # This var should be on the stage, not this sprite
                # We'll store it for the stage to pick up
                if not hasattr(self, "_pending_stage_vars"):
                    self._pending_stage_vars = []
                self._pending_stage_vars.append(sv)
                # Also declare it locally so references work
                if vname not in self.current_vars:
                    self._declare_var(vname, 0)
                # Mark it as a stage var so we know to not emit it on the sprite
                self._stage_var_names = getattr(self, "_stage_var_names", set())
                self._stage_var_names.add(vname)
            elif scope == "o" and not is_stage:
                # This sprite only - just declare it
                if vname not in self.current_vars:
                    self._declare_var(vname, 0)
            elif scope == "a" and is_stage:
                # We're generating the stage and this is an "a" var
                if vname not in self.current_vars:
                    self._declare_var(vname, 0)
            elif scope == "o" and is_stage:
                # "o" on stage doesn't make sense, but declare it anyway
                if vname not in self.current_vars:
                    self._declare_var(vname, 0)

        # If we're on the stage, pick up pending stage vars from sprites
        if is_stage:
            for sv in getattr(self, "_pending_stage_vars", []):
                vname = sv["name"]
                if vname not in self.current_vars:
                    val = sv["value"]
                    if isinstance(val, A.NumberLit):
                        self._declare_var(vname, val.value)
                    elif isinstance(val, A.StringLit):
                        self._declare_var(vname, val.value)
                    else:
                        self._declare_var(vname, 0)

        # Generate custom block definitions (procedures_definition)
        for cb in target.custom_blocks:
            self.gen_custom_block_def(cb)

        # Generate scripts
        for script in target.scripts:
            self.gen_script(script)

        # Costumes
        costumes_json = self.gen_costumes(target, is_stage)

        # Sounds
        sounds_json = self.gen_sounds(target)

        # Variables JSON - Scratch 3 format: {id: [name, value]}
        # Skip "a" (all sprites) vars on sprites, they go on the stage
        variables_json = {}
        stage_var_names = getattr(self, "_stage_var_names", set())
        for vname, vid in self.current_vars.items():
            if not is_stage and vname in stage_var_names:
                continue  # this var belongs on the stage, not here
            val = self.current_var_values.get(vname, 0)
            variables_json[vid] = [vname, val]

        # Lists JSON - Scratch 3 format: {id: [name, [items...]]}
        lists_json = {}
        for lname, lid in self.current_lists.items():
            val = self.current_list_values.get(lname, [])
            lists_json[lid] = [lname, val]

        target_json: dict = {
            "isStage": is_stage,
            "name": target.name,
            "variables": variables_json,
            "lists": lists_json,
            "broadcasts": self.current_broadcasts,
            "blocks": self.current_blocks,
            "comments": {},
            "currentCostume": 0,
            "costumes": costumes_json,
            "sounds": sounds_json,
            "volume": 100,
            "layerOrder": layer_order,
        }
        if is_stage:
            target_json.update({
                "tempo": 60,
                "videoState": "on",
                "videoTransparency": 50,
                "textToSpeechLanguage": None,
            })
        else:
            target_json.update({
                "visible": target.visible,
                "x": target.x,
                "y": target.y,
                "size": target.size,
                "direction": target.direction,
                "draggable": False,
                "rotationStyle": B.ROTATION_STYLES.get(target.rotation_style, "all around"),
            })
        return target_json

    # ---- variable / list scanning -----------------------------------------
    def _scan_variables(self, target: A.Target) -> None:
        """Walk target.scripts and target.custom_blocks looking for
        VarAssign / VarModify nodes and declare them."""
        def walk(stmts):
            for s in stmts:
                if isinstance(s, A.VarAssign):
                    self._declare_var(s.name, s.value)
                elif isinstance(s, A.VarModify):
                    self._declare_var(s.name, 0)
                elif isinstance(s, A.IfStatement):
                    walk(s.then_body)
                    if s.else_body:
                        walk(s.else_body)
                elif isinstance(s, (A.RepeatStatement, A.RepeatUntilStatement,
                                    A.ForeverStatement, A.WhileStatement,
                                    A.ForEachStatement, A.AllAtOnceStatement)):
                    walk(s.body)

        # If the user wrote `Points = 0` somewhere, declare Points as a var
        # with initial value 0 (only the FIRST assignment counts as init).
        for script in target.scripts:
            walk(script.body)
        for cb in target.custom_blocks:
            walk(cb.body)

    def _declare_var(self, name: str, value: Any) -> None:
        if name in self.current_vars:
            return
        vid = gen_id()
        self.current_vars[name] = vid
        # Only use the value if it's a literal.  BareRef values get
        # resolved: if it's a known variable or builtin reporter, the
        # initial value is 0 (the actual value is set at runtime by the
        # `set var to ...` block); otherwise it's a string literal.
        if isinstance(value, A.NumberLit):
            self.current_var_values[name] = value.value
        elif isinstance(value, A.StringLit):
            self.current_var_values[name] = value.value
        elif isinstance(value, A.BareRef):
            lower = value.name.lower()
            if (value.name in self.current_vars
                    or lower in B.BUILTIN_ALIASES
                    or value.name in B.REPORTERS):
                # will be set at runtime - initialize to 0
                self.current_var_values[name] = 0
            else:
                # genuine string literal
                self.current_var_values[name] = value.name
        else:
            # complex expression - will be set at runtime
            self.current_var_values[name] = 0

    def _scan_lists(self, target: A.Target) -> None:
        decls = getattr(target, "_list_decls", [])
        for decl in decls:
            name = decl["name"]
            if name in self.current_lists:
                continue
            lid = gen_id()
            self.current_lists[name] = lid
            # Resolve initial values
            initial = []
            for item in decl["initial"]:
                if isinstance(item, A.NumberLit):
                    initial.append(item.value)
                elif isinstance(item, A.StringLit):
                    initial.append(item.value)
                elif isinstance(item, A.BareRef):
                    initial.append(item.name)
                else:
                    initial.append(0)
            self.current_list_values[name] = initial

    # =====================================================================
    # Costumes and sounds
    # =====================================================================
    def gen_costumes(self, target: A.Target, is_stage: bool) -> List[dict]:
        costumes: List[dict] = []
        if is_stage:
            # Stage costumes = backdrops declared via b "name" ...
            if not target.costumes:
                # Default blank backdrop
                name, data, _ignored_md5ext, rcx, rcy = ASSETS.default_backdrop()
                asset_id = _md5(data)
                md5ext = f"{asset_id}.svg"
                self.assets[md5ext] = data
                costumes.append({
                    "assetId": asset_id,
                    "name": name,
                    "bitmapResolution": 1,
                    "md5ext": md5ext,
                    "dataFormat": "svg",
                    "rotationCenterX": rcx,
                    "rotationCenterY": rcy,
                })
            for c in target.costumes:
                name = c["name"]
                path = c.get("path")
                data, _ignored_md5ext, fmt, rcx, rcy = self._load_asset(path, is_stage=True)
                asset_id = _md5(data)
                md5ext = f"{asset_id}.{fmt}"
                self.assets[md5ext] = data
                costumes.append({
                    "assetId": asset_id,
                    "name": name,
                    "bitmapResolution": 1 if fmt == "svg" else 2,
                    "md5ext": md5ext,
                    "dataFormat": fmt,
                    "rotationCenterX": rcx,
                    "rotationCenterY": rcy,
                })
        else:
            # Sprite costume - use img= if specified
            path = target.img
            data, _ignored_md5ext, fmt, rcx, rcy = self._load_asset(path, is_stage=False)
            asset_id = _md5(data)
            md5ext = f"{asset_id}.{fmt}"
            self.assets[md5ext] = data
            # Use the costume name from the asset (e.g. "Lint Zippy")
            costume_name = "costume1"
            try:
                costume_name, _, _, _, _ = ASSETS.default_sprite_costume()
            except Exception:
                pass
            costumes.append({
                "assetId": asset_id,
                "name": costume_name,
                "bitmapResolution": 1 if fmt == "svg" else 2,
                "md5ext": md5ext,
                "dataFormat": fmt,
                "rotationCenterX": rcx,
                "rotationCenterY": rcy,
            })
            # Additional costumes from `costume name from "path.png"` imports
            for cinfo in getattr(target, "_costume_imports", []):
                cname = cinfo["name"]
                cpath = cinfo["path"]
                cdata, _cmd5, cfmt, crcx, crcy = self._load_asset(cpath, is_stage=False)
                casset_id = _md5(cdata)
                cmd5ext = f"{casset_id}.{cfmt}"
                self.assets[cmd5ext] = cdata
                costumes.append({
                    "assetId": casset_id,
                    "name": cname,
                    "bitmapResolution": 1 if cfmt == "svg" else 2,
                    "md5ext": cmd5ext,
                    "dataFormat": cfmt,
                    "rotationCenterX": crcx,
                    "rotationCenterY": crcy,
                })
        return costumes

    def gen_sounds(self, target: A.Target) -> List[dict]:
        """Generate sound assets from `sound name from "path.wav"` imports."""
        sounds = []
        for sinfo in getattr(target, "_sound_imports", []):
            name = sinfo["name"]
            path = sinfo["path"]
            full = path
            if self.asset_root and not os.path.isabs(path):
                full = os.path.join(self.asset_root, path)
            if os.path.isfile(full):
                with open(full, "rb") as f:
                    data = f.read()
                # Determine format
                if full.lower().endswith(".wav"):
                    fmt = "wav"
                elif full.lower().endswith(".mp3"):
                    fmt = "mp3"
                else:
                    fmt = "wav"
                asset_id = _md5(data)
                md5ext = f"{asset_id}.{fmt}"
                self.assets[md5ext] = data
                sounds.append({
                    "assetId": asset_id,
                    "name": name,
                    "dataFormat": fmt,
                    "format": "",
                    "rate": 48000,
                    "sampleCount": 0,
                    "md5ext": md5ext,
                })
            else:
                # File not found - use silent fallback
                from . import assets as ASSETS2
                data = ASSETS2.SILENT_WAV
                asset_id = _md5(data)
                md5ext = f"{asset_id}.wav"
                self.assets[md5ext] = data
                sounds.append({
                    "assetId": asset_id,
                    "name": name,
                    "dataFormat": "wav",
                    "format": "",
                    "rate": 48000,
                    "sampleCount": 0,
                    "md5ext": md5ext,
                })
        return sounds

    def _load_asset(self, path: Optional[str], is_stage: bool) -> Tuple[bytes, str, str, int, int]:
        """Returns (data, md5ext, format, rotationCenterX, rotationCenterY)."""
        if path:
            # Resolve relative to asset_root if set
            full = path
            if self.asset_root and not os.path.isabs(path):
                full = os.path.join(self.asset_root, path)
            if os.path.isfile(full):
                with open(full, "rb") as f:
                    data = f.read()
                fmt = "svg" if full.lower().endswith(".svg") else (
                    "png" if full.lower().endswith(".png") else "svg"
                )
                # rotation center: half of image size (rough)
                rcx, rcy = self._image_rotation_center(data, fmt, is_stage)
                md5 = _md5(data)
                return data, f"{md5}.{fmt}", fmt, rcx, rcy
            # File not found - fall through to default
        if is_stage:
            name, data, md5ext, rcx, rcy = ASSETS.default_backdrop()
            return data, md5ext, "svg", rcx, rcy
        else:
            name, data, md5ext, rcx, rcy = ASSETS.default_sprite_costume()
            return data, md5ext, "svg", rcx, rcy

    def _image_rotation_center(self, data: bytes, fmt: str, is_stage: bool) -> Tuple[int, int]:
        """Best-effort rotation center based on image dimensions."""
        if fmt == "svg":
            # Try to parse viewBox
            try:
                txt = data.decode("utf-8", errors="replace")
                import re
                m = re.search(r'viewBox=["\']\s*[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)', txt)
                if m:
                    w, h = float(m.group(1)), float(m.group(2))
                    return (int(w / 2), int(h / 2))
                m = re.search(r'<svg[^>]*width=["\']([\d.]+)', txt)
                m2 = re.search(r'<svg[^>]*height=["\']([\d.]+)', txt)
                if m and m2:
                    w, h = float(m.group(1)), float(m2.group(1))
                    return (int(w / 2), int(h / 2))
            except Exception:
                pass
            return (240, 180) if is_stage else (48, 50)
        # PNG: read header for dimensions
        try:
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                w = int.from_bytes(data[16:20], "big")
                h = int.from_bytes(data[20:24], "big")
                return (w // 2, h // 2)
        except Exception:
            pass
        return (240, 180) if is_stage else (48, 50)

    # =====================================================================
    # Script (hat + body)
    # =====================================================================
    def gen_script(self, script: A.Script) -> None:
        hat = script.hat
        spec = B.HAT_BLOCKS.get(hat.kind)
        if spec is None:
            raise CompileError(f"unknown hat kind: {hat.kind!r}", hat.line)

        # Emit warning for hidden/experimental blocks
        warn = spec.get("_warn")
        if warn:
            import sys
            print(f"WARNING (line {hat.line}): {warn}", file=sys.stderr)

        hat_id = gen_id()
        hat_block: dict = {
            "opcode": spec["opcode"],
            "next": None,
            "parent": None,
            "inputs": {},
            "fields": {},
            "shadow": False,
            "topLevel": True,
            "x": 0,
            "y": 0,
        }

        # Hat fields
        for fname, arg_idx in spec.get("fields", []):
            val = hat.args[arg_idx] if arg_idx < len(hat.args) else ""
            # For broadcast receive hat, the field name is BROADCAST_OPTION
            # and the value is [name, broadcast_id] where broadcast_id is a
            # unique ID that must match the broadcasts dict.
            if hat.kind == "receive":
                # Generate a unique broadcast ID
                bcast_id = gen_id()
                hat_block["fields"]["BROADCAST_OPTION"] = [val, bcast_id]
                # Track the broadcast with its ID
                self.current_broadcasts[bcast_id] = val
            else:
                hat_block["fields"][fname] = [val, None]

        # Hat inputs (for greater_than)
        arg_consumed = 0
        for input_name, input_kind, source in spec.get("args", []):
            # for greater_than, the VALUE comes from args[1]
            if hat.kind == "greater_than":
                val_node = hat.args[1] if len(hat.args) > 1 else A.NumberLit(0)
            else:
                val_node = hat.args[arg_consumed] if arg_consumed < len(hat.args) else None
            arg_consumed += 1
            shadow, block_id = self.gen_input_value(val_node, input_kind)
            hat_block["inputs"][input_name] = self._pack_input(input_kind, shadow, block_id)

        self.current_blocks[hat_id] = hat_block

        # Body
        if script.body:
            first_id, last_id = self.gen_chain(script.body, parent_id=hat_id)
            hat_block["next"] = first_id

    # =====================================================================
    # Statement chain
    # =====================================================================
    def gen_chain(self, stmts: List[A.Statement], parent_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Generate a chain of statements linked via parent/next.
        Returns (first_id, last_id)."""
        if not stmts:
            return None, None
        first_id: Optional[str] = None
        prev_id: Optional[str] = parent_id
        for stmt in stmts:
            top_id, last_id = self.gen_statement(stmt, parent_id=prev_id)
            if top_id is None:
                continue
            if first_id is None:
                first_id = top_id
            if prev_id is not None:
                self.current_blocks[prev_id]["next"] = top_id
            prev_id = last_id
        return first_id, prev_id

    # =====================================================================
    # Statement dispatch
    # =====================================================================
    def gen_statement(self, stmt, parent_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(stmt, A.VarAssign):
            return self.gen_var_assign(stmt, parent_id)
        if isinstance(stmt, A.VarModify):
            return self.gen_var_modify(stmt, parent_id)
        if isinstance(stmt, A.ListOp):
            return self.gen_list_op(stmt, parent_id)
        if isinstance(stmt, A.IfStatement):
            return self.gen_if(stmt, parent_id)
        if isinstance(stmt, A.RepeatStatement):
            return self.gen_repeat(stmt, parent_id)
        if isinstance(stmt, A.RepeatUntilStatement):
            return self.gen_repeat_until(stmt, parent_id)
        if isinstance(stmt, A.ForeverStatement):
            return self.gen_forever(stmt, parent_id)
        if isinstance(stmt, A.WhileStatement):
            return self.gen_while(stmt, parent_id)
        if isinstance(stmt, A.ForEachStatement):
            return self.gen_for_each(stmt, parent_id)
        if isinstance(stmt, A.AllAtOnceStatement):
            return self.gen_all_at_once(stmt, parent_id)
        if isinstance(stmt, A.WaitStatement):
            return self.gen_simple_stack("control_wait",
                                         [("DURATION", "number", stmt.secs)],
                                         parent_id, stmt.line)
        if isinstance(stmt, A.WaitUntilStatement):
            return self.gen_wait_until(stmt, parent_id)
        if isinstance(stmt, A.StopStatement):
            return self.gen_stop(stmt, parent_id)
        if isinstance(stmt, A.BroadcastStatement):
            opcode = "event_broadcastandwait" if stmt.wait else "event_broadcast"
            # message must be a broadcast input - if it's a literal string,
            # we need to create a broadcast msg
            msg = self._resolve_broadcast_msg(stmt.msg)
            return self.gen_simple_stack(opcode,
                                         [("BROADCAST_INPUT", "broadcast", msg)],
                                         parent_id, stmt.line)
        if isinstance(stmt, A.BlockCall):
            return self.gen_block_call(stmt, parent_id)
        if isinstance(stmt, A.LocalVarDecl):
            return self.gen_var_assign(
                A.VarAssign(name=stmt.name, value=stmt.value, line=stmt.line),
                parent_id
            )
        raise CompileError(f"unknown statement type: {type(stmt).__name__}", stmt.line)

    def gen_simple_stack(self, opcode: str, inputs_spec, parent_id, line) -> Tuple[str, str]:
        """Generate a simple stack block with the given inputs.

        inputs_spec: list of (input_name, input_kind, value_node_or_string)
        """
        block_id = gen_id()
        inputs: Dict[str, list] = {}
        for input_name, input_kind, val in inputs_spec:
            # If val is already a string (e.g. broadcast msg), use as literal
            if isinstance(val, str):
                if input_kind == "broadcast":
                    shadow = [SHADOW_BROADCAST, val]
                    inputs[input_name] = [1, shadow]
                else:
                    shadow = [SHADOW_STRING, val]
                    inputs[input_name] = [1, shadow]
            else:
                shadow, sub = self.gen_input_value(val, input_kind)
                inputs[input_name] = self._pack_input(input_kind, shadow, sub)
        self.current_blocks[block_id] = {
            "opcode": opcode,
            "next": None, "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        return block_id, block_id

    def _is_boolean_expr(self, expr) -> bool:
        """Check if an expression is a boolean (for condition coercion)."""
        if isinstance(expr, A.BinOp):
            return expr.op in (">", "<", "=", "!=", ">=", "<=", "and", "or")
        if isinstance(expr, A.UnaryOp):
            return expr.op == "not"
        if isinstance(expr, A.FuncCall):
            # Check if it returns a boolean
            spec = B.REPORTERS.get(expr.name)
            if spec and spec.get("returns") == "boolean":
                return True
            # List.contains returns boolean
            return False
        if isinstance(expr, A.BuiltinRef):
            spec = B.REPORTERS.get(expr.name)
            if spec and spec.get("returns") == "boolean":
                return True
            return False
        if isinstance(expr, A.BareRef):
            # Could resolve to a boolean reporter - check
            lower = expr.name.lower()
            if lower in B.BUILTIN_ALIASES:
                spec = B.REPORTERS.get(B.BUILTIN_ALIASES[lower])
                if spec and spec.get("returns") == "boolean":
                    return True
            return False
        if isinstance(expr, A.ListReporterRef):
            return expr.method == "contains"
        if isinstance(expr, A.ArgumentRef):
            arg_type = getattr(expr, "_arg_type", "string")
            return arg_type == "boolean"
        return False

    def _coerce_condition(self, expr):
        """Coerce a non-boolean expression to boolean (like goboscript).
        If the expression is not boolean, wrap it in `expr = true` so that
        non-boolean values don't always evaluate to truthy."""
        if self._is_boolean_expr(expr):
            return expr
        # Wrap in (expr = true)
        return A.BinOp(op="=", left=expr, right=A.StringLit(value="true"), line=getattr(expr, 'line', 0))

    def gen_wait_until(self, stmt: A.WaitUntilStatement, parent_id: Optional[str]):
        """control_wait_until - has a CONDITION input (boolean)."""
        cond = self._coerce_condition(stmt.cond)
        shadow_c, sub_c = self.gen_input_value(cond, "boolean")
        cond_input = self._pack_input("boolean", shadow_c, sub_c)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_wait_until",
            "next": None, "parent": parent_id,
            "inputs": {"CONDITION": cond_input},
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        return block_id, block_id

    # ---- variable assignment ---------------------------------------------
    def gen_var_assign(self, stmt: A.VarAssign, parent_id: Optional[str]):
        # Ensure var is declared
        if stmt.name not in self.current_vars:
            self._declare_var(stmt.name, stmt.value)
        vid = self.current_vars[stmt.name]
        block_id = gen_id()
        shadow, sub_block = self.gen_input_value(stmt.value, "any")
        inp = self._pack_input("any", shadow, sub_block)
        self.current_blocks[block_id] = {
            "opcode": "data_setvariableto",
            "next": None,
            "parent": parent_id,
            "inputs": {"VALUE": inp},
            "fields": {"VARIABLE": [stmt.name, vid]},
            "shadow": False,
            "topLevel": False,
        }
        return block_id, block_id

    def gen_var_modify(self, stmt: A.VarModify, parent_id: Optional[str]):
        if stmt.name not in self.current_vars:
            self._declare_var(stmt.name, 0)
        vid = self.current_vars[stmt.name]
        # Compile += as: set var to (var + value), -= as set var to (var - value), etc.
        # Actually Scratch has data_changevariableby only for +=.
        # For -=, we need: change var by (0 - value)
        # For *=, /= : set var to (var * value)
        if stmt.op == "+=":
            block_id = gen_id()
            shadow, sub_block = self.gen_input_value(stmt.value, "number")
            inp = self._pack_input("number", shadow, sub_block)
            self.current_blocks[block_id] = {
                "opcode": "data_changevariableby",
                "next": None,
                "parent": parent_id,
                "inputs": {"VALUE": inp},
                "fields": {"VARIABLE": [stmt.name, vid]},
                "shadow": False,
                "topLevel": False,
            }
            return block_id, block_id
        else:
            # General case: set var to (var OP value)
            op_map = {"+=": "+", "-=": "-", "*=": "*", "/=": "/"}
            op = op_map[stmt.op]
            var_ref = A.VarRef(name=stmt.name, line=stmt.line)
            new_value = A.BinOp(op=op, left=var_ref, right=stmt.value, line=stmt.line)
            return self.gen_var_assign(A.VarAssign(name=stmt.name, value=new_value, line=stmt.line), parent_id)

    # ---- list operations --------------------------------------------------
    def gen_list_op(self, stmt: A.ListOp, parent_id: Optional[str]):
        if stmt.list_name not in self.current_lists:
            # auto-declare
            lid = gen_id()
            self.current_lists[stmt.list_name] = lid
            self.current_list_values[stmt.list_name] = []
        lid = self.current_lists[stmt.list_name]

        if stmt.op == "add":
            # data_addtolist: LIST, ITEM  (ITEM is required)
            if not stmt.args:
                raise CompileError(
                    f'{stmt.list_name}.add() requires an argument, '
                    f'e.g. {stmt.list_name}.add(item)',
                    stmt.line
                )
            shadow, sub = self.gen_input_value(stmt.args[0], "string")
            inp = self._pack_input("string", shadow, sub)
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_addtolist",
                "next": None, "parent": parent_id,
                "inputs": {"ITEM": inp},
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        if stmt.op == "delete":
            # data_deleteoflist: LIST, INDEX  (INDEX is required)
            # special: index "all" -> data_deletealloflist
            if stmt.args and isinstance(stmt.args[0], A.BareRef) and stmt.args[0].name.lower() == "all":
                block_id = gen_id()
                self.current_blocks[block_id] = {
                    "opcode": "data_deletealloflist",
                    "next": None, "parent": parent_id,
                    "inputs": {},
                    "fields": {"LIST": [stmt.list_name, lid]},
                    "shadow": False, "topLevel": False,
                }
                return block_id, block_id
            if not stmt.args:
                raise CompileError(
                    f'{stmt.list_name}.delete() requires an index argument, '
                    f'e.g. {stmt.list_name}.delete(1) or {stmt.list_name}.delete(all)',
                    stmt.line
                )
            shadow, sub = self.gen_input_value(stmt.args[0], "number")
            inp = self._pack_input("number", shadow, sub)
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_deleteoflist",
                "next": None, "parent": parent_id,
                "inputs": {"INDEX": inp},
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        if stmt.op == "insert":
            # data_insertatlist: LIST, INDEX, ITEM  (both required)
            # Syntax: list.insert(item, index)
            if len(stmt.args) < 2:
                raise CompileError(
                    f'{stmt.list_name}.insert() requires 2 arguments: '
                    f'item and index, e.g. {stmt.list_name}.insert(item, 1)',
                    stmt.line
                )
            shadow_idx, sub_idx = self.gen_input_value(stmt.args[1], "number")
            shadow_item, sub_item = self.gen_input_value(stmt.args[0], "string")
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_insertatlist",
                "next": None, "parent": parent_id,
                "inputs": {
                    "INDEX": self._pack_input("number", shadow_idx, sub_idx),
                    "ITEM": self._pack_input("string", shadow_item, sub_item),
                },
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        if stmt.op == "replace":
            # data_replaceitemoflist: LIST, INDEX, ITEM  (both required)
            # Syntax: list.replace(index, item)
            if len(stmt.args) < 2:
                raise CompileError(
                    f'{stmt.list_name}.replace() requires 2 arguments: '
                    f'index and item, e.g. {stmt.list_name}.replace(1, item)',
                    stmt.line
                )
            shadow_idx, sub_idx = self.gen_input_value(stmt.args[0], "number")
            shadow_item, sub_item = self.gen_input_value(stmt.args[1], "string")
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_replaceitemoflist",
                "next": None, "parent": parent_id,
                "inputs": {
                    "INDEX": self._pack_input("number", shadow_idx, sub_idx),
                    "ITEM": self._pack_input("string", shadow_item, sub_item),
                },
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        if stmt.op == "show":
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_showlist",
                "next": None, "parent": parent_id,
                "inputs": {},
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        if stmt.op == "hide":
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": "data_hidelist",
                "next": None, "parent": parent_id,
                "inputs": {},
                "fields": {"LIST": [stmt.list_name, lid]},
                "shadow": False, "topLevel": False,
            }
            return block_id, block_id
        raise CompileError(f"unknown list op: {stmt.op}", stmt.line)

    # ---- control flow -----------------------------------------------------
    def gen_if(self, stmt: A.IfStatement, parent_id: Optional[str]):
        cond = self._coerce_condition(stmt.cond)
        shadow_cond, sub_cond = self.gen_input_value(cond, "boolean")
        cond_input = self._pack_input("boolean", shadow_cond, sub_cond)
        then_first, then_last = self.gen_chain(stmt.then_body, parent_id=None)
        block_id = gen_id()
        inputs = {
            "CONDITION": cond_input,
            "SUBSTACK": self._pack_substack(then_first),
        }
        if stmt.else_body:
            else_first, else_last = self.gen_chain(stmt.else_body, parent_id=None)
            inputs["SUBSTACK2"] = self._pack_substack(else_first)
        self.current_blocks[block_id] = {
            "opcode": "control_if_else" if stmt.else_body else "control_if",
            "next": None, "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        # Fix parents of substack chain
        if then_first is not None:
            self.current_blocks[then_first]["parent"] = block_id
        if stmt.else_body and else_first is not None:
            self.current_blocks[else_first]["parent"] = block_id
        return block_id, block_id

    def gen_repeat(self, stmt: A.RepeatStatement, parent_id: Optional[str]):
        shadow_t, sub_t = self.gen_input_value(stmt.times, "number")
        body_first, body_last = self.gen_chain(stmt.body, parent_id=None)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_repeat",
            "next": None, "parent": parent_id,
            "inputs": {
                "TIMES": self._pack_input("number", shadow_t, sub_t),
                "SUBSTACK": self._pack_substack(body_first),
            },
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = block_id
        return block_id, block_id

    def gen_repeat_until(self, stmt: A.RepeatUntilStatement, parent_id: Optional[str]):
        cond = self._coerce_condition(stmt.cond)
        shadow_c, sub_c = self.gen_input_value(cond, "boolean")
        body_first, body_last = self.gen_chain(stmt.body, parent_id=None)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_repeat_until",
            "next": None, "parent": parent_id,
            "inputs": {
                "CONDITION": self._pack_input("boolean", shadow_c, sub_c),
                "SUBSTACK": self._pack_substack(body_first),
            },
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = block_id
        return block_id, block_id

    def gen_forever(self, stmt: A.ForeverStatement, parent_id: Optional[str]):
        body_first, body_last = self.gen_chain(stmt.body, parent_id=None)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_forever",
            "next": None, "parent": parent_id,
            "inputs": {"SUBSTACK": self._pack_substack(body_first)},
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = block_id
        # forever has no "next" - it loops forever
        return block_id, block_id

    def gen_while(self, stmt: A.WhileStatement, parent_id: Optional[str]):
        # while (c) { body } => repeatUntil (not c) { body }
        new_cond = A.UnaryOp(op="not", operand=stmt.cond, line=stmt.line)
        ru = A.RepeatUntilStatement(cond=new_cond, body=stmt.body, line=stmt.line)
        return self.gen_repeat_until(ru, parent_id)

    def gen_for_each(self, stmt: A.ForEachStatement, parent_id: Optional[str]):
        """control_for_each: VALUE input (count), VARIABLE field, SUBSTACK input.

        The VARIABLE field uses the [name, id] format like a variable
        reference, so the loop counter variable must be declared.
        """
        if stmt.var_name not in self.current_vars:
            self._declare_var(stmt.var_name, 0)
        vid = self.current_vars[stmt.var_name]
        var_field = [stmt.var_name, vid]

        shadow_c, sub_c = self.gen_input_value(stmt.count, "number")
        body_first, body_last = self.gen_chain(stmt.body, parent_id=None)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_for_each",
            "next": None, "parent": parent_id,
            "inputs": {
                "VALUE": self._pack_input("number", shadow_c, sub_c),
                "SUBSTACK": self._pack_substack(body_first),
            },
            "fields": {"VARIABLE": var_field},
            "shadow": False, "topLevel": False,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = block_id
        return block_id, block_id

    def gen_all_at_once(self, stmt: A.AllAtOnceStatement, parent_id: Optional[str]):
        """control_all_at_once: SUBSTACK input only."""
        body_first, body_last = self.gen_chain(stmt.body, parent_id=None)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_all_at_once",
            "next": None, "parent": parent_id,
            "inputs": {"SUBSTACK": self._pack_substack(body_first)},
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = block_id
        return block_id, block_id

    def gen_stop(self, stmt: A.StopStatement, parent_id: Optional[str]):
        kind = B.STOP_OPTIONS.get(stmt.kind.lower(), stmt.kind)
        block_id = gen_id()
        self.current_blocks[block_id] = {
            "opcode": "control_stop",
            "next": None, "parent": parent_id,
            "inputs": {},
            "fields": {"STOP_OPTION": [kind, None]},
            "shadow": False, "topLevel": False,
        }
        return block_id, block_id

    def gen_broadcast(self, stmt: A.BroadcastStatement, parent_id: Optional[str]):
        opcode = "event_broadcastandwait" if stmt.wait else "event_broadcast"
        msg = self._resolve_broadcast_msg(stmt.msg)
        # Generate a unique broadcast ID for this message
        bcast_id = gen_id()
        self.current_broadcasts[bcast_id] = msg
        block_id = gen_id()
        # Broadcast input: [shadow_type, [shadow_type, name, id]]
        # The format is [1, [11, name, id]] where 11 = SHADOW_BROADCAST
        shadow = [SHADOW_BROADCAST, msg, bcast_id]
        self.current_blocks[block_id] = {
            "opcode": opcode,
            "next": None, "parent": parent_id,
            "inputs": {"BROADCAST_INPUT": [1, shadow]},
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        return block_id, block_id

    def _resolve_broadcast_msg(self, msg_node) -> str:
        if isinstance(msg_node, A.StringLit):
            msg = msg_node.value
        elif isinstance(msg_node, A.BareRef):
            msg = msg_node.name
        elif isinstance(msg_node, A.NumberLit):
            msg = str(msg_node.value)
        else:
            # complex expr - use a placeholder
            msg = "message"
        return msg

    # ---- generic stack block from table ----------------------------------
    def gen_block_call(self, stmt: A.BlockCall, parent_id: Optional[str]):
        # Resolve the key: "namespace.method" or "method"
        if stmt.namespace:
            key = f"{stmt.namespace}.{stmt.method}"
        else:
            key = stmt.method

        # Special: say/think without post parens
        effective_key = key
        if key in ("say", "think") and not stmt.post:
            effective_key = key + "_"

        # Custom block call?
        if not stmt.namespace and stmt.method in self.current_custom_blocks:
            # Check argument count
            cb_info = self.current_custom_blocks[stmt.method]
            expected_args = len(cb_info.get("argument_ids", []))
            actual_args = len(stmt.args)
            if actual_args != expected_args:
                raise ArgumentOops(
                    f'"{stmt.method}" expected {expected_args} argument(s) '
                    f'but {actual_args} were given',
                    stmt.line
                )
            return self.gen_custom_block_call(stmt, parent_id)

        # If it looks like a custom block call but isn't defined, raise ForgotOops
        if not stmt.namespace and stmt.method not in B.STACK_BLOCKS:
            if stmt.method in self._all_custom_blocks:
                # Defined in another sprite - that's OK, just not in this one
                pass
            else:
                suggestion = did_you_mean(stmt.method, self._all_custom_blocks)
                raise ForgotOops(
                    f'You forgot to define custom block "{stmt.method}"{suggestion}',
                    stmt.line
                )

        spec = B.STACK_BLOCKS.get(effective_key)
        if spec is None:
            all_keys = list(B.STACK_BLOCKS.keys()) + list(self.current_custom_blocks.keys())
            suggestion = did_you_mean(key, all_keys)
            raise CompileError(
                f'"{key}" is not valid TypeScratch syntax{suggestion}'
                + (f"  (did you mean to use it as a custom block?)" if not stmt.namespace and not suggestion else ""),
                stmt.line
            )

        # Emit warning for hidden/experimental blocks
        warn = spec.get("_warn")
        if warn:
            import sys
            print(f"WARNING (line {stmt.line}): {warn}", file=sys.stderr)

        # Count clone creation for the clone limit warning
        # We count each createCloneOf block; if it's inside a repeat(N)
        # with a literal N, we multiply.
        if spec["opcode"] == "control_create_clone_of":
            # Check if parent is a repeat with a literal count
            # (We can't easily check this here, so we just count the block)
            # The warning fires if there are many clone blocks OR if the
            # project seems clone-heavy.
            self._clone_count += 1

        block_id = gen_id()
        inputs: Dict[str, list] = {}
        fields: Dict[str, list] = {}

        # Consume args from stmt.args and stmt.post in order
        args_iter = list(stmt.args)
        post_iter = list(stmt.post or [])
        arg_idx = 0
        post_idx = 0

        # First, fields that come from args (None value)
        for fname, fval in spec.get("fields", []):
            if fval is None:
                # value comes from next arg
                if arg_idx < len(args_iter):
                    val_node = args_iter[arg_idx]
                    arg_idx += 1
                    fields[fname] = [self._resolve_field_value(val_node, fname), None]
                else:
                    fields[fname] = ["", None]
            else:
                fields[fname] = [fval, None]

        # Then, args (inputs)
        for spec_entry in spec.get("args", []):
            input_name = spec_entry[0]
            input_kind = spec_entry[1]
            source = spec_entry[2] if len(spec_entry) > 2 else "args"
            optional = spec_entry[3] if len(spec_entry) > 3 else False

            if source == "args":
                if arg_idx < len(args_iter):
                    val_node = args_iter[arg_idx]
                    arg_idx += 1
                    shadow, sub = self.gen_input_value(val_node, input_kind)
                    inputs[input_name] = self._pack_input(input_kind, shadow, sub)
                elif post_idx < len(post_iter):
                    # Allow falling through to post parens if args are exhausted.
                    # This lets users write `changeEffect(color)(25)` as well as
                    # `changeEffect(color, 25)`.
                    val_node = post_iter[post_idx]
                    post_idx += 1
                    shadow, sub = self.gen_input_value(val_node, input_kind)
                    inputs[input_name] = self._pack_input(input_kind, shadow, sub)
                elif optional:
                    # provide default
                    shadow, sub = self.gen_input_value(A.NumberLit(1), input_kind)
                    inputs[input_name] = self._pack_input(input_kind, shadow, sub)
                else:
                    raise CompileError(
                        f"block {key!r} expects more arguments (input {input_name!r})",
                        stmt.line
                    )
            elif source == "post":
                if post_idx < len(post_iter):
                    val_node = post_iter[post_idx]
                    post_idx += 1
                    shadow, sub = self.gen_input_value(val_node, input_kind)
                    inputs[input_name] = self._pack_input(input_kind, shadow, sub)
                elif arg_idx < len(args_iter):
                    # Allow falling back to args
                    val_node = args_iter[arg_idx]
                    arg_idx += 1
                    shadow, sub = self.gen_input_value(val_node, input_kind)
                    inputs[input_name] = self._pack_input(input_kind, shadow, sub)
                else:
                    raise CompileError(
                        f"block {key!r} expects a post-paren argument for {input_name!r} "
                        f"(e.g. {key}(...)(value))",
                        stmt.line
                    )

        # Special handling: if we have extra args for a string input, join them
        # This handles `say(Hello, World!)` where MESSAGE should be "Hello, World!"
        if arg_idx < len(args_iter):
            # find a string input we already filled and re-join
            for spec_entry in spec.get("args", []):
                input_name = spec_entry[0]
                input_kind = spec_entry[1]
                source = spec_entry[2] if len(spec_entry) > 2 else "args"
                if input_kind in ("string", "any") and source == "args" and arg_idx < len(args_iter):
                    # Re-join: get the existing value and append remaining args
                    existing = inputs.get(input_name)
                    # existing is packed; we'll just create a new joined string
                    existing_val = ""
                    if existing and len(existing) > 1:
                        prim = existing[1]
                        if isinstance(prim, list) and len(prim) > 1:
                            existing_val = prim[1]
                    parts = [str(existing_val)]
                    while arg_idx < len(args_iter):
                        v = args_iter[arg_idx]
                        arg_idx += 1
                        parts.append(self._stringify(v))
                    joined = ", ".join(parts) if parts[0] else ", ".join(parts[1:])
                    shadow = [SHADOW_STRING, joined]
                    inputs[input_name] = [1, shadow]

        self.current_blocks[block_id] = {
            "opcode": spec["opcode"],
            "next": None, "parent": parent_id,
            "inputs": inputs,
            "fields": fields,
            "shadow": False, "topLevel": False,
        }
        return block_id, block_id

    def _resolve_field_value(self, val_node, fname: str) -> str:
        """Resolve an arg to a field value (string)."""
        if isinstance(val_node, A.StringLit):
            return val_node.value
        if isinstance(val_node, A.NumberLit):
            return str(val_node.value)
        if isinstance(val_node, A.BareRef):
            return val_node.name
        if isinstance(val_node, A.ColorLit):
            return val_node.value
        # Handle BinOp with minus (e.g. "left-right" parsed as left - right)
        # This happens because - is no longer in IDENT_EXTRA for ++/-- support
        if isinstance(val_node, A.BinOp) and val_node.op == "-":
            left = self._resolve_field_value(val_node.left, fname)
            right = self._resolve_field_value(val_node.right, fname)
            return f"{left}-{right}"
        raise CompileError(f"cannot use complex expression as field value for {fname!r}", val_node.line if hasattr(val_node, 'line') else 0)

    def _stringify(self, val_node) -> str:
        if isinstance(val_node, A.StringLit):
            return val_node.value
        if isinstance(val_node, A.NumberLit):
            return str(val_node.value)
        if isinstance(val_node, A.BareRef):
            return val_node.name
        if isinstance(val_node, A.ColorLit):
            return val_node.value
        return ""

    # ---- custom blocks ----------------------------------------------------
    def gen_custom_block_def(self, cb: A.CustomBlockDef) -> None:
        # Build proccode: "name %s %n %b" based on param types
        type_codes = {"string": "%s", "number": "%n", "boolean": "%b"}
        proccode = cb.name + "".join(" " + type_codes.get(p["type"], "%s") for p in cb.params)
        argument_ids = [gen_id() for _ in cb.params]
        argument_names = [p["name"] for p in cb.params]
        argument_defaults = []
        for p in cb.params:
            if p["type"] == "number":
                argument_defaults.append(0)
            elif p["type"] == "boolean":
                argument_defaults.append(False)
            else:
                argument_defaults.append("")

        self.current_custom_blocks[cb.name] = {
            "proccode": proccode,
            "argument_ids": argument_ids,
            "argument_names": argument_names,
            "argument_defaults": argument_defaults,
            "warp": cb.warp,
        }

        # Generate the prototype block (procedures_prototype)
        # In real Scratch, the prototype has EMPTY inputs and shadow=false.
        # The argument info lives entirely in the mutation.
        proto_id = gen_id()
        proto_block = {
            "opcode": "procedures_prototype",
            "next": None,
            "parent": None,
            "inputs": {},
            "fields": {},
            "shadow": False,
            "topLevel": False,
        }
        # mutation - this is where the argument info lives
        proto_block["mutation"] = {
            "tagName": "mutation",
            "children": [],
            "proccode": proccode,
            "argumentids": "[]",
            "warp": "true" if cb.warp else "false",
            "argumentdefaults": "[]",
            "argumentnames": "[]",
        }
        # JSON-encode the lists for mutation
        import json as _json
        proto_block["mutation"]["argumentids"] = _json.dumps(argument_ids)
        proto_block["mutation"]["argumentdefaults"] = _json.dumps(argument_defaults)
        proto_block["mutation"]["argumentnames"] = _json.dumps(argument_names)

        self.current_blocks[proto_id] = proto_block

        # Generate the definition block (procedures_definition)
        def_id = gen_id()
        # Set the current proc params so body expressions can resolve
        # parameter names to argument_reporter blocks.
        old_params = self.current_proc_params
        self.current_proc_params = {
            p["name"]: {"arg_id": arg_id, "type": p["type"]}
            for p, arg_id in zip(cb.params, argument_ids)
        }
        # The custom block body is the chain inside the def
        body_first, body_last = self.gen_chain(cb.body, parent_id=None)
        self.current_proc_params = old_params

        self.current_blocks[def_id] = {
            "opcode": "procedures_definition",
            "next": body_first,
            "parent": None,
            "inputs": {"custom_block": [2, proto_id]},
            "fields": {},
            "shadow": False,
            "topLevel": True,
            "x": 0,
            "y": 0,
        }
        if body_first is not None:
            self.current_blocks[body_first]["parent"] = def_id

        # Store the body_first for reference (for calls that need to know)
        self.current_custom_blocks[cb.name]["def_block_id"] = def_id
        self.current_custom_blocks[cb.name]["proto_block_id"] = proto_id

    def gen_custom_block_call(self, stmt: A.BlockCall, parent_id: Optional[str]):
        info = self.current_custom_blocks[stmt.method]
        block_id = gen_id()
        # arguments: each input is one of the argument_ids
        inputs = {}
        for arg_id, arg_node in zip(info["argument_ids"], stmt.args):
            # determine kind from param type
            param_types = info.get("argument_types") or ["string"] * len(info["argument_ids"])
            # actually we need the param types - re-derive from proccode? store them
            # We'll use 'any' to be flexible
            shadow, sub = self.gen_input_value(arg_node, "any")
            inputs[arg_id] = self._pack_input("any", shadow, sub)
        self.current_blocks[block_id] = {
            "opcode": "procedures_call",
            "next": None, "parent": parent_id,
            "inputs": inputs,
            "fields": {},
            "shadow": False, "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "proccode": info["proccode"],
                "argumentids": _json_dumps(info["argument_ids"]),
                "warp": "true" if info["warp"] else "false",
            },
        }
        return block_id, block_id

    # =====================================================================
    # Expressions
    # =====================================================================
    def gen_input_value(self, expr, kind: str) -> Tuple[Optional[list], Optional[str]]:
        """Generate an input value.
        Returns (shadow_primitive, block_id_or_None).
        One of them is None:
          - For literal shadow: ([prim_type, value], None)
          - For block input: (None, block_id)
          - For variable: ([12, name, id], None) - and we'll pack as [3, ...]
        """
        if expr is None:
            return self._default_shadow(kind), None

        # Plain Python values (str, int, float) - happen when broadcast
        # messages come back as strings, etc.
        if isinstance(expr, str):
            if kind == "broadcast":
                self.current_broadcasts[expr] = expr
                return [SHADOW_BROADCAST, expr], None
            return [SHADOW_STRING, expr], None
        if isinstance(expr, (int, float)):
            return [SHADOW_NUMBER, str(expr)], None

        # Resolve BareRef first
        if isinstance(expr, A.BareRef):
            expr = self._resolve_bare_ref(expr)

        if isinstance(expr, A.NumberLit):
            val = expr.value
            return [SHADOW_NUMBER, str(val)], None
        if isinstance(expr, A.StringLit):
            return [SHADOW_STRING, expr.value], None
        if isinstance(expr, A.ColorLit):
            return [SHADOW_COLOR, expr.value], None
        if isinstance(expr, A.VarRef):
            vid = self.current_vars.get(expr.name)
            if vid is None:
                # auto-declare (shouldn't normally happen)
                self._declare_var(expr.name, 0)
                vid = self.current_vars[expr.name]
            return [SHADOW_VAR, expr.name, vid], None
        if isinstance(expr, A.ArgumentRef):
            # Generate an argument_reporter block.
            # In real Scratch, argument_reporter blocks inside a custom block
            # body have shadow=false (they're real blocks, not shadows).
            arg_type = getattr(expr, "_arg_type", "string")
            opcode = "argument_reporter_boolean" if arg_type == "boolean" else "argument_reporter_string_number"
            block_id = gen_id()
            self.current_blocks[block_id] = {
                "opcode": opcode,
                "next": None, "parent": None,
                "inputs": {},
                "fields": {"VALUE": [expr.name, None]},
                "shadow": False, "topLevel": False,
            }
            return None, block_id
        if isinstance(expr, A.ListReporterRef):
            return self._gen_list_reporter(expr)
        if isinstance(expr, A.TernaryExpr):
            return self._gen_ternary(expr)
        if isinstance(expr, A.BuiltinRef):
            # Builtin reporter (e.g. answer, mouseX)
            spec = B.REPORTERS.get(expr.name)
            if spec is None:
                # try alias
                alias = B.BUILTIN_ALIASES.get(expr.name.lower())
                if alias:
                    spec = B.REPORTERS.get(alias)
            if spec is None:
                suggestion = did_you_mean(expr.name, B.REPORTERS.keys())
                raise CompileError(
                    f'"{expr.name}" is not valid TypeScratch syntax{suggestion}',
                    expr.line
                )
            return self._gen_reporter_block(spec, [], expr.line)
        if isinstance(expr, A.FuncCall):
            # Could be: reporter (pickRandom, join, abs, etc.)
            # or math op like Math.abs
            name = expr.name
            spec = B.REPORTERS.get(name)
            if spec is None:
                # try alias
                alias = B.BUILTIN_ALIASES.get(name.lower())
                if alias:
                    spec = B.REPORTERS.get(alias)
            if spec is None:
                suggestion = did_you_mean(name, B.REPORTERS.keys())
                raise CompileError(
                    f'"{name}" is not valid TypeScratch syntax{suggestion}',
                    expr.line
                )
            return self._gen_reporter_block(spec, expr.args, expr.line)
        if isinstance(expr, A.BinOp):
            return self._gen_binop(expr)
        if isinstance(expr, A.UnaryOp):
            return self._gen_unaryop(expr)
        raise CompileError(f"cannot generate expression: {type(expr).__name__}", getattr(expr, 'line', 0))

    def _resolve_bare_ref(self, ref: A.BareRef):
        """Resolve a BareRef into VarRef / ArgumentRef / BuiltinRef / StringLit."""
        name = ref.name
        if name in self.current_vars:
            return A.VarRef(name=name, line=ref.line)
        # custom block parameter?
        if name in self.current_proc_params:
            param_info = self.current_proc_params[name]
            ref = A.ArgumentRef(name=name, arg_id=param_info["arg_id"], line=ref.line)
            ref._arg_type = param_info["type"]
            return ref
        # check builtin aliases (case-insensitive)
        lower = name.lower()
        if lower in B.BUILTIN_ALIASES:
            return A.BuiltinRef(name=B.BUILTIN_ALIASES[lower], line=ref.line)
        # check direct reporter name
        if name in B.REPORTERS:
            return A.BuiltinRef(name=name, line=ref.line)
        # default: string literal
        return A.StringLit(value=name, line=ref.line)

    def _gen_ternary(self, expr: A.TernaryExpr) -> Tuple[Optional[list], Optional[str]]:
        """Generate a ternary expression [if (cond) x else y].

        This is desugared into: a temp variable, set by an if/else.
        We create the if/else blocks inline and return a VarRef to the temp.
        """
        # Create a temp variable
        tmp_name = f"_ternary_{gen_id()[:8]}"
        self._declare_var(tmp_name, 0)
        vid = self.current_vars[tmp_name]

        # Coerce the condition
        cond = self._coerce_condition(expr.cond)
        shadow_cond, sub_cond = self.gen_input_value(cond, "boolean")
        cond_input = self._pack_input("boolean", shadow_cond, sub_cond)

        # Generate the true branch: set tmp = true_expr
        true_shadow, true_sub = self.gen_input_value(expr.true_expr, "any")
        true_block_id = gen_id()
        self.current_blocks[true_block_id] = {
            "opcode": "data_setvariableto",
            "next": None, "parent": None,
            "inputs": {"VALUE": self._pack_input("any", true_shadow, true_sub)},
            "fields": {"VARIABLE": [tmp_name, vid]},
            "shadow": False, "topLevel": False,
        }

        # Generate the false branch: set tmp = false_expr
        false_shadow, false_sub = self.gen_input_value(expr.false_expr, "any")
        false_block_id = gen_id()
        self.current_blocks[false_block_id] = {
            "opcode": "data_setvariableto",
            "next": None, "parent": None,
            "inputs": {"VALUE": self._pack_input("any", false_shadow, false_sub)},
            "fields": {"VARIABLE": [tmp_name, vid]},
            "shadow": False, "topLevel": False,
        }

        # Generate the if/else block
        if_block_id = gen_id()
        self.current_blocks[if_block_id] = {
            "opcode": "control_if_else",
            "next": None, "parent": None,
            "inputs": {
                "CONDITION": cond_input,
                "SUBSTACK": [2, true_block_id],
                "SUBSTACK2": [2, false_block_id],
            },
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        self.current_blocks[true_block_id]["parent"] = if_block_id
        self.current_blocks[false_block_id]["parent"] = if_block_id

        # Return a variable reference to the temp
        return [SHADOW_VAR, tmp_name, vid], None

    def _gen_list_reporter(self, expr: A.ListReporterRef) -> Tuple[Optional[list], Optional[str]]:
        """Generate a list reporter block (data_itemoflist, data_lengthoflist,
        data_listcontainsitem, data_itemnumoflist, data_listcontents).

        The list reference is a FIELD with [name, id] format."""
        # Make sure the list is declared
        if expr.list_name not in self.current_lists:
            lid = gen_id()
            self.current_lists[expr.list_name] = lid
            self.current_list_values[expr.list_name] = []
        lid = self.current_lists[expr.list_name]
        list_field = [expr.list_name, lid]

        method = expr.method
        # Normalize aliases
        if method == "itemNumber":
            method = "itemNum"
        if method == "asString":
            method = "contents"

        block_id = gen_id()

        if method == "item":
            # data_itemoflist: INDEX input, LIST field  (INDEX is required)
            if not expr.args:
                raise CompileError(
                    f'{expr.list_name}.item() requires an index argument, '
                    f'e.g. {expr.list_name}.item(1)',
                    expr.line
                )
            idx_node = expr.args[0]
            shadow, sub = self.gen_input_value(idx_node, "number")
            self.current_blocks[block_id] = {
                "opcode": "data_itemoflist",
                "next": None, "parent": None,
                "inputs": {"INDEX": self._pack_input("number", shadow, sub)},
                "fields": {"LIST": list_field},
                "shadow": False, "topLevel": False,
            }
            return None, block_id

        if method == "length":
            # data_lengthoflist: just LIST field
            self.current_blocks[block_id] = {
                "opcode": "data_lengthoflist",
                "next": None, "parent": None,
                "inputs": {},
                "fields": {"LIST": list_field},
                "shadow": False, "topLevel": False,
            }
            return None, block_id

        if method == "contains":
            # data_listcontainsitem: ITEM input, LIST field  (ITEM is required)
            if not expr.args:
                raise CompileError(
                    f'{expr.list_name}.contains() requires an argument, '
                    f'e.g. {expr.list_name}.contains(item)',
                    expr.line
                )
            item_node = expr.args[0]
            shadow, sub = self.gen_input_value(item_node, "string")
            self.current_blocks[block_id] = {
                "opcode": "data_listcontainsitem",
                "next": None, "parent": None,
                "inputs": {"ITEM": self._pack_input("string", shadow, sub)},
                "fields": {"LIST": list_field},
                "shadow": False, "topLevel": False,
            }
            return None, block_id

        if method == "itemNum":
            # data_itemnumoflist: ITEM input, LIST field  (ITEM is required)
            if not expr.args:
                raise CompileError(
                    f'{expr.list_name}.itemNum() requires an argument, '
                    f'e.g. {expr.list_name}.itemNum(item)',
                    expr.line
                )
            item_node = expr.args[0]
            shadow, sub = self.gen_input_value(item_node, "string")
            self.current_blocks[block_id] = {
                "opcode": "data_itemnumoflist",
                "next": None, "parent": None,
                "inputs": {"ITEM": self._pack_input("string", shadow, sub)},
                "fields": {"LIST": list_field},
                "shadow": False, "topLevel": False,
            }
            return None, block_id

        if method == "contents":
            # data_listcontents: just LIST field
            self.current_blocks[block_id] = {
                "opcode": "data_listcontents",
                "next": None, "parent": None,
                "inputs": {},
                "fields": {"LIST": list_field},
                "shadow": False, "topLevel": False,
            }
            return None, block_id

        raise CompileError(
            f"unknown list reporter method: {method!r}  "
            f"(supported: item, length, contains, itemNum, contents)",
            expr.line
        )

    def _gen_reporter_block(self, spec, args, line) -> Tuple[Optional[list], Optional[str]]:
        # Emit warning for hidden/experimental reporters
        warn = spec.get("_warn")
        if warn:
            import sys
            print(f"WARNING (line {line}): {warn}", file=sys.stderr)

        block_id = gen_id()
        inputs = {}
        fields = {}
        arg_idx = 0
        for fname, fval in spec.get("fields", []):
            if fval is None:
                if arg_idx < len(args):
                    val_node = args[arg_idx]
                    arg_idx += 1
                    fields[fname] = [self._resolve_field_value(val_node, fname), None]
                else:
                    fields[fname] = ["", None]
            else:
                fields[fname] = [fval, None]
        for spec_entry in spec.get("args", []):
            input_name = spec_entry[0]
            input_kind = spec_entry[1]
            if arg_idx < len(args):
                val_node = args[arg_idx]
                arg_idx += 1
                shadow, sub = self.gen_input_value(val_node, input_kind)
                inputs[input_name] = self._pack_input(input_kind, shadow, sub)
            else:
                shadow, sub = self.gen_input_value(A.NumberLit(0), input_kind)
                inputs[input_name] = self._pack_input(input_kind, shadow, sub)
        self.current_blocks[block_id] = {
            "opcode": spec["opcode"],
            "next": None, "parent": None,
            "inputs": inputs,
            "fields": fields,
            "shadow": False, "topLevel": False,
        }
        return None, block_id

    def _gen_binop(self, expr: A.BinOp) -> Tuple[Optional[list], Optional[str]]:
        op = expr.op
        op_to_opcode = {
            "+": "operator_add",
            "-": "operator_subtract",
            "*": "operator_multiply",
            "/": "operator_divide",
            "mod": "operator_mod",
            ">": "operator_gt",
            "<": "operator_lt",
            "=": "operator_equals",
            "!=": "operator_not_equals",  # TurboWarp extension, falls back to not(a=b)
            ">=": "operator_gt_or_equal",  # TurboWarp extension, falls back
            "<=": "operator_lt_or_equal",  # TurboWarp extension, falls back
            "and": "operator_and",
            "or": "operator_or",
        }
        opcode = op_to_opcode.get(op)
        if opcode is None:
            raise CompileError(f"unknown binary operator: {op!r}", expr.line)

        # For != >= <= we use the TurboWarp opcodes which are backward-compatible
        # (in vanilla Scratch they get desugared to not(a=b), a>b or a=c, a<b or a=c)

        block_id = gen_id()
        # Determine input kind and input names based on operator type
        # Math operators (+,-,*,/,mod) use NUM1/NUM2
        # Comparison operators (>,<,=) use OPERAND1/OPERAND2
        # Logic operators (and,or) use OPERAND1/OPERAND2
        if op in ("+", "-", "*", "/", "mod"):
            input1_name = "NUM1"
            input2_name = "NUM2"
            kind = "number"
        elif op in (">", "<", "=", "!=", ">=", "<="):
            input1_name = "OPERAND1"
            input2_name = "OPERAND2"
            kind = "any"
        else:  # and, or
            input1_name = "OPERAND1"
            input2_name = "OPERAND2"
            kind = "boolean"
        left_shadow, left_sub = self.gen_input_value(expr.left, kind)
        right_shadow, right_sub = self.gen_input_value(expr.right, kind)
        inputs = {
            input1_name: self._pack_input(kind, left_shadow, left_sub),
            input2_name: self._pack_input(kind, right_shadow, right_sub),
        }
        self.current_blocks[block_id] = {
            "opcode": opcode,
            "next": None, "parent": None,
            "inputs": inputs,
            "fields": {},
            "shadow": False, "topLevel": False,
        }
        return None, block_id

    def _gen_unaryop(self, expr: A.UnaryOp) -> Tuple[Optional[list], Optional[str]]:
        op = expr.op
        if op == "not":
            block_id = gen_id()
            shadow, sub = self.gen_input_value(expr.operand, "boolean")
            self.current_blocks[block_id] = {
                "opcode": "operator_not",
                "next": None, "parent": None,
                "inputs": {"OPERAND": self._pack_input("boolean", shadow, sub)},
                "fields": {},
                "shadow": False, "topLevel": False,
            }
            return None, block_id
        if op == "-":
            # negate: 0 - operand
            zero = A.NumberLit(0)
            new_expr = A.BinOp(op="-", left=zero, right=expr.operand, line=expr.line)
            return self._gen_binop(new_expr)
        raise CompileError(f"unknown unary operator: {op!r}", expr.line)

    # =====================================================================
    # Input packing
    # =====================================================================
    def _pack_input(self, kind: str, shadow: Optional[list], block_id: Optional[str]) -> list:
        """Pack a shadow/block into the Scratch input format.

        Scratch 3 input formats:
          [1, [prim, val]]              - pure shadow (literal value)
          [2, block_id]                 - block only, no shadow (substacks, booleans)
          [2, block_id, [prim, val]]    - block with shadow (reporter covering default)
          [3, [12, name, id]]           - variable reference
          [3, block_id, [prim, val]]    - block with shadow (alt form, used by reporters)

        When a reporter covers an input, we MUST include the shadow so that
        removing the reporter in the editor shows a default value instead of
        a "hole".  This is the key fix for the hole bug.
        """
        # Variable input - use format [3, [12, name, id]]
        if shadow is not None and len(shadow) > 0 and shadow[0] == SHADOW_VAR:
            return [3, shadow]
        # List input (similar)
        if shadow is not None and len(shadow) > 0 and shadow[0] == SHADOW_LIST:
            return [3, shadow]
        # Broadcast input
        if shadow is not None and len(shadow) > 0 and shadow[0] == SHADOW_BROADCAST:
            if block_id is None:
                return [1, shadow]
            return [2, block_id, shadow]
        # Block covering a shadow - MUST include the shadow so the editor
        # shows a default value when the reporter is removed.
        # Use format [3, block_id, shadow] (shadow type 3) like real Scratch.
        if block_id is not None and shadow is not None:
            return [3, block_id, shadow]
        # Block only (no shadow provided) - generate a default shadow based
        # on the input kind so the editor doesn't show a "hole" when the
        # reporter is removed.
        if block_id is not None and shadow is None:
            default = self._default_shadow(kind)
            if default is not None:
                return [3, block_id, default]
            return [2, block_id]
        # Pure shadow
        if shadow is not None:
            return [1, shadow]
        # Empty - shouldn't happen
        return [1, self._default_shadow(kind)]

    def _pack_substack(self, first_block_id: Optional[str]) -> list:
        if first_block_id is None:
            return [2, None]  # empty substack
        return [2, first_block_id]

    def _default_shadow(self, kind: str) -> list:
        if kind == "number":
            return [SHADOW_NUMBER, ""]
        if kind == "color":
            return [SHADOW_COLOR, "#000000"]
        if kind == "boolean":
            return None  # no shadow for booleans
        if kind == "broadcast":
            return [SHADOW_BROADCAST, ""]
        return [SHADOW_STRING, ""]


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj)
