"""Autocomplete frequency table for the TypeScratch IDE.

This is a Markov-style ranking system. Each entry maps a "context"
(the last word or token typed) to a list of suggestions with scores 0-100.

The higher the score, the more likely the suggestion is what the user wants.
The IDE shows the top suggestion as ghost text (gray) that the user can
accept with Tab.
"""

# Context -> [(suggestion, score), ...]
# Sorted by score descending. The top suggestion is shown as ghost text.
COMPLETIONS = {
    # After "when" - hat blocks
    "when": [
        ("gf clicked", 90),
        ("spr clicked", 60),
        ("key", 40),
        ("I receive", 30),
        ("cloned", 20),
        ("backdrop switches to", 15),
        ("touching", 10),
    ],
    # After "when gf"
    "gf": [("clicked", 100)],
    # After "when spr"
    "spr": [("clicked", 100)],
    # After "when key"
    "key": [("[space] pressed", 50), ("[up arrow] pressed", 30), ("[any] pressed", 20)],

    # After "if" - conditions
    "if": [("not ", 20), ("(x > 0)", 10)],

    # After "say"
    "say": [("(", 95)],

    # After "think"
    "think": [("(", 95)],

    # After "move"
    "move": [("(10)", 80), ("(", 20)],

    # After "turn"
    "turn": [("Right(15)", 60), ("Left(15)", 30), ("(", 10)],

    # After "goto"
    "goto": [("(0, 0)", 50), ("(100, 50)", 30), ("(", 20)],

    # After "repeat"
    "repeat": [("(10)", 60), ("(5)", 30), ("(", 10)],

    # After "forever"
    "forever": [("{", 100)],

    # After "pen."
    "pen": [(".Down", 40), (".Up", 30), (".Clear", 20), (".SetColor", 10)],

    # After "broadcast"
    "broadcast": [("(", 90)],

    # After "stop"
    "stop": [("(all)", 70), ("(this script)", 20), ("(", 10)],

    # After "wait"
    "wait": [("(1)", 60), ("(0.5)", 30), ("(", 10)],

    # After "set"
    "set": [("X", 20), ("Y", 20), ("Size", 15)],

    # After "change"
    "change": [("X", 20), ("Y", 20), ("Size", 15)],

    # After "switch"
    "switch": [("CostumeTo", 50), ("BackdropTo", 30)],

    # After "show"
    "show": [("", 50)],
    # After "hide"
    "hide": [("", 50)],

    # After "def"
    "def": [(" ", 100)],

    # After "extension"
    "extension": [("Pen", 50), ("Music", 20), ("Text to Speech", 10)],

    # After "s" (sprite)
    "s": [('"', 90)],

    # After "b" (backdrop)
    "b": [('"', 90)],

    # After "a" (all sprites var)
    "a": [("", 50)],

    # After "o" (this sprite only var)
    "o": [("", 50)],

    # After "list"
    "list": [(" ", 90)],

    # After "createCloneOf"
    "createCloneOf": [("(myself)", 80), ("(", 20)],

    # After "playSound"
    "playSound": [("(", 80)],

    # After "ask"
    "ask": [("(", 80)],
}

# Also: word-prefix completions (no context needed)
# When the user types a partial word, suggest full block names
WORD_COMPLETIONS = [
    "when gf clicked",
    "when spr clicked",
    "when key",
    "when I receive",
    "when cloned",
    "say",
    "think",
    "move",
    "turnRight",
    "turnLeft",
    "goto",
    "glide",
    "pointInDirection",
    "pointTowards",
    "changeX",
    "changeY",
    "setX",
    "setY",
    "ifOnEdgeBounce",
    "setRotationStyle",
    "switchCostumeTo",
    "nextCostume",
    "switchBackdropTo",
    "nextBackdrop",
    "changeSize",
    "setSize",
    "show",
    "hide",
    "goFront",
    "goBack",
    "goFwdLyrs",
    "goBwdLyrs",
    "playSound",
    "playSoundUntilDone",
    "stopAllSounds",
    "changePitch",
    "setPitch",
    "changeVolume",
    "setVolume",
    "clearSoundEffects",
    "changeSoundEffect",
    "setSoundEffect",
    "wait",
    "waitUntil",
    "repeat",
    "forever",
    "repeatUntil",
    "while",
    "forEach",
    "allAtOnce",
    "stop",
    "createCloneOf",
    "deleteThisClone",
    "broadcast",
    "ask",
    "resetTimer",
    "setDraggable",
    "showVariable",
    "hideVariable",
    "incrementCounter",
    "resetCounter",
    "counter",
    "isTurboWarp",
    "pen.Down",
    "pen.Up",
    "pen.Clear",
    "pen.SetColor",
    "pen.SetSize",
    "pen.Stamp",
    "pen.ChangeColor",
    "pen.ChangeSize",
    "music.PlayNote",
    "music.PlayDrum",
    "music.Rest",
    "music.SetInstrument",
    "music.SetTempo",
    "music.ChangeTempo",
    "music.Tempo",
    "tts.Speak",
    "tts.SetVoice",
    "tts.SetLanguage",
    "translate.To",
    "translate.ViewerLanguage",
    "video.Toggle",
    "video.SetTransparency",
    "video.Motion",
    "distanceTo",
    "touching",
    "touchingColor",
    "colorIsTouching",
    "keyPressed",
    "attribute",
    "current",
    "join",
    "lengthOf",
    "letterOf",
    "contains",
    "pickRandom",
    "round",
    "abs",
    "floor",
    "ceiling",
    "sqrt",
    "sin",
    "cos",
    "tan",
    "extension",
    "fuse",
    "sound",
    "costume",
    "private",
    "def",
    "elif",
    "else",
    "not",
    "and",
    "or",
    "mod",
    "true",
    "false",
]


def get_completion(context: str, prefix: str) -> str:
    """Get the best autocomplete suggestion.

    Args:
        context: the last complete word typed (e.g. "when", "say", "if")
        prefix: the partial word currently being typed (e.g. "cl" for "clicked")

    Returns:
        The suggested text to show as ghost text, or "" if no suggestion.
    """
    # First try context-based completions (Markov-style)
    if context in COMPLETIONS:
        suggestions = COMPLETIONS[context]
        for suggestion, score in suggestions:
            if suggestion.startswith(prefix) or not prefix:
                # Return the part of the suggestion that hasn't been typed yet
                remaining = suggestion[len(prefix):] if suggestion.startswith(prefix) else suggestion
                return remaining
        # If prefix doesn't match any suggestion, try the top one anyway
        if suggestions and not prefix:
            return suggestions[0][0]

    # Fall back to word-prefix completions
    if prefix and len(prefix) >= 2:
        best_match = None
        best_score = 0
        for word in WORD_COMPLETIONS:
            if word.startswith(prefix):
                # Score by how much of the word the prefix covers
                score = len(prefix) / len(word)
                if score > best_score:
                    best_score = score
                    best_match = word
        if best_match:
            return best_match[len(prefix):]

    return ""


def get_context_and_prefix(line: str, cursor_x: int) -> tuple:
    """Extract the context word and current prefix from the line.

    Returns (context, prefix) where context is the last complete word
    before the cursor, and prefix is the partial word being typed.
    """
    before_cursor = line[:cursor_x]

    # Split on whitespace and common delimiters
    import re
    tokens = re.split(r'[\s.()[\]{},]', before_cursor)

    # Filter out empty strings
    tokens = [t for t in tokens if t]

    if not tokens:
        return ("", "")

    # The prefix is the last token (might be partial)
    prefix = tokens[-1] if tokens else ""

    # The context is the second-to-last token (the last complete word)
    context = tokens[-2] if len(tokens) >= 2 else ""

    return (context, prefix)
