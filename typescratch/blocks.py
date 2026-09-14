"""Scratch 3.0 block table - mapping from TypeScratch syntax to Scratch opcodes.

Each entry is a dict with keys:
    opcode     Scratch opcode (e.g. "looks_sayforsecs")
    args       list of input specs.  Each spec is a tuple:
                  (input_name, input_kind, source)
               where input_kind in {"number","string","color","boolean","any",
                                     "substack","substack2","var","list","menu"}
               and source in {"args","post"} (which paren group the value
               comes from - args = first parens, post = second parens).
               For args, the index is implicit (consumed in order).
    fields     list of (field_name, value_or_None).  If None, the value
               comes from the next arg.
    category   for organization only.
    special    optional marker for special-case handling.

For reporters (boolean-returning or value-returning blocks used in
expressions), see REPORTERS below.
"""

# ---------------------------------------------------------------------------
# Stack blocks (statements)
# ---------------------------------------------------------------------------

STACK_BLOCKS = {
    # ---- Motion ----
    "move": {
        "opcode": "motion_movesteps",
        "args": [("STEPS", "number", "args")],
    },
    "turnRight": {
        "opcode": "motion_turnright",
        "args": [("DEGREES", "number", "args")],
    },
    "turnLeft": {
        "opcode": "motion_turnleft",
        "args": [("DEGREES", "number", "args")],
    },
    "goto": {
        "opcode": "motion_gotoxy",
        "args": [("X", "number", "args"), ("Y", "number", "args")],
    },
    "goToXY": {
        "opcode": "motion_gotoxy",
        "args": [("X", "number", "args"), ("Y", "number", "args")],
    },
    "glide": {
        "opcode": "motion_glidesecstoxy",
        "args": [("SECS", "number", "args"), ("X", "number", "args"), ("Y", "number", "args")],
    },
    "glideTo": {
        "opcode": "motion_glideto",
        "args": [("SECS", "number", "args"), ("TO", "menu", "args")],
    },
    "pointInDirection": {
        "opcode": "motion_pointindirection",
        "args": [("DIRECTION", "angle", "args")],
    },
    "pointTowards": {
        "opcode": "motion_pointtowards",
        "args": [("TOWARDS", "menu", "args")],
    },
    "goTo": {
        "opcode": "motion_goto",
        "args": [("TO", "menu", "args")],
    },
    "changeX": {
        "opcode": "motion_changexby",
        "args": [("DX", "number", "args")],
    },
    "changeY": {
        "opcode": "motion_changeyby",
        "args": [("DY", "number", "args")],
    },
    "setX": {
        "opcode": "motion_setx",
        "args": [("X", "number", "args")],
    },
    "setY": {
        "opcode": "motion_sety",
        "args": [("Y", "number", "args")],
    },
    "ifOnEdgeBounce": {
        "opcode": "motion_ifonedgebounce",
        "args": [],
    },
    "setRotationStyle": {
        "opcode": "motion_setrotationstyle",
        "fields": [("STYLE", None)],
    },

    # ---- Looks ----
    "say": {
        "opcode": "looks_sayforsecs",
        "args": [("MESSAGE", "string", "args"), ("SECS", "number", "post")],
    },
    "say_": {  # used when no post parens -> say without secs
        "opcode": "looks_say",
        "args": [("MESSAGE", "string", "args")],
    },
    "think": {
        "opcode": "looks_thinkforsecs",
        "args": [("MESSAGE", "string", "args"), ("SECS", "number", "post")],
    },
    "think_": {
        "opcode": "looks_think",
        "args": [("MESSAGE", "string", "args")],
    },
    "switchCostumeTo": {
        "opcode": "looks_switchcostumeto",
        "fields": [("COSTUME", None)],
    },
    "nextCostume": {
        "opcode": "looks_nextcostume",
        "args": [],
    },
    "switchBackdropTo": {
        "opcode": "looks_switchbackdropto",
        "fields": [("BACKDROP", None)],
    },
    "nextBackdrop": {
        "opcode": "looks_nextbackdrop",
        "args": [],
    },
    "changeSize": {
        "opcode": "looks_changesizeby",
        "args": [("CHANGE", "number", "args")],
    },
    "setSize": {
        "opcode": "looks_setsizeto",
        "args": [("SIZE", "number", "args")],
    },
    "changeEffect": {
        "opcode": "looks_changeeffectby",
        "fields": [("EFFECT", None)],
        "args": [("CHANGE", "number", "args")],
    },
    "setEffect": {
        "opcode": "looks_seteffectto",
        "fields": [("EFFECT", None)],
        "args": [("VALUE", "number", "args")],
    },
    "clearGraphicEffects": {
        "opcode": "looks_cleargraphiceffects",
        "args": [],
    },
    "show": {
        "opcode": "looks_show",
        "args": [],
    },
    "hide": {
        "opcode": "looks_hide",
        "args": [],
    },
    "goToFront": {
        "opcode": "looks_gotofrontback",
        "fields": [("FRONT_BACK", "front")],
    },
    "goToBack": {
        "opcode": "looks_gotofrontback",
        "fields": [("FRONT_BACK", "back")],
    },
    "goFront": {
        "opcode": "looks_gotofrontback",
        "fields": [("FRONT_BACK", "front")],
    },
    "goBack": {
        "opcode": "looks_gotofrontback",
        "fields": [("FRONT_BACK", "back")],
    },
    "goForwardLayers": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "front")],
        "args": [("NUM", "number", "args")],
    },
    "goBackLayers": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "back")],
        "args": [("NUM", "number", "args")],
    },
    "goFwdLyrs": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "front")],
        "args": [("NUM", "number", "args")],
    },
    "goBwdLyrs": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "back")],
        "args": [("NUM", "number", "args")],
    },
    "goFwdLayers": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "front")],
        "args": [("NUM", "number", "args")],
    },
    "goBwdLayers": {
        "opcode": "looks_goforwardbackwardlayers",
        "fields": [("FRONTBACK", "back")],
        "args": [("NUM", "number", "args")],
    },

    # ---- Sound ----
    "playSound": {
        "opcode": "sound_play",
        "fields": [("SOUND_MENU", None)],
    },
    "playSoundUntilDone": {
        "opcode": "sound_playuntildone",
        "fields": [("SOUND_MENU", None)],
    },
    "stopAllSounds": {
        "opcode": "sound_stopallsounds",
        "args": [],
    },
    "changePitch": {
        "opcode": "sound_changepitchby",
        "args": [("PITCH", "number", "args")],
    },
    "setPitch": {
        "opcode": "sound_setpitchto",
        "args": [("PITCH", "number", "args")],
    },
    "changeVolume": {
        "opcode": "sound_changevolumeby",
        "args": [("VOLUME", "number", "args")],
    },
    "setVolume": {
        "opcode": "sound_setvolumeto",
        "args": [("VOLUME", "number", "args")],
    },

    # ---- Control ----
    "createCloneOf": {
        "opcode": "control_create_clone_of",
        "fields": [("CLONE_OPTION", None)],
    },
    "deleteThisClone": {
        "opcode": "control_delete_this_clone",
        "args": [],
    },
    "runBroadcast": {  # alias for broadcast() - used internally
        "opcode": "event_broadcast",
        "args": [("BROADCAST_INPUT", "broadcast", "args")],
    },
    "runBroadcastAndWait": {
        "opcode": "event_broadcastandwait",
        "args": [("BROADCAST_INPUT", "broadcast", "args")],
    },

    # ---- Sensing ----
    "askAndWait": {
        "opcode": "sensing_askandwait",
        "args": [("QUESTION", "string", "args")],
    },
    "resetTimer": {
        "opcode": "sensing_resettimer",
        "args": [],
    },
    "setDraggable": {
        "opcode": "sensing_setdragmode",
        "fields": [("DRAG_MODE", None)],
    },

    # ---- Variables (handled specially in codegen) ----
    # ---- Lists (handled specially in codegen via ListOp) ----

    # ---- Pen extension ----
    # accessed as pen.X
    "pen.Down": {"opcode": "pen_penDown", "args": []},
    "pen.Up": {"opcode": "pen_penUp", "args": []},
    "pen.SetColor": {
        "opcode": "pen_setPenColorTo",
        "args": [("COLOR", "color", "args")],
    },
    "pen.ChangeColor": {
        "opcode": "pen_changePenColorBy",
        "args": [("COLOR", "number", "args")],
    },
    "pen.SetHue": {
        "opcode": "pen_setPenHueToNumber",
        "args": [("HUE", "number", "args")],
    },
    "pen.ChangeHue": {
        "opcode": "pen_changePenHueBy",
        "args": [("HUE", "number", "args")],
    },
    "pen.SetShade": {
        "opcode": "pen_setPenShadeToNumber",
        "args": [("SHADE", "number", "args")],
    },
    "pen.ChangeShade": {
        "opcode": "pen_changePenShadeBy",
        "args": [("SHADE", "number", "args")],
    },
    "pen.SetSize": {
        "opcode": "pen_setPenSizeTo",
        "args": [("SIZE", "number", "args")],
    },
    "pen.ChangeSize": {
        "opcode": "pen_changePenSizeBy",
        "args": [("SIZE", "number", "args")],
    },
    "pen.SetSaturation": {
        "opcode": "pen_setPenSaturationToNumber",
        "args": [("SATURATION", "number", "args")],
    },
    "pen.ChangeSaturation": {
        "opcode": "pen_changePenSaturationBy",
        "args": [("SATURATION", "number", "args")],
    },
    "pen.SetBrightness": {
        "opcode": "pen_setPenBrightnessToNumber",
        "args": [("BRIGHTNESS", "number", "args")],
    },
    "pen.ChangeBrightness": {
        "opcode": "pen_changePenBrightnessBy",
        "args": [("BRIGHTNESS", "number", "args")],
    },
    "pen.SetTransparency": {
        "opcode": "pen_setPenTransparencyToNumber",
        "args": [("TRANSPARENCY", "number", "args")],
    },
    "pen.ChangeTransparency": {
        "opcode": "pen_changePenTransparencyBy",
        "args": [("TRANSPARENCY", "number", "args")],
    },
    "pen.Stamp": {"opcode": "pen_stamp", "args": []},
    "pen.Clear": {"opcode": "pen_clear", "args": []},

    # ---- Music extension (extension Music) ----
    "music.PlayDrum": {
        "opcode": "music_playDrumForBeats",
        "fields": [("DRUM", None)],
        "args": [("BEATS", "number", "args")],
    },
    "music.Rest": {
        "opcode": "music_restForBeats",
        "args": [("BEATS", "number", "args")],
    },
    "music.PlayNote": {
        "opcode": "music_playNoteForBeats",
        "args": [("NOTE", "number", "args"), ("BEATS", "number", "args")],
    },
    "music.SetInstrument": {
        "opcode": "music_setInstrument",
        "fields": [("INSTRUMENT", None)],
    },
    "music.SetTempo": {
        "opcode": "music_setTempo",
        "args": [("TEMPO", "number", "args")],
    },
    "music.ChangeTempo": {
        "opcode": "music_changeTempo",
        "args": [("TEMPO", "number", "args")],
    },

    # ---- Text to Speech extension (extension Text to Speech) ----
    "tts.Speak": {
        "opcode": "text2speech_speakAndWait",
        "args": [("WORDS", "string", "args")],
    },
    "tts.SetVoice": {
        "opcode": "text2speech_setVoice",
        "fields": [("VOICE", None)],
    },
    "tts.SetLanguage": {
        "opcode": "text2speech_setLanguage",
        "fields": [("LANGUAGE", None)],
    },

    # ---- Speech to Text extension (hidden / experimental in Scratch UI) ----
    # Emits a warning at compile time.  Generates the real speech2text
    # blocks; they may or may not work in your Scratch editor.
    "listenAndWait": {
        "opcode": "speech2text_listenAndWait",
        "args": [],
        "_warn": "Speech to Text is hidden in the Scratch UI and may not work.",
    },
    "listen.Wait": {
        "opcode": "speech2text_listenAndWait",
        "args": [],
        "_warn": "Speech to Text is hidden in the Scratch UI and may not work.",
    },

    # ---- Sound: clear/change/set sound effects ----
    "clearSoundEffects": {
        "opcode": "sound_cleareffects",
        "args": [],
    },
    "changeSoundEffect": {
        "opcode": "sound_changeeffectby",
        "fields": [("EFFECT", None)],
        "args": [("VALUE", "number", "args")],
    },
    "setSoundEffect": {
        "opcode": "sound_seteffectto",
        "fields": [("EFFECT", None)],
        "args": [("VALUE", "number", "args")],
    },

    # ---- Variables: show/hide variable (the monitor, not the value) ----
    "showVariable": {
        "opcode": "data_showvariable",
        "fields": [("VARIABLE", None)],
    },
    "hideVariable": {
        "opcode": "data_hidevariable",
        "fields": [("VARIABLE", None)],
    },

    # ---- Hidden Control blocks: counter ----
    "incrementCounter": {
        "opcode": "control_incr_counter",
        "args": [],
    },
    "resetCounter": {
        "opcode": "control_clear_counter",
        "args": [],
    },

    # ---- Hidden Control block: all-at-once (run without screen refresh) ----
    "allAtOnce": {
        "opcode": "control_all_at_once",
        "substack": "SUBSTACK",
    },

    # ---- Hidden Looks blocks: stretch (legacy but still functional) ----
    "changeStretch": {
        "opcode": "looks_changestretchby",
        "args": [("CHANGE", "number", "args")],
    },
    "setStretch": {
        "opcode": "looks_setstretchto",
        "args": [("STRETCH", "number", "args")],
    },

    # ---- Hidden Looks block: hide all sprites ----
    "hideAllSprites": {
        "opcode": "looks_hideallsprites",
        "args": [],
    },

    # ---- Hidden Looks block: switch backdrop to X and wait ----
    "switchBackdropToAndWait": {
        "opcode": "looks_switchbackdroptoandwait",
        "fields": [("BACKDROP", None)],
    },

    # ---- Video Sensing extension ----
    "video.Toggle": {
        "opcode": "videoSensing_videoToggle",
        "fields": [("VIDEO_STATE", None)],
    },
    "video.SetTransparency": {
        "opcode": "videoSensing_setVideoTransparency",
        "args": [("TRANSPARENCY", "number", "args")],
    },

    # ---- Makey Makey extension ----
    # Both blocks are hats - declared in HAT_BLOCKS below.

    # ---- micro:bit extension ----
    "mb.DisplaySymbol": {
        "opcode": "microbit_displaySymbol",
        "args": [("MATRIX", "string", "args")],
    },
    "mb.DisplayText": {
        "opcode": "microbit_displayText",
        "args": [("TEXT", "string", "args")],
    },
    "mb.DisplayClear": {
        "opcode": "microbit_displayClear",
        "args": [],
    },

    # ---- LEGO BOOST extension ----
    "boost.MotorOnFor": {
        "opcode": "boost_motorOnFor",
        "fields": [("MOTOR_ID", None)],
        "args": [("DURATION", "number", "args")],
    },
    "boost.MotorOnForRotation": {
        "opcode": "boost_motorOnForRotation",
        "fields": [("MOTOR_ID", None)],
        "args": [("ROTATION", "number", "args")],
    },
    "boost.MotorOn": {
        "opcode": "boost_motorOn",
        "fields": [("MOTOR_ID", None)],
    },
    "boost.MotorOff": {
        "opcode": "boost_motorOff",
        "fields": [("MOTOR_ID", None)],
    },
    "boost.SetMotorPower": {
        "opcode": "boost_setMotorPower",
        "fields": [("MOTOR_ID", None)],
        "args": [("POWER", "number", "args")],
    },
    "boost.SetMotorDirection": {
        "opcode": "boost_setMotorDirection",
        "fields": [("MOTOR_ID", None), ("MOTOR_DIRECTION", None)],
    },
    "boost.SetLightHue": {
        "opcode": "boost_setLightHue",
        "args": [("HUE", "number", "args")],
    },

    # ---- LEGO EV3 extension ----
    "ev3.MotorTurnClockwise": {
        "opcode": "ev3_motorTurnClockwise",
        "fields": [("PORT", None)],
        "args": [("TIME", "number", "args")],
    },
    "ev3.MotorTurnCounterClockwise": {
        "opcode": "ev3_motorTurnCounterClockwise",
        "fields": [("PORT", None)],
        "args": [("TIME", "number", "args")],
    },
    "ev3.MotorSetPower": {
        "opcode": "ev3_motorSetPower",
        "fields": [("PORT", None)],
        "args": [("POWER", "number", "args")],
    },
    "ev3.Beep": {
        "opcode": "ev3_beep",
        "args": [("NOTE", "number", "args"), ("TIME", "number", "args")],
    },

    # ---- LEGO WeDo 2.0 extension ----
    "wedo.MotorOnFor": {
        "opcode": "wedo2_motorOnFor",
        "fields": [("MOTOR_ID", None)],
        "args": [("DURATION", "number", "args")],
    },
    "wedo.MotorOn": {
        "opcode": "wedo2_motorOn",
        "fields": [("MOTOR_ID", None)],
    },
    "wedo.MotorOff": {
        "opcode": "wedo2_motorOff",
        "fields": [("MOTOR_ID", None)],
    },
    "wedo.SetMotorPower": {
        "opcode": "wedo2_startMotorPower",
        "fields": [("MOTOR_ID", None)],
        "args": [("POWER", "number", "args")],
    },
    "wedo.SetMotorDirection": {
        "opcode": "wedo2_setMotorDirection",
        "fields": [("MOTOR_ID", None), ("MOTOR_DIRECTION", None)],
    },
    "wedo.SetLightHue": {
        "opcode": "wedo2_setLightHue",
        "args": [("HUE", "number", "args")],
    },
    "wedo.PlayNote": {
        "opcode": "wedo2_playNoteFor",
        "args": [("NOTE", "number", "args"), ("DURATION", "number", "args")],
    },

    # ---- Go Direct Force & Acceleration extension (gdxfor) ----
    # All hats and reporters - see HAT_BLOCKS and REPORTERS below.
}

# ---------------------------------------------------------------------------
# Reporter blocks (used in expressions - return a value)
# ---------------------------------------------------------------------------

REPORTERS = {
    # Motion
    "xPosition": {"opcode": "motion_xposition", "returns": "number"},
    "x": {"opcode": "motion_xposition", "returns": "number"},
    "yPosition": {"opcode": "motion_yposition", "returns": "number"},
    "y": {"opcode": "motion_yposition", "returns": "number"},
    "direction": {"opcode": "motion_direction", "returns": "number"},

    # Looks
    "costumeName": {"opcode": "looks_costumename", "returns": "string"},
    "costumeNumber": {"opcode": "looks_costumenumber", "returns": "number"},
    "costumeNumberName": {
        "opcode": "looks_costumenumbername",
        "fields": [("NUMBER_NAME", None)],
        "returns": "any",
    },
    "cstmNumName": {
        "opcode": "looks_costumenumbername",
        "fields": [("NUMBER_NAME", None)],
        "returns": "any",
    },
    "backdropName": {"opcode": "looks_backdropname", "returns": "string"},
    "backdropNumber": {"opcode": "looks_backdropnumber", "returns": "number"},
    "backdropNumberName": {
        "opcode": "looks_backdropnumbername",
        "fields": [("NUMBER_NAME", None)],
        "returns": "any",
    },
    "size": {"opcode": "looks_size", "returns": "number"},

    # Sound
    "volume": {"opcode": "sound_volume", "returns": "number"},
    "tempo": {"opcode": "sound_tempo", "returns": "number"},

    # Sensing
    "answer": {"opcode": "sensing_answer", "returns": "string"},
    "mouseDown": {"opcode": "sensing_mousedown", "returns": "boolean"},
    "mouseX": {"opcode": "sensing_mousex", "returns": "number"},
    "mouseY": {"opcode": "sensing_mousey", "returns": "number"},
    "loudness": {"opcode": "sensing_loudness", "returns": "number"},
    "timer": {"opcode": "sensing_timer", "returns": "number"},
    "daysSince2000": {"opcode": "sensing_dayssince2000", "returns": "number"},
    "username": {"opcode": "sensing_username", "returns": "string"},
    "keyPressed": {
        "opcode": "sensing_keypressed",
        "fields": [("KEY_OPTION", None)],
        "returns": "boolean",
    },
    "touching": {
        "opcode": "sensing_touchingobject",
        "fields": [("TOUCHINGOBJECTMENU", None)],
        "returns": "boolean",
    },
    "touchingColor": {
        "opcode": "sensing_touchingcolor",
        "args": [("COLOR", "color", "args")],
        "returns": "boolean",
    },
    "colorIsTouching": {
        "opcode": "sensing_coloristouching",
        "args": [("COLOR", "color", "args"), ("COLOR2", "color", "args")],
        "returns": "boolean",
    },
    "distanceTo": {
        "opcode": "sensing_distanceto",
        "fields": [("DISTANCETOMENU", None)],
        "returns": "number",
    },

    # Operators
    "pickRandom": {
        "opcode": "operator_random",
        "args": [("FROM", "number", "args"), ("TO", "number", "args")],
        "returns": "number",
    },
    "join": {
        "opcode": "operator_join",
        "args": [("STRING1", "string", "args"), ("STRING2", "string", "args")],
        "returns": "string",
    },
    "lengthOf": {
        "opcode": "operator_length",
        "args": [("STRING", "string", "args")],
        "returns": "number",
    },
    "contains": {
        "opcode": "operator_contains",
        "args": [("STRING1", "string", "args"), ("STRING2", "string", "args")],
        "returns": "boolean",
    },
    "round": {
        "opcode": "operator_round",
        "args": [("NUM", "number", "args")],
        "returns": "number",
    },
    # math ops - single arg + OPERATOR field
    "abs":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "abs")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "floor":     {"opcode": "operator_mathop", "fields": [("OPERATOR", "floor")],     "args": [("NUM", "number", "args")], "returns": "number"},
    "ceiling":   {"opcode": "operator_mathop", "fields": [("OPERATOR", "ceiling")],   "args": [("NUM", "number", "args")], "returns": "number"},
    "sqrt":      {"opcode": "operator_mathop", "fields": [("OPERATOR", "sqrt")],      "args": [("NUM", "number", "args")], "returns": "number"},
    "sin":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "sin")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "cos":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "cos")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "tan":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "tan")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "asin":      {"opcode": "operator_mathop", "fields": [("OPERATOR", "asin")],      "args": [("NUM", "number", "args")], "returns": "number"},
    "acos":      {"opcode": "operator_mathop", "fields": [("OPERATOR", "acos")],      "args": [("NUM", "number", "args")], "returns": "number"},
    "atan":      {"opcode": "operator_mathop", "fields": [("OPERATOR", "atan")],      "args": [("NUM", "number", "args")], "returns": "number"},
    "ln":        {"opcode": "operator_mathop", "fields": [("OPERATOR", "ln")],        "args": [("NUM", "number", "args")], "returns": "number"},
    "log":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "log")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "e_^":       {"opcode": "operator_mathop", "fields": [("OPERATOR", "e ^")],       "args": [("NUM", "number", "args")], "returns": "number"},
    "10_^":      {"opcode": "operator_mathop", "fields": [("OPERATOR", "10 ^")],      "args": [("NUM", "number", "args")], "returns": "number"},

    # ---- Music extension reporters ----
    "music.Tempo": {"opcode": "music_getTempo", "returns": "number"},

    # ---- Translate extension reporters ----
    "translate.To": {
        "opcode": "translate_getTranslate",
        "args": [("WORDS", "string", "args"), ("LANGUAGE", "string", "args")],
        "returns": "string",
    },
    "translate.ViewerLanguage": {
        "opcode": "translate_getViewerLanguage",
        "returns": "string",
    },

    # ---- Speech to Text extension reporter (hidden / experimental) ----
    "speech": {
        "opcode": "speech2text_getSpeech",
        "returns": "string",
        "_warn": "Speech to Text is hidden in the Scratch UI and may not work.",
    },

    # ---- Hidden Control reporter: counter ----
    "counter": {
        "opcode": "control_get_counter",
        "returns": "number",
    },

    # ---- TurboWarp extension reporters ----
    # These only return true when the project is running inside TurboWarp
    # (https://turbowarp.org).  In vanilla Scratch they return false.
    "isTurboWarp": {
        "opcode": "tw_isTurboWarp",
        "returns": "boolean",
    },
    "isCompiled": {
        "opcode": "tw_isCompiled",
        "returns": "boolean",
    },
    "isForked": {
        "opcode": "tw_isForked",
        "returns": "boolean",
    },

    # ---- Sensing: [attribute] of [sprite]  (sensing_of) ----
    "attribute": {
        "opcode": "sensing_of",
        "fields": [("PROPERTY", None), ("TARGET", None)],
        "returns": "any",
    },
    # alias
    "getAttribute": {
        "opcode": "sensing_of",
        "fields": [("PROPERTY", None), ("TARGET", None)],
        "returns": "any",
    },

    # ---- Sensing: current [YEAR/MONTH/DATE/DAYOFWEEK/HOUR/MINUTE/SECOND/WEEKOFYEAR] ----
    "current": {
        "opcode": "sensing_current",
        "fields": [("CURRENTMENU", None)],
        "returns": "number",
    },

    # ---- Operators: letter (n) of (string) ----
    "letterOf": {
        "opcode": "operator_letter_of",
        "args": [("LETTER", "number", "args"), ("STRING", "string", "args")],
        "returns": "string",
    },

    # ---- Video Sensing extension reporter ----
    "video.Motion": {
        "opcode": "videoSensing_videoOn",
        "fields": [("ATTRIBUTE", None), ("SUBJECT", None)],
        "returns": "number",
    },

    # ---- micro:bit extension reporters / booleans ----
    "mb.ButtonPressed": {
        "opcode": "microbit_isButtonPressed",
        "fields": [("BTN", None)],
        "returns": "boolean",
    },
    "mb.Tilted": {
        "opcode": "microbit_isTilted",
        "fields": [("DIRECTION", None)],
        "returns": "boolean",
    },
    "mb.TiltAngle": {
        "opcode": "microbit_getTiltAngle",
        "fields": [("DIRECTION", None)],
        "returns": "number",
    },

    # ---- LEGO BOOST extension reporters / booleans ----
    "boost.MotorPosition": {
        "opcode": "boost_getMotorPosition",
        "fields": [("MOTOR_REPORTER_ID", None)],
        "returns": "number",
    },
    "boost.SeeingColor": {
        "opcode": "boost_seeingColor",
        "fields": [("COLOR", None)],
        "returns": "boolean",
    },
    "boost.TiltAngle": {
        "opcode": "boost_getTiltAngle",
        "fields": [("TILT_DIRECTION", None)],
        "returns": "number",
    },

    # ---- LEGO EV3 extension reporters / booleans ----
    "ev3.MotorPosition": {
        "opcode": "ev3_getMotorPosition",
        "fields": [("PORT", None)],
        "returns": "number",
    },
    "ev3.ButtonPressed": {
        "opcode": "ev3_buttonPressed",
        "fields": [("PORT", None)],
        "returns": "boolean",
    },
    "ev3.Distance":     {"opcode": "ev3_getDistance",     "returns": "number"},
    "ev3.Brightness":   {"opcode": "ev3_getBrightness",   "returns": "number"},

    # ---- LEGO WeDo 2.0 extension reporters / booleans ----
    "wedo.Distance":    {"opcode": "wedo2_getDistance",   "returns": "number"},
    "wedo.Tilted": {
        "opcode": "wedo2_isTilted",
        "fields": [("TILT_DIRECTION_ANY", None)],
        "returns": "boolean",
    },
    "wedo.TiltAngle": {
        "opcode": "wedo2_getTiltAngle",
        "fields": [("TILT_DIRECTION", None)],
        "returns": "number",
    },

    # ---- Go Direct Force & Acceleration (gdxfor) reporters / booleans ----
    "gdx.Force":         {"opcode": "gdxfor_getForce",         "returns": "number"},
    "gdx.FreeFalling":   {"opcode": "gdxfor_isFreeFalling",    "returns": "boolean"},
    "gdx.Tilted": {
        "opcode": "gdxfor_isTilted",
        "fields": [("TILT", None)],
        "returns": "boolean",
    },
    "gdx.Tilt": {
        "opcode": "gdxfor_getTilt",
        "fields": [("TILT", None)],
        "returns": "number",
    },
    "gdx.SpinSpeed": {
        "opcode": "gdxfor_getSpinSpeed",
        "fields": [("DIRECTION", None)],
        "returns": "number",
    },
    "gdx.Acceleration": {
        "opcode": "gdxfor_getAcceleration",
        "fields": [("DIRECTION", None)],
        "returns": "number",
    },
}

# ---------------------------------------------------------------------------
# Auto-generate "?" variants for boolean reporters.
# In Scratch, boolean reporters often have "?" in their display names
# (e.g. "touching?", "key pressed?").  In TypeScratch we name them
# without the "?" (e.g. "isTurboWarp"), but users may instinctively add
# the "?".  This loop creates aliases so both forms work.
# ---------------------------------------------------------------------------
for _key in list(REPORTERS.keys()):
    _spec = REPORTERS[_key]
    if _spec.get("returns") == "boolean" and not _key.endswith("?"):
        REPORTERS[_key + "?"] = _spec

# ---------------------------------------------------------------------------
# Built-in reporters reachable by bare name (e.g. `days since 2000`)
# Maps lowercased bare name -> (canonical_name, reporter_key)
# ---------------------------------------------------------------------------

BUILTIN_ALIASES = {
    # motion
    "x position": "xPosition",
    "y position": "yPosition",
    # looks
    "costume name": "costumeName",
    "costume number": "costumeNumber",
    "backdrop name": "backdropName",
    "backdrop number": "backdropNumber",
    # sensing
    "answer": "answer",
    "mouse down": "mouseDown",
    "mouse x": "mouseX",
    "mouse y": "mouseY",
    "loudness": "loudness",
    "timer": "timer",
    "days since 2000": "daysSince2000",
    "username": "username",
    "key space pressed": "keyPressed",
    # sound
    "volume": "volume",
    "tempo": "tempo",
    "size": "size",
    "direction": "direction",
}

# ---------------------------------------------------------------------------
# Hat blocks (event_whenX)
# ---------------------------------------------------------------------------

HAT_BLOCKS = {
    "gf":             {"opcode": "event_whenflagclicked"},
    "spr":            {"opcode": "event_whenthisspriteclicked"},
    "stage_clicked":  {"opcode": "event_whenstageclicked"},
    "cloned":         {"opcode": "control_start_as_clone"},
    "key":            {"opcode": "event_whenkeypressed",
                       "fields": [("KEY_OPTION", 0)]},
    "backdrop":       {"opcode": "event_whenbackdropswitchesto",
                       "fields": [("BACKDROP", 0)]},
    "receive":        {"opcode": "event_whenbroadcastreceived",
                       "fields": [("BROADCAST_OPTION", 0)]},
    "greater_than":   {"opcode": "event_whengreaterthan",
                       "fields": [("WHENGREATERTHANMENU", 0)],
                       "args": [("VALUE", "number", "args")]},

    # ---- Video Sensing extension hat ----
    "video_motion":   {"opcode": "videoSensing_whenMotionGreaterThan",
                       "args": [("REFERENCE", "number", "args")]},

    # ---- Speech to Text extension hat (hidden / experimental) ----
    "i_hear":         {"opcode": "speech2text_whenIHearHat",
                       "fields": [("PHRASE", 0)],
                       "_warn": "Speech to Text is hidden in the Scratch UI and may not work."},

    # ---- Hidden Event hat: when touching [object] ----
    "touching":       {"opcode": "event_whentouchingobject",
                       "fields": [("TOUCHINGOBJECTMENU", 0)]},

    # ---- Makey Makey extension hats ----
    "makey_key":      {"opcode": "makeymakey_whenMakeyKeyPressed",
                       "fields": [("KEY", 0)]},
    "makey_code":     {"opcode": "makeymakey_whenCodePressed",
                       "fields": [("SEQUENCE", 0)]},

    # ---- micro:bit extension hats ----
    "mb_button":      {"opcode": "microbit_whenButtonPressed",
                       "fields": [("BTN", 0)]},
    "mb_gesture":     {"opcode": "microbit_whenGesture",
                       "fields": [("GESTURE", 0)]},
    "mb_tilted":      {"opcode": "microbit_whenTilted",
                       "fields": [("DIRECTION", 0)]},
    "mb_pin":         {"opcode": "microbit_whenPinConnected",
                       "fields": [("PIN", 0)]},

    # ---- LEGO BOOST extension hats ----
    "boost_color":    {"opcode": "boost_whenColor",
                       "fields": [("COLOR", 0)]},
    "boost_tilted":   {"opcode": "boost_whenTilted",
                       "fields": [("TILT_DIRECTION_ANY", 0)]},

    # ---- LEGO EV3 extension hats ----
    "ev3_button":     {"opcode": "ev3_whenButtonPressed",
                       "fields": [("PORT", 0)]},
    "ev3_distance":   {"opcode": "ev3_whenDistanceLessThan",
                       "args": [("DISTANCE", "number", "args")]},
    "ev3_brightness": {"opcode": "ev3_whenBrightnessLessThan",
                       "args": [("DISTANCE", "number", "args")]},

    # ---- LEGO WeDo 2.0 extension hats ----
    "wedo_distance":  {"opcode": "wedo2_whenDistance",
                       "fields": [("OP", 0)],
                       "args": [("REFERENCE", "number", "args")]},
    "wedo_tilted":    {"opcode": "wedo2_whenTilted",
                       "fields": [("TILT_DIRECTION_ANY", 0)]},

    # ---- Go Direct Force & Acceleration (gdxfor) hats ----
    "gdx_gesture":    {"opcode": "gdxfor_whenGesture",
                       "fields": [("GESTURE", 0)]},
    "gdx_force":      {"opcode": "gdxfor_whenForcePushedOrPulled",
                       "fields": [("PUSH_PULL", 0)]},
    "gdx_tilted":     {"opcode": "gdxfor_whenTilted",
                       "fields": [("TILT", 0)]},
}

# ---------------------------------------------------------------------------
# Stop options
# ---------------------------------------------------------------------------
STOP_OPTIONS = {
    "all": "all",
    "this script": "this script",
    "thisscript": "this script",
    "other scripts in sprite": "other scripts in sprite",
    "other scripts in stage": "other scripts in stage",
}

# ---------------------------------------------------------------------------
# Effect names
# ---------------------------------------------------------------------------
EFFECT_NAMES = {"color", "fisheye", "whirl", "pixelate", "mosaic", "brightness", "ghost"}

# ---------------------------------------------------------------------------
# Rotation styles
# ---------------------------------------------------------------------------
ROTATION_STYLES = {
    "all around": "all around",
    "all-around": "all around",
    "left-right": "left-right",
    "left right": "left-right",
    "don't rotate": "don't rotate",
    "dont rotate": "don't rotate",
    "don't-rotate": "don't rotate",
}

# ---------------------------------------------------------------------------
# Sprite menu targets (for pointTowards, goTo, distanceTo, etc.)
# ---------------------------------------------------------------------------
SPRITE_MENUS = {
    "mouse": "_mouse_",
    "random": "_random_",
    "_mouse_": "_mouse_",
    "_random_": "_random_",
}
