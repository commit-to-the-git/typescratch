# TypeScratch

A small programming language that compiles to **Scratch 3 (.sb3)** files.  Write text, get a runnable Scratch project you can open in [scratch.mit.edu](https://scratch.mit.edu) or any Scratch 3 compatible editor.

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

Or from source:

```bash
git clone https://github.com/yourname/typescratch.git
cd typescratch
pip install -e .
```

## CLI

```bash
# Compile a .tysh file (writes thing.sb3 next to thing.tysh)
typescratch build thing.tysh

# Specify output path
typescratch build thing.tysh --out custom_name.sb3

# Verbose AST / token / block-graph dump to stderr
typescratch build thing.tysh --debug
```

## Library API

```python
import typescratch

# 1. Compile a .tysh file to a .sb3 file (output defaults to <input>.sb3)
typescratch.file("C:/Users/pc/Desktop/thing.tysh")
typescratch.file("thing.tysh", out="custom.sb3")

# 2. Compile a .tysh file to a specific .sb3 path
typescratch.compile("out.sb3", src_path="thing.tysh")
# or with just the output - it will look for out.tysh
typescratch.compile("out.sb3")

# 3. Compile from a source string
sb3_bytes = typescratch.source('''
    s "Sprite1"
    when gf clicked { say(Hello, World!)(2) }
''')
# or write to a file:
typescratch.source('say(Hello, World!)', out="hello.sb3", filename="hello.tysh")

# 4. Low-level: get the project.json + assets dict
project, assets = typescratch.compile_source(src, debug=True)
```

## Language reference

### Comments

```tysh
// line comment - goes to end of line
```

### Extensions

```tysh
extension Pen
extension Music
extension Video Sensing
extension Text to Speech
```

### Sprites & Backdrops

```tysh
// sprite with attributes (all optional - defaults: x=0, y=0, dir=90, size=100)
s "Player" xy=100, 50 dir=90 size=110 visible=true rot=all around

// backdrop
b "Stage 1" img=./backdrops/forest.svg
b "Stage 2"
```

If `img=` is omitted or the file doesn't exist, the sprite gets the default Scratch Cat costume and the stage gets a blank white backdrop.

### Variables

```tysh
Score = 0           // creates a variable named Score, initial value 0
Name = Scratch Cat  // creates Name with initial value "Scratch Cat"
Score += 10         // change Score by 10
Score -= 5          // change Score by -5
Score *= 2          // set Score to (Score * 2)
Score /= 3          // set Score to (Score / 3)
showVariable(Score) // show the variable monitor on stage
hideVariable(Score) // hide the variable monitor
```

### Lists

```tysh
list inventory = [sword, shield, potion]
list scores = [10, 20, 30]

// Stack blocks (modify the list):
inventory.add(new item)
inventory.delete(1)
inventory.delete(all)
inventory.insert(cool thing, 0)
inventory.replace(1, better sword)
inventory.show                       // show the list monitor on stage
inventory.hide                       // hide the list monitor

// Reporters (use in expressions):
X = inventory.item(1)                // item N of list
L = inventory.length                 // length of list
Has = inventory.contains(sword)      // list contains X?  (boolean)
Pos = inventory.itemNum(sword)       // item # of X in list
All = inventory.contents             // list as a string (space-separated)
```

### Hats (events)

```tysh
when gf clicked { ... }                       // when green flag clicked
when spr clicked { ... }                      // when this sprite clicked
when stage clicked { ... }                    // when stage clicked
when cloned { ... }                           // when I start as a clone
when key [space] pressed { ... }              // when [key] pressed
when backdrop switches to [Stage 2] { ... }   // when backdrop switches to [name]
when I receive [start game] { ... }           // when I receive [broadcast]
when [loudness] > [10] { ... }                // when [property] > [value]
```

### Motion

```tysh
move(10)                 // move 10 steps
turnRight(15)            // turn right 15 degrees
turnLeft(15)             // turn left 15 degrees
goto(10, 20)             // go to x: 10 y: 20
glide(1, 100, 50)        // glide 1 sec to x:100 y:50
glideTo(2, mouse)        // glide 2 secs to mouse-pointer
pointInDirection(90)     // point in direction 90
pointTowards(mouse)      // point towards mouse-pointer
goTo(random)             // go to random position
changeX(5)               // change x by 5
changeY(5)               // change y by 5
setX(100)                // set x to 100
setY(50)                 // set y to 50
ifOnEdgeBounce           // if on edge, bounce
setRotationStyle(left-right)  // all around | left-right | don't rotate
```

**Reporters:** `xPosition` (alias `x`), `yPosition` (alias `y`), `direction`

### Looks

```tysh
say(Hello, World!)(2)    // say "Hello, World!" for 2 seconds
say(Just saying)         // say "Just saying" (no time limit)
think(Hmm...)(1)         // think "Hmm..." for 1 second
switchCostumeTo(costume2)
nextCostume
switchBackdropTo(Stage 2)
nextBackdrop
changeSize(10)
setSize(100)
changeEffect(color)(25)
setEffect(color)(0)
clearGraphicEffects
show
hide
goToFront
goToBack(2)
```

**Reporters:** `costumeName`, `costumeNumber`, `backdropName`, `backdropNumber`, `size`

### Sound

```tysh
playSound(meow)
playSoundUntilDone(meow)
stopAllSounds
changePitch(10)
setPitch(100)
changeVolume(10)
setVolume(100)
changeSoundEffect(pitch)(10)       // pitch | pan
setSoundEffect(pitch)(100)
clearSoundEffects
```

**Reporters:** `volume`, `tempo`

### Control flow

```tysh
wait(1)                       // wait 1 second
waitUntil (cond)              // wait until condition is true
repeat(10) { ... }            // repeat 10 times
forever { ... }               // repeat forever
if (cond) { ... }
if (cond) { ... } else { ... }
repeatUntil (cond) { ... }
while (cond) { ... }          // sugar: becomes repeatUntil(not cond)
stop(all)                     // all | this script | other scripts in sprite | other scripts in stage
createCloneOf(myself)         // myself | sprite name
deleteThisClone
broadcast(message1)           // broadcast message1
broadcast(message1) and wait  // broadcast and wait
```

### Sensing

```tysh
ask(What is your name?) and wait   // ask and wait
resetTimer
setDraggable(true)                  // true | false

// Reporters:
answer
mouseDown
mouseX
mouseY
loudness
timer
daysSince2000            // alias: "days since 2000"
username
touching(mouse)          // mouse | edge | sprite name
touchingColor(#ff0000)
colorIsTouching(#ff0000, #00ff00)
distanceTo(mouse)
keyPressed(space)
attribute(x position, Sprite1)     // [property] of [sprite]
current(YEAR)                       // YEAR | MONTH | DATE | DAYOFWEEK | HOUR | MINUTE | SECOND | WEEKOFYEAR
```

### Operators (in expressions)

```tysh
5 + 3                  // addition
10 - 4                 // subtraction
6 * 7                  // multiplication
20 / 4                 // division
17 mod 5               // modulo
pickRandom(1, 100)     // random integer
join(Hello, World)     // string concatenation
letterOf(1, Hello)     // letter N of string
lengthOf(Hello World)  // string length
contains(Hello World, World)  // string contains
round(3.7)             // round
abs(-5)                // |x|
floor(3.7)  ceiling(3.2)  sqrt(16)
sin(0)  cos(0)  tan(0)  asin(1)  acos(0)  atan(1)
ln(2.7)  log(100)
```

Comparison: `>`, `<`, `=` (or `==`)
Logic: `and`, `or`, `not`

### Pen extension

```tysh
pen.Down
pen.Up
pen.SetColor(#ff0000)
pen.ChangeColor(10)
pen.SetSize(2)
pen.ChangeSize(1)
pen.SetHue(180)  pen.ChangeHue(10)
pen.SetShade(50) pen.ChangeShade(10)
pen.SetSaturation(80)  pen.ChangeSaturation(10)
pen.SetBrightness(50)  pen.ChangeBrightness(10)
pen.SetTransparency(0) pen.ChangeTransparency(10)
pen.Stamp
pen.Clear
```

### Custom blocks (My Blocks)

```tysh
s "Calculator"

// Define a custom block with arguments
def Add(a, b) {
  Result = a + b
  say(join(Result is, Result))
}

// With run-without-screen-refresh (warp)
def FastLoop(n) warp=true {
  repeat(n) { move(1) }
}

// Boolean argument
def IfPositive(n) {
  if n > 0 { say(Yes) } else { say(No) }
}

when gf clicked {
  Add(5, 3)
  FastLoop(100)
  IfPositive(42)
}
```

Argument types default to `string`; you can also specify `number` or `bool`:

```tysh
def Compute(base number, bonus number, debug bool) {
  ...
}
```

### Bare names and string literals

TypeScratch follows the principle that **Scratch has no strings, only text**.  Inside a parenthesized argument list, any unquoted word is treated as text by default:

```tysh
say(Hello, World!)        // MESSAGE = "Hello, World!"
say(LOOK I HAVE A IMAGE!) // MESSAGE = "LOOK I HAVE A IMAGE!"
```

If a bare word matches a declared variable, a custom-block parameter, or a builtin reporter (like `answer`, `mouseX`, `timer`), it's resolved to that variable/parameter/reporter instead:

```tysh
Score = 0
Score += 10
say(Score is)(Score)      // "Score is 10"
```

To force string interpretation, wrap the value in quotes:

```tysh
say("Score")              // MESSAGE = "Score" (literal text)
```

## Extensions

TypeScratch supports all 11 official Scratch 3.0 extensions.  Declare them at the top of your file with `extension <Name>`:

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

(Speech to Text is intentionally NOT supported . it's hidden in the Scratch UI and doesn't actually work.)

Many aliases are accepted (e.g. `tts` → `text2speech`, `wedo` → `wedov2`, `lego mindstorms` → `ev3`).

### Music

```tysh
music.PlayNote(60, 0.5)             // play note 60 for 0.5 beats
music.PlayDrum(Snare Drum, 0.25)    // play drum sample
music.Rest(0.25)                    // rest for 0.25 beats
music.SetInstrument(Piano)          // set instrument
music.SetTempo(120)
music.ChangeTempo(20)
TempoVar = music.Tempo              // reporter
```

### Text to Speech

```tysh
tts.Speak(Hello from TypeScratch!)
tts.SetVoice(Alto)                  // alto | tenor | squirrel | kitten | giant | kitten
tts.SetLanguage(English)
```

### Speech to Text

Hidden / experimental . Scratch's Speech to Text extension is hidden in the UI and may not work in all editors.  TypeScratch supports it but prints a warning at compile time so you know what you're getting into.

```tysh
extension Speech to Text

listen.Wait                         // listen and wait
Result = speech                     // get the recognized speech
when i_hear [hello] { ... }         // hat: when I hear "hello"
```

### Translate

```tysh
SpanishHello = translate.To(Hello, Spanish)
CurrentLang = translate.ViewerLanguage
```

### Video Sensing

```tysh
video.Toggle(on)                    // on | off
video.SetTransparency(50)
Motion = video.Motion(motion, sprite)   // motion | direction on sprite | stage
when video_motion > 50 { ... }
```

### Makey Makey

```tysh
when makey_key [Space] pressed { ... }
when makey_code [up up down down] pressed { ... }
```

### micro:bit

```tysh
mb.DisplayText(Hello)
mb.DisplaySymbol(heart)
mb.DisplayClear
when mb_button [A] pressed { ... }
when mb_gesture [shake] { ... }
when mb_tilted [front] { ... }
when mb_pin [0] connected { ... }
if mb.ButtonPressed(A) { ... }
if mb.Tilted(any) { ... }
Angle = mb.TiltAngle(front)
```

### LEGO BOOST

```tysh
boost.MotorOnFor(A, 1)              // motor A for 1 second
boost.MotorOnForRotation(B, 2)
boost.MotorOn(A)  boost.MotorOff(A)
boost.SetMotorPower(A, 50)
boost.SetMotorDirection(A, this way)
boost.SetLightHue(180)
Pos = boost.MotorPosition(A)
if boost.SeeingColor(blue) { ... }
Angle = boost.TiltAngle(up)
when boost_color [blue] { ... }
when boost_tilted [any] { ... }
```

### LEGO EV3

```tysh
ev3.MotorTurnClockwise(A, 1)
ev3.MotorTurnCounterClockwise(B, 1)
ev3.MotorSetPower(C, 75)
ev3.Beep(60, 0.5)
Pos = ev3.MotorPosition(A)
Dist = ev3.Distance
Bright = ev3.Brightness
if ev3.ButtonPressed(1) { ... }
when ev3_button [1] pressed { ... }
when ev3_distance 5 { ... }         // when distance < 5
when ev3_brightness 10 { ... }
```

### LEGO WeDo 2.0

```tysh
wedo.MotorOnFor(A, 1)
wedo.MotorOn(A)  wedo.MotorOff(A)
wedo.SetMotorPower(A, 50)
wedo.SetMotorDirection(A, this way)
wedo.SetLightHue(180)
wedo.PlayNote(60, 0.5)
Dist = wedo.Distance
if wedo.Tilted(any) { ... }
Angle = wedo.TiltAngle(up)
when wedo_distance [<] [5] { ... }
when wedo_tilted [any] { ... }
```

### Go Direct Force & Acceleration

```tysh
Force = gdx.Force
if gdx.FreeFalling { ... }
if gdx.Tilted(any) { ... }
Angle = gdx.Tilt(x)
Spin = gdx.SpinSpeed(x)
Acc = gdx.Acceleration(x)
when gdx_gesture [shaken] { ... }
when gdx_force [pushed] { ... }
when gdx_tilted [any] { ... }
```

## Hidden / Hacked / TurboWarp Blocks

TypeScratch supports the hidden blocks that exist in Scratch's runtime but aren't shown in the editor's palette.  Use these with care . they may not work in every Scratch editor.

### Counter (hidden Control)

```tysh
resetCounter           // clear the counter
incrementCounter       // increment counter by 1
Count = counter        // reporter: current counter value
```

### forEach loop (hidden Control)

```tysh
forEach (i) in (5) {
  say(join(Iteration, i))
}
// or: forEach (i in 5) { ... }
```

Iterates `i` from 1 to `count`, running the body once per value.

### allAtOnce (hidden Control)

```tysh
allAtOnce {
  move(10)
  turnRight(15)
  move(10)
}
```

Runs the body without yielding to the screen refresh between blocks (like a warp-mode custom block).

### Stretch (legacy Looks)

```tysh
changeStretch(10)      // change stretch by 10
setStretch(100)        // set stretch to 100
```

### Other hidden Looks blocks

```tysh
hideAllSprites                         // hide all sprites in the project
switchBackdropToAndWait(Stage 2)       // switch backdrop to X and wait
```

### Hidden Event hat

```tysh
when touching [mouse] { ... }          // when touching mouse / edge / sprite
```

### TurboWarp reporters

These return `true` only when the project is running inside [TurboWarp](https://turbowarp.org).  In vanilla Scratch they return `false` (and the blocks are invisible).

```tysh
if isTurboWarp { say(Running in TurboWarp!) }
if isCompiled { say(Compiled mode!) }
if isForked { say(Forked TurboWarp!) }
```

## Errors

Errors include line/column numbers and the source snippet:

```
CompileError at line 12:19 (thing.tysh): expected ')', got NOT ('not')
  >>   say(No it is not positive)
```

Use `--debug` for a full dump of tokens, AST, and the generated block graph.

## Examples

See [`examples/`](examples/) for runnable programs:

- `hello.tysh` - the simplest program
- `pen_spiral.tysh` - pen extension demo
- `custom_blocks.tysh` - My Blocks with arguments
- `user_example.tysh` - the example from the original TypeScratch request
- `full_test.tysh` - exercises every supported core feature
- `showcase.tysh` - exercises EVERY feature (324 blocks across 4 targets)
- `showcase_extensions.tysh` - exercises ALL 12 extensions (Pen, Music, TTS, Speech-to-Text, Translate, Video Sensing, Makey Makey, micro:bit, BOOST, EV3, WeDo 2, Go Direct Force)

## Project structure

```
typescratch/
├── typescratch/
│   ├── __init__.py    # public API: file(), source(), compile(), compile_source()
│   ├── cli.py         # `typescratch build` CLI
│   ├── lexer.py       # .tysh tokenizer
│   ├── parser.py      # tokens -> AST
│   ├── ast_nodes.py   # AST dataclass definitions
│   ├── blocks.py      # TypeScratch syntax -> Scratch opcode table
│   ├── codegen.py     # AST -> Scratch project.json
│   ├── sb3.py         # .sb3 zip packager
│   ├── assets.py      # default Scratch Cat + blank backdrop SVGs
│   └── errors.py      # CompileError + Debug logger
├── examples/          # example .tysh programs
├── pyproject.toml
├── setup.py
└── README.md
```

## License

Apache License 2.0 . see [LICENSE](LICENSE).
