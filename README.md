# TypeScratch

A programming language that compiles to **Scratch 3 (.sb3)** files. Write text, get a runnable Scratch project you can open in [scratch.mit.edu](https://scratch.mit.edu) or [TurboWarp](https://turbowarp.org/editor).

The official mascot is **Lint Zippy**, an original character created for TypeScratch (CC BY-NC-ND 4.0).

```tysh
extension Pen
// your average comment
s "Sprite1"
when gf clicked {
  say(Hello, World!)(2)
  pen.Down
  goto(10, 20)
  pen.Up
  Points = 0
  Name = Scratch Cat
  Points += 1
}
when spr clicked {
  if (days since 2000) > 120 {
    say(idk)
  }
}
```

## Install

```bash
pip install typescratch
```

On Windows, `windows-curses` is automatically installed for the IDE.

## CLI

```bash
typescratch build thing.tysh                    # compile to .sb3
typescratch build thing.tysh --out out.sb3      # specify output
typescratch build thing.tysh --debug             # verbose token/AST dump
typescratch ide thing.tysh                       # launch the terminal IDE
typescratch decompile game.sb3                   # decompile .sb3 to .tysh
typescratch decompile game.sb3 --out game.tysh   # specify output
typescratch fmt game.tysh                        # auto-indent in place
typescratch install user/repo                    # install a package from GitHub
typescratch uninstall repo-name                  # remove a package
typescratch list                                 # list installed packages
typescratch meow                                 # print the Scratch Cat in ASCII art
typescratch version
```

Or use `python -m typescratch build thing.tysh` if `typescratch` is not on PATH.

## Library API

```python
import typescratch

# Compile a .tysh file to .sb3 (output defaults to <input>.sb3)
typescratch.file("thing.tysh")
typescratch.file("thing.tysh", out="custom.sb3")

# Compile from a source string
sb3_bytes = typescratch.source('s "S" when gf clicked { say(hi) }')
typescratch.source(src, out="out.sb3")

# Decompile a .sb3 file to .tysh source
from typescratch.decompiler import decompile_sb3
source_code = decompile_sb3("game.sb3")
```

## Language reference

### Comments

```tysh
// line comment (only at the start of a line, after whitespace)
// this is because // is also the floor division operator
```

### Extensions

```tysh
extension Pen
extension Music
extension Text to Speech
extension Translate
extension Video Sensing
extension Makey Makey
extension micro:bit
extension LEGO BOOST
extension LEGO EV3
extension LEGO WeDo 2
extension Go Direct Force
```

### Sprites and Backdrops

```tysh
s "Player" xy=100, 50 dir=90 size=110 visible=true rot=all around
b "Stage 1" img=./backdrops/forest.svg
```

If `img=` is omitted or the file doesn't exist, the sprite gets the official TypeScratch mascot, **Lint Zippy**, as its default costume.

### Sound and Costume Imports

```tysh
s "Player"
sound meow from "./meow.wav"
sound jump from "./jump.mp3"
costume walk1 from "./walk1.png"
costume walk2 from "./walk2.png"
when gf clicked {
  playSound(meow)
  switchCostumeTo(walk1)
}
```

### Variables

```tysh
Score = 0
Name = Scratch Cat
Score += 10
Score -= 5
Score *= 2
Score /= 3
Score++           // increment by 1
Score--           // decrement by 1
showVariable(Score)
hideVariable(Score)
```

### Local Variables (inside custom blocks)

```tysh
def Compute(base) {
  private result = base * 2
  say(result)
}
```

### Lists

```tysh
list inventory = [sword, shield, potion]
list scores = [10, 20, 30]

inventory.add(new item)
inventory.delete(1)
inventory.delete(all)
inventory.insert(cool thing, 0)
inventory.replace(1, better sword)
inventory.show
inventory.hide

// List reporters (use in expressions):
X = inventory.item(1)
L = inventory.length
Has = inventory.contains(sword)
Pos = inventory.itemNum(sword)
All = inventory.contents
```

### Hats (events)

```tysh
when gf clicked { ... }
when spr clicked { ... }
when stage clicked { ... }
when cloned { ... }
when key [space] pressed { ... }
when backdrop switches to [Stage 2] { ... }
when I receive [start game] { ... }
when [loudness] > [10] { ... }
when touching [mouse] { ... }
```

### Motion

```tysh
move(10)
turnRight(15)
turnLeft(15)
goto(10, 20)
glide(1, 100, 50)
pointInDirection(90)
pointTowards(mouse)
changeX(5)
changeY(5)
setX(100)
setY(50)
ifOnEdgeBounce
setRotationStyle(left-right)
```

### Looks

```tysh
say(Hello, World!)(2)
say(Just saying)
think(Hmm...)(1)
switchCostumeTo(costume2)
nextCostume
switchBackdropTo(Stage 2)
changeSize(10)
setSize(100)
show
hide
goFront                  // go to front layer
goBack                   // go to back layer
goFwdLyrs(2)             // go forward 2 layers
goBwdLyrs(2)             // go backward 2 layers
```

### Sound

```tysh
playSound(meow)
playSoundUntilDone(meow)
stopAllSounds
changePitch(10)
setPitch(100)
changeVolume(10)
setVolume(100)
changeSoundEffect(pitch)(10)
setSoundEffect(pitch)(100)
clearSoundEffects
```

### Control flow

```tysh
wait(1)
waitUntil (cond)
repeat(10) { ... }
forever { ... }
if (cond) { ... }
if (cond) { ... } elif (cond2) { ... } else { ... }
repeatUntil (cond) { ... }
while (cond) { ... }
forEach (i) in (5) { ... }
allAtOnce { ... }
stop(all)
createCloneOf(myself)
deleteThisClone
broadcast(message1)
broadcast(message1) and wait
```

### Operators (in expressions)

```tysh
5 + 3                  // addition
10 - 4                 // subtraction
6 * 7                  // multiplication
20 / 4                 // division
17 // 5                // floor division (round(17 / 5))
17 mod 5               // modulo
"Hello" & " World"     // string join
5 != 3                 // not equals
5 >= 5                 // greater than or equal
3 <= 5                 // less than or equal
pickRandom(1, 100)
join(Hello, World)
letterOf(1, Hello)
lengthOf(Hello World)
contains(Hello World, World)
round(3.7)
abs(-5)
floor(3.7)  ceiling(3.2)  sqrt(16)
sin(0)  cos(0)  tan(0)  asin(1)  acos(0)  atan(1)
ln(2.7)  log(100)
```

Comparison: `>`, `<`, `=`, `!=`, `>=`, `<=`
Logic: `and`, `or`, `not`

### Ternary Expressions

```tysh
say([if (x > 5) yes else no])
X = [if (Score > 100) winner else loser]
```

### Sensing

```tysh
ask(What is your name?) and wait
resetTimer

// Reporters:
answer
mouseDown
mouseX
mouseY
loudness
timer
daysSince2000
username
touching(mouse)
touchingColor(#ff0000)
colorIsTouching(#ff0000, #00ff00)
distanceTo(mouse)
keyPressed(space)
attribute(x position, Sprite1)
current(YEAR)
```

### Pen extension

```tysh
pen.Clear
pen.Down
pen.Up
pen.SetColor(#ff0000)
pen.SetSize(3)
pen.Stamp
```

### Custom blocks (My Blocks)

```tysh
def Greet(name) {
  say(join(Hello, name))(2)
}

def FastLoop(n) warp=true {
  repeat(n) { move(1) }
}

def Calc(base number, mult number, debug bool) {
  Result = base * mult
  if debug { say(Result) }
}

when gf clicked {
  Greet(Bob)
  FastLoop(100)
  Calc(5, 3, true)
}
```

### Multi-file Projects (fuse)

```tysh
fuse "helpers.tysh"
fuse "typescratch_packages/my-lib/main.tysh"
```

Inline other `.tysh` files into your project. Recursive, so fused files can fuse other files.

### Hidden / Hacked / TurboWarp Blocks

```tysh
resetCounter
incrementCounter
Count = counter
forEach (i) in (5) { say(i) }
allAtOnce { move(10) turnRight(15) }
changeStretch(10)
setStretch(100)
hideAllSprites
switchBackdropToAndWait(Stage 2)
if isTurboWarp { say(Running in TurboWarp!) }
if isTurboWarp? { say(Running in TurboWarp!) }
```

### Error Types

TypeScratch has friendly error types:

- **SyntaxOops**: syntax errors (missing braces, unknown tokens)
- **ForgotOops**: using an undefined custom block, variable, or broadcast
- **ArgumentOops**: calling a custom block with the wrong number of arguments
- **TypeMismatchOops**: using a non-boolean where a boolean is expected (reserved for future use)

All errors include line numbers and "Did you mean?" suggestions.

## Decompiler

TypeScratch includes a decompiler that converts `.sb3` files back to `.tysh` source code:

```bash
typescratch decompile game.sb3
typescratch decompile game.sb3 --out game.tysh
```

Tested on griffpatch's appel game (8146 lines decompiled with zero unknown blocks).

## IDE

TypeScratch includes a terminal-based IDE with syntax highlighting, auto-indentation, and compile/verify buttons:

```bash
typescratch ide              # new file
typescratch ide game.tysh    # open existing file
```

Controls:
- **F5**: Compile to .sb3
- **F6**: Verify syntax
- **Ctrl+S**: Save
- **Ctrl+Q**: Quit
- Arrow keys, Page Up/Down, Home/End

## Formatter

```bash
typescratch fmt game.tysh              # format in place
typescratch fmt game.tysh --out out.tysh
```

## Package Manager

```bash
typescratch install user/repo          # install from GitHub
typescratch install user/repo@v1.0     # install specific tag
typescratch uninstall repo-name        # remove package
typescratch list                       # list installed packages
```

Packages are cloned into `./typescratch_packages/`. Use `fuse` to include them:
```tysh
fuse "typescratch_packages/my-lib/main.tysh"
```

## Easter Eggs

```bash
typescratch meow    # prints the TypeScratch mascot in ASCII art
```

## Project structure

```
typescratch/
    typescratch/
        __init__.py          # public API
        __main__.py          # python -m typescratch entry point
        cli.py               # CLI (build, ide, decompile, fmt, install, meow)
        lexer.py             # .tysh tokenizer
        parser.py            # tokens -> AST
        ast_nodes.py         # AST dataclass definitions
        blocks.py            # TypeScratch syntax -> Scratch opcode table
        codegen.py           # AST -> Scratch project.json
        sb3.py               # .sb3 zip packager
        decompiler.py        # .sb3 -> .tysh decompiler
        ide.py               # terminal IDE (curses)
        package_manager.py   # GitHub package installer
        assets.py            # default mascot (Lint Zippy) and backdrop
        errors.py            # SyntaxOops, ForgotOops, ArgumentOops
        lint_zippy.svg       # official mascot (CC BY-NC-ND 4.0)
        logo.svg             # TypeScratch logo
        logo_ascii.txt       # ASCII art logo for the IDE
        meow.txt             # ASCII art for the meow easter egg
```

## License

Apache License 2.0 for the TypeScratch language and compiler.

The TypeScratch mascot "Lint Zippy" (lint_zippy.svg) is licensed under CC BY-NC-ND 4.0. See MASCOT_LICENSE.

GitHub: https://github.com/commit-to-the-git/typescratch
