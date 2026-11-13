# ESP32-S3 AI Desktop Robot

## Phase 1 — Bench Development and Software Architecture

### 1. Development philosophy

The project is divided into three major stages:

| Stage | Objective | Deliverable |
|---|---|---|
| 1. Electronics bench | Validate individual components | Working ESP32, servos, LCD, microphone, and speaker |
| 2. Software integration | Develop firmware, backend, and autonomy | Fully functioning robot software on the bench |
| 3. Mechanical integration | Design and print the robot | Complete desktop companion |

Our immediate focus is **Stages 1 and 2**.

The goal is a robot that can listen, speak, display expressions, and generate autonomous motion commands before it has a physical body.

### 2. Bench hardware architecture

We use the same electronics intended for the final robot.

```
                         INTERNET
                            │
                     ┌──────▼──────┐
                     │  OpenAI API │
                     │             │
                     │ LLM / Voice │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │ Python      │
                     │ Backend     │
                     │             │
                     │ AI Interface│
                     │ Behavior    │
                     │ Memory      │
                     │ Telemetry   │
                     └──────┬──────┘
                            │
                       Wi-Fi / USB
                            │
              ┌─────────────▼─────────────┐
              │         ESP32-S3          │
              │                           │
              │ FreeRTOS                  │
              │ State Machine             │
              │ Motion Controller         │
              │ Audio Driver              │
              │ Display Driver            │
              │ Communication Interface   │
              └─────────────┬─────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
     ┌────▼────┐       ┌────▼────┐      ┌─────▼─────┐
     │ PCA9685 │       │ GC9A01  │      │ I2S Audio │
     │         │       │ LCD     │      │           │
     │ 3 Servos│       │ Eyes    │      │ Mic/Speak │
     └─────────┘       └─────────┘      └───────────┘
```

Communication starts over **USB serial**, then migrates to **Wi-Fi/WebSockets**. USB is easier to debug and removes network connectivity as a variable during early development.

### 3. Electronics bench setup

| Component | Quantity | Purpose |
|---|---|---|
| ESP32-S3 DevKitC-1-N8R8 | 1 | Main embedded computer |
| PCA9685 servo controller | 1 | Servo PWM generation |
| MG90S micro servo | 3 | Motion actuators |
| GC9A01 round LCD | 1 | Animated face |
| INMP441 microphone | 1 | Voice input |
| MAX98357A amplifier | 1 | Audio output |
| 4Ω 3W speaker | 1 | Voice playback |
| 5V 5A regulated power supply | 1 | Servo and peripheral power |
| Breadboard | 1 | Low-current signal prototyping |
| Jumper wires | Assorted | Connections |
| Multimeter | 1 | Electrical verification |

> **Important:** Do not distribute servo motor power through a solderless breadboard. Use suitable terminal blocks or a power distribution board, with a fuse and common ground.

Attach the servos to a small temporary wooden or printed test fixture rather than letting them move loose on the bench.

### 4. Firmware architecture

Use **ESP-IDF with C++ and FreeRTOS**, rather than Arduino. ESP-IDF gives greater control over task scheduling, memory allocation, peripheral drivers, and diagnostics.

Repository structure:

```
aibot/
│
├── firmware/
│   ├── CMakeLists.txt
│   ├── sdkconfig.defaults
│   ├── tools/              # host-side bring-up scripts (serial console)
│   │
│   ├── main/
│   │   ├── main.cpp
│   │   └── CMakeLists.txt
│   │
│   └── components/
│       │
│       ├── robot_core/
│       │   ├── robot_state.hpp
│       │   ├── robot_state.cpp
│       │   ├── behavior_manager.cpp
│       │   └── behavior_manager.hpp
│       │
│       ├── motion/
│       │   ├── servo_driver.cpp
│       │   ├── servo_driver.hpp
│       │   ├── trajectory.cpp
│       │   └── trajectory.hpp
│       │
│       ├── display/
│       │   ├── lcd_driver.cpp
│       │   ├── eye_animation.cpp
│       │   └── expressions.cpp
│       │
│       ├── audio/
│       │   ├── microphone.cpp
│       │   ├── speaker.cpp
│       │   └── audio_manager.cpp
│       │
│       └── communication/
│           ├── serial_protocol.cpp
│           ├── wifi_manager.cpp
│           └── websocket_client.cpp
│
├── backend/
│   ├── main.py
│   ├── ai/
│   │   ├── openai_client.py
│   │   ├── conversation.py
│   │   └── personality.py
│   │
│   ├── behavior/
│   │   ├── behavior_planner.py
│   │   └── motion_commands.py
│   │
│   └── communication/
│       ├── serial_interface.py
│       └── websocket_server.py
│
├── sim/                    # software-only actuator simulator (section 7)
│   ├── robot_sim/
│   └── tests/
│
├── tests/
│   ├── test_motion.py
│   ├── test_communication.py
│   └── test_behavior.py
│
└── docs/
    ├── architecture.md
    ├── hardware.md
    └── communication_protocol.md
```

This keeps the embedded control software separate from the AI backend.

### 5. FreeRTOS task architecture

Five initial firmware tasks:

| Task | Target rate | Priority |
|---|---|---|
| Motion controller | 50 Hz | High |
| Communication | Event-driven | Medium |
| Audio processing | Buffer-driven | High |
| Display animation | 30 Hz | Low |
| Behavior manager | 10 Hz | Medium |

These are initial scheduling targets, not guaranteed real-time performance figures.

- The motion controller must never wait for an LLM response or a network transaction.
- The communication task receives high-level commands and updates a thread-safe command buffer.
- The motion task reads those commands and independently generates the desired actuator positions.

Example command flow:

```
Python Backend
     │
     ▼
MOVE_HEAD(30°, -10°)
     │
     ▼
Communication Task
     │
     ▼
Command Queue
     │
     ▼
Motion Controller
     │
     ▼
Trajectory Generator
     │
     ▼
PCA9685
     │
     ▼
Servos
```

This is the same fundamental separation used in larger robotic control systems.

### 6. Bench development milestones

| Milestone | Objective | Verification | Status |
|---|---|---|---|
| M1 | ESP32 development environment | Flash firmware and read serial logs | ✅ Done. ESP-IDF v6.1 installed; firmware boots, streams telemetry and answers commands on the board |
| M2 | LCD interface | Animated eyes and expressions | ✅ Done. Animated face (eyes and mouth) at 30 fps: blinks, idle glances, eased expression changes, test talking mouth; `expr`/`look`/`blink`/`eyes`/`talk` commands. 80 MHz SPI, 15 ms/frame |
| M3 | Audio output | Play synthesized speech | ✅ Done. Speech from `say.py` plays cleanly through the MAX98357A and speaker, 0 dropouts; boot volume 50%. Lip sync checked by eye in M6: the mouth moves in time with the voice |
| M4 | Audio input | Record microphone audio | ✅ Done. INMP441 streams 16 kHz audio to the PC with no gaps, also while the robot speaks; `tools/record.py` saves it as WAV and voice plays back clearly. Gain 18 dB |
| M5 | Python communication | Send commands and receive telemetry | ✅ Done. `backend/` package: `Robot` class with reply matching, telemetry, audio in and out; 14 tests on a fake robot; demo and a 60 s soak on the robot with 0 lost or wrong replies |
| M6 | Initial AI integration | Hold a conversation with coordinated expressions | ✅ Done. Local speech recognition, OpenAI replies, Piper voice, expressions; "Hey Mochi" sessions and lip sync checked on the robot |
| M7 | Servo control | Independently command three servos | 🟡 Wired; all three servos move. Direction, centering and real joint limits still to check |
| M8 | Motion trajectories | Smooth, bounded servo movements | 🟡 Trajectory planner prototyped and tested in `sim/`; not yet ported to firmware |
| M9 | Final AI integration | Hold a conversation with coordinated expressions and motion | ⬜ Not started |

*Status as of 2026-10-29. Servo work (M7, M8) now comes after initial AI integration (M6), and M9 adds motion to the conversation; the servo firmware already written stays in the tree.*

**Next steps**

1. Decide on 240 MHz CPU, and on 16 MB flash (the chip reports 16 MB).
2. For M7: check each joint's direction, its center pulse and its real limits (see [M7 — Servo control](#m7--servo-control)).

#### M2 — LCD interface

Two flat, glowing eyes on the 240×240 GC9A01 round display: solid rounded shapes in one accent color on black, in the style of Vector or EMO. Expression comes from eye shape alone.

**Wiring** (SPI; all pins configurable in menuconfig):

| LCD pin | ESP32-S3 | Purpose |
|---|---|---|
| VCC | 3V3 | Power |
| GND | GND | Ground |
| DIN | GPIO 11 | SPI data (MOSI) |
| CLK | GPIO 12 | SPI clock |
| CS | GPIO 10 | Chip select |
| DC | GPIO 13 | Data/command select |
| RST | GPIO 14 | Reset |
| BL | GPIO 21 | Backlight (PWM dimming) |

GPIO 10–12 are the native SPI pins, so the bus can run at 80 MHz. These pins avoid I2C (8, 9), octal PSRAM (35–37), USB (19, 20) and strapping pins.

**Design**

- Draw the eyes procedurally rather than with LVGL. The eyes are a few shapes, and a GUI toolkit adds weight without helping.
- The drawing code is plain C++ with no ESP-IDF dependencies. It runs on the LCD and on a PC, where it produces PNG/GIF previews and unit tests, the same pattern as `sim/` for motion.
- Each eye is described by a small parameter set: openness, upper and lower lid angle, roundness, size, gaze offset and color. Expressions are named parameter sets, and transitions interpolate between them.
- Frames are drawn in horizontal bands into two small DMA buffers in internal RAM. One band is sent while the next is drawn, so there's no 115 KB full framebuffer. A full frame is about 12 ms of SPI time at 80 MHz, well inside the 33 ms budget at 30 fps.

**Steps**

1. **Bring-up:** `esp_lcd` with the `espressif/esp_lcd_gc9a01` component. Add an `lcdtest` command (solid colors, then a test pattern) to check color order, orientation and inversion.
2. **Eye drawing:** a new `display` component, plus a host preview tool that renders every expression to PNG for tuning without flashing.
3. **Display task:** 30 Hz, low priority. Frame time and fps go into telemetry. Backlight brightness by LEDC PWM.
4. **Animation:**
   - Randomized blinks.
   - Idle gaze: small random eye movements with pauses.
   - Eased 150–250 ms transitions between expressions.
   - Expressions: neutral, happy, sad, surprised, angry, sleepy, plus listening and thinking for M6.
5. **Commands and docs:**
   - Serial commands: `expr <name>`, `look <x> <y>`, `blink`, `eyes auto on|off`, `bright <0-100>`.
   - Add them to the protocol table and `robot_cli.py`, and add LCD wiring to `firmware/README.md`.

**Done when:**

- Every expression shows on the LCD.
- Animation holds a steady 30 fps and blinks look natural.
- Python can switch expressions and gaze over serial.
- Telemetry reports display frame time.

#### M3 — Audio output

Speech is made on the PC with [Piper](https://github.com/rhasspy/piper) (offline neural TTS, voice `en_US-lessac-medium`), resampled to 16 kHz and streamed to the robot over the USB serial link, which now runs at 921600 baud. The robot plays it through a MAX98357A I2S amplifier and moves its mouth with the loudness.

**Wiring** (I2S; pins configurable in menuconfig → *aibot audio*):

| MAX98357A pin | Connect to | Notes |
|---|---|---|
| VIN | External 5 V supply (shared GND) | The board's 5V pin is unpowered from USB on this board; see bench findings |
| GND | ESP32 GND | |
| BCLK | GPIO 4 | Bit clock |
| LRC | GPIO 5 | Word select (left/right clock) |
| DIN | GPIO 6 | Audio data |
| GAIN | leave unconnected | 9 dB gain |
| SD | leave unconnected | Amp on, plays (left + right) / 2 |
| Speaker + / − | Amp's + / − speaker terminals | 4 Ω 3 W speaker. Never connect either speaker wire to GND |

GPIO 4–6 avoid I2C (8, 9), the LCD (10–14, 21), USB (19, 20), PSRAM (35–37) and strapping pins. The speaker can draw several hundred mA at full volume; if the board browns out or resets on loud sounds, lower `vol` or power the amp from a separate 5 V supply that shares GND with the ESP32.

**Design**

- `audio` component: I2S at 16 kHz, 16-bit mono, sent to both slots. A 2-second ring buffer in PSRAM feeds a high-priority playback task 20 ms at a time. New streams wait for 100 ms of audio before starting; when the buffer runs dry the speaker gets silence, and the dropout is counted.
- Serial link: 921600 baud (switched at startup; boot messages stay at 115200). Lines can be up to 1024 characters.
- Audio travels as `pcm <base64>` lines of 320 samples (20 ms). Each reply reports the robot's buffer, and `say.py` keeps about 0.75 s queued. This uses about half the link.
- Lip sync: the display task maps the playback loudness of each 20 ms block to mouth openness; the animator opens the mouth in about 25 ms and closes it in about 70 ms.

**Progress**

- [x] `audio` component, playback task, `beep`, `vol`, `pcm` commands
- [x] Serial link at 921600 baud with 1024-character lines
- [x] `tools/say.py`: Piper TTS → 16 kHz → streamed with flow control
- [x] Lip sync from playback loudness
- [x] Tested without a speaker: 3 s and 6 s sentences streamed in real time with 0 dropouts; all commands answer correctly
- [x] Wire the MAX98357A and speaker
- [x] `beep` is clearly audible; set a comfortable default `vol` (50%)
- [x] `say.py` speech sounds clean, with no gaps or clicks
- [ ] Mouth moves in time with the voice (tune `kSpeechFloor` / `kSpeechGain` in `display_commands.cpp` if needed)

**Bench findings (2026-10-28)**

- The board's 5V pin read 1.2 V when powered from the COM port, so the amp runs from an external 5 V supply with grounds tied at a single point. On many ESP32-S3 boards that pin only gets USB power once the IN-OUT solder jumper next to it is bridged.
- At first the amp played faint noise or garbage, and the beep came through only when a finger touched BCLK: the bit clock was ringing on a long jumper wire. Fixed by setting the I2S pins to their weakest drive in firmware and using a shorter BCLK wire.
- Known issue: one crack each time a program opens the serial port, because that resets the board and the separately powered amp plays the boot glitch. Fix later, if wanted, by driving SD from a GPIO with a 10 kΩ pull-down.

**Checks to run after wiring**

```bash
cd firmware
python3 tools/robot_cli.py /dev/ttyACM0     # then: beep, beep 440 1000, vol 30, beep
python3 tools/say.py /dev/ttyACM0 "Hello, I'm aibot."
```

#### M4 — Audio input

The robot records from an INMP441 I2S microphone and streams the audio to the PC over the serial link, where `tools/record.py` saves it as a WAV file. Speech recognition happens on the PC in M6; M4 only has to deliver clean audio.

**Wiring** (I2S; pins configurable in menuconfig → *aibot audio*):

| INMP441 pin | Connect to | Notes |
|---|---|---|
| VDD | ESP32 3V3 | 3.3 V only |
| GND | ESP32 GND | |
| SCK | GPIO 15 | Bit clock. Keep the wire short (see the M3 bench findings) |
| WS | GPIO 16 | Word select |
| SD | GPIO 17 | Audio data |
| L/R | GND | Mic sends on the left slot |

GPIO 15–17 avoid every pin already in use (speaker 4–6, I2C 8–9, LCD 10–14 and 21, USB 19–20, PSRAM 35–37).

**Design**

- `microphone` driver in the `audio` component, on the second I2S controller so the mic and speaker run independently. The INMP441 sends 24-bit samples in 32-bit slots, so the mic channel uses 32-bit slots while the speaker keeps 16-bit.
- A high-priority mic task reads 20 ms blocks (320 samples) at 16 kHz, removes DC drift and rumble with a high-pass filter at about 80 Hz, sends silence for the first 300 ms after boot while the mic starts up, applies a software gain (default +18 dB: the INMP441 is quiet at speaking distance), and converts to 16-bit with saturation. It tracks the peak level for telemetry.
- SCK and WS use the weakest pin drive, as the speaker pins do since M3.
- Commands: `mic on` / `mic off` start and stop streaming, `mic gain <0-40>` sets the gain in dB, `mic` alone shows the state.
- While on, the robot sends one line per block: `{"type":"mic","seq":N,"data":"<base64>"}`. The sequence number lets the PC spot gaps. That is about 45 kB/s robot → PC, half the link; speech to the speaker uses the other direction, so both can run at once.
- If sending falls behind and the I2S buffer overflows, the block is dropped and counted. Telemetry adds `mic_peak` (loudest sample since the last report, 0–1) and `mic_overruns`.
- `tools/record.py`: records N seconds to a WAV file with a live level bar, then reports gaps, peak and average level, and clipping. Warns when everything is zero (mic not connected). Play a recording back through the robot with `say.py --wav`.
- `robot_cli.py` hides `mic` data lines and shows the mic fields in telemetry.
- Out of scope: echo. The mic will hear the robot's own speaker; M6 has to deal with that (for example by muting the mic while the robot talks).

**Progress**

- [x] Mic driver, mic task and `mic` commands
- [x] Mic fields in telemetry; `robot_cli.py` hides mic data
- [x] `tools/record.py`
- [x] Before wiring: recording gives all zeros with no gaps and no overruns, also while speech plays (5 s of speech with the mic on: 280 blocks, 0 gaps, 0 overruns, 0 speaker dropouts)
- [x] Wire the INMP441
- [x] A voice recording plays back clearly; set the default gain (18 dB)
- [x] Recording and playback at the same time work without gaps (5 s of speech with the mic on: 281 blocks, 0 gaps, 0 overruns, 0 speaker dropouts)

**Bench findings (2026-10-28)**

- At +24 dB, speech at about 30 cm clipped. +12 dB never clipped but played back quietly; +18 dB is the default, a little loud: loud speech close to the mic can still clip, and `record.py` warns when it does.
- Every recording started pinned at full scale for about 50 ms: the INMP441 outputs junk while it starts up after the board resets. The firmware now sends silence for the first 300 ms after boot.
- Low-frequency drift after startup was removed by raising the high-pass filter from about 13 Hz to about 80 Hz. The remaining background is about −43 dBFS at +12 dB gain, most likely room noise (PC fan); speech sits about 20 dB above it.

**Checks to run after wiring**

```bash
cd firmware
python3 tools/record.py /dev/ttyACM0 -s 5 -o hello.wav   # speak during the 5 s
python3 tools/say.py /dev/ttyACM0 --wav hello.wav        # hear it back on the robot
```

#### M5 — Python communication

A reusable `backend/` package that owns the serial link, so M6 (conversation) and later milestones build on one tested interface instead of separate scripts. Threads, not asyncio, to match the existing tools; this can change when the link moves to Wi-Fi/WebSockets.

**Design**

- `backend/communication/serial_interface.py`: a `Robot` class.
  - Opens the port, then pings until the robot answers (opening the port resets the board).
  - Methods for the commands (`ping`, `status`, `expr`, `look`, `blink`, `eyes_auto`, `talk`, `beep`, `volume`, `mic_gain`, `servo`, `relax`, `rate`, `reboot`, …). Each sends one line and returns the reply as a dict. An `error` reply raises `RobotError`; no reply in time raises `RobotTimeout`.
  - Reply matching: protocol v0 has no message IDs, but the robot answers in order, so pending commands are matched first-in, first-out. Each reply is also checked against its command: an `ack` names its `cmd`, and `pong`, `telemetry`, `i2cscan` and `pcm` belong to `ping`, `status`, `i2cscan` and `pcm`. A reply for a later command means earlier ones lost theirs, and they fail at once instead of waiting for a timeout. `status` replies with an ordinary telemetry message, so telemetry resolves a pending `status` only when it is next in line.
  - A `boot` message (the robot rebooted) fails everything pending with `RobotReset` and is reported to listeners.
  - Telemetry: the latest message in `robot.telemetry`, plus listeners.
  - Audio out: `play(samples)` streams 16 kHz audio with the same flow control as `say.py` (about 0.75 s queued on the robot, at most 8 `pcm` lines in flight).
  - Audio in: `mic_on(callback)` / `mic_off()`. The callback gets each 20 ms block; gaps in the sequence numbers are counted.
  - Firmware log lines go to Python `logging`.
- `backend/tests/`: a fake robot in Python that speaks protocol v0 (periodic telemetry, mic stream, a `pcm` buffer that drains in real time, reboots, dropped replies on request), so the tests run without hardware.
- `backend/main.py`: demo and soak test on the real robot.
- The tools in `firmware/tools/` stay as they are for now.

**Progress**

- [x] `Robot` class: connection, commands, reply matching, telemetry, logs
- [x] Audio out (`play`) and in (`mic_on`): on the robot, a chime played with 0 samples dropped, and 3 s of mic gave 151 blocks with 0 gaps
- [x] Fake robot and tests: 14 tests, stable over 10 runs
- [x] Demo on the robot: face, eyes, beep and audio, with telemetry
- [x] Soak test on the robot: 60 s, 3 threads, telemetry every 100 ms: 5459 commands (91/s), 0 wrong replies, 0 errors, 0 timeouts; latency median 33 ms, max 44 ms

**Bench findings (2026-10-28)**

- A `ping` round trip takes about 21 ms over USB serial, most of it the USB link rather than the firmware. Fine for commands; M6 should not wait for a reply between every audio chunk, which `play()` already avoids by keeping up to 8 in flight.

**Checks**

```bash
pip install -r backend/requirements.txt
python3 -m pytest backend/tests
python3 -m backend.main /dev/ttyACM0            # demo
python3 -m backend.main /dev/ttyACM0 --soak 60  # 60 s of rapid commands
```

#### M6 — Initial AI integration

Talk to the robot and it answers out loud, with the face following along: listening while you talk, thinking while it works out a reply, then a mood that fits what it says.

**One turn**

| Step | Where | How |
|---|---|---|
| 1. Hear you | PC | Detects the start and end of speech from the mic loudness (adaptive noise floor). Face → `listening` |
| 2. Voice → text | PC | faster-whisper, small English model, int8 on the CPU. Face → `thinking` |
| 3. Text → reply | OpenAI | Responses API, streamed, with the recent conversation as context |
| 4. Reply → voice | PC | Piper (as in M3), one sentence at a time, so speaking starts after the first sentence |
| 5. Face | Robot | The reply starts with a mood tag (`[happy]`, `[sad]`, …) that sets the expression; the mouth follows the voice (M3 lip sync); back to `neutral` afterwards |

**Design**

- `backend/audio/listener.py`: start/end-of-speech detection on 20 ms mic blocks, with pre-roll so the first syllable isn't cut. Pure code, no threads, so it is easy to test.
- `backend/audio/stt.py`, `backend/audio/tts.py`: faster-whisper and Piper. Piper uses the voice already downloaded into `firmware/tools/voices/`.
- `backend/ai/openai_client.py`: streams replies and keeps the last turns as history. `backend/ai/personality.py`: the system prompt (a friendly desk robot; one to three short spoken sentences; no lists, emoji or markdown) and the moods.
- `backend/ai/conversation.py`: the loop. Mic blocks go through a queue so the serial reader never waits. A worker turns reply sentences into audio while the previous sentence plays.
- Echo: mic blocks are ignored while the robot thinks and speaks, and for 0.3 s after.
- The robot is called **Mochi**, and talks in sessions (`backend/ai/wake_word.py`):
  - Asleep (`sleepy` face): every sentence is transcribed on the PC for free, and only one with "Mochi" in it wakes the robot. Nothing else is sent anywhere.
  - "Hey Mochi!" on its own gets a built-in greeting; "Hey Mochi, what's …?" wakes it and answers the question. Each session starts a fresh conversation.
  - Awake, it answers everything, until "Bye bye Mochi" (or goodbye, good night, see you) gets a built-in goodbye and puts it back to sleep, or nobody speaks for 2 minutes and it naps.
  - Speech recognition is nudged towards the name (faster-whisper `hotwords`), and common misspellings (Mochie, Moochi, …) count.
  - `AIBOT_NAME` and `AIBOT_IDLE_TIMEOUT_S` in `.env` change the name and nap time; `--always-answer` never sleeps.
- The system prompt includes facts about how the robot is built (body, what it can't do yet, where speech recognition, replies and the voice run, and how to change them), so it can answer questions about itself.
- Settings and the OpenAI API key come from a `.env` file in the repository root, which git ignores.
- `AIBOT_VOICE` in `.env` (or `--voice`) picks another Piper voice, e.g. `en_US-amy-medium`; it is downloaded into `firmware/tools/voices/` on first use. Samples: https://rhasspy.github.io/piper-samples/
- Latency target: under about 3 s from the end of your speech to the first word of the reply. Each turn prints its timings.
- Speech recognition, the AI and speech synthesis are passed in as objects, so tests use stand-ins with the M5 fake robot.

**Progress**

- [x] Speech detection, speech recognition, speech synthesis
- [x] OpenAI client and personality
- [x] Conversation loop with expressions and echo handling
- [x] Tests without hardware
- [x] OpenAI key in `.env`; pick the default model (`gpt-5.4-mini` with reasoning off)
- [x] Sessions: "Hey Mochi" to start, "Bye bye Mochi" or 2 minutes of silence to end; only questions in a session cost anything
- [x] Conversation on the robot with sessions
- [x] Conversation on the robot; measure latency (first turn: text 1.1 s and first word 2.7 s after you stop, plus the 0.7 s of silence that marks the end)
- [x] Mouth moves in time with the voice (open since M3)

**Bench findings (2026-10-28)**

- Speech recognition on this PC (4 cores, no GPU): `base.en` transcribes 5–6 s of speech in about 0.9 s; `small.en` takes about 3 s and was no more accurate on the bench recordings, so `base.en` is the default. Both are English-only.
- Time to the first words of a reply, with the robot's prompt: `gpt-4o-mini` 0.70 s, `gpt-4.1-mini` 0.82 s, `gpt-5.4-nano` 0.55 s, `gpt-5.4-mini` 0.63 s, `gpt-5.5` 0.82 s (GPT-5 models with reasoning off). `gpt-5.4-mini` gave the most natural short replies. `gpt-4.1-nano` is retired.
- Whisper writes "You" for some non-speech sounds (here, probably the crack when the board resets). While Mochi is asleep these are ignored; during a session they would still be answered.
- The OpenAI client's HTTP layer needs `brotli` 1.2 or newer; Ubuntu's 1.0.9 breaks every request. It also pulls in an `anyio` whose pytest plugin needs pytest 8. Both are in `backend/requirements.txt`.

**Bench findings (2026-10-29)**

- Sessions on the robot work: speech without the name is ignored while asleep; "Hey Mochi!" gets the greeting; "Hey Mochi, what's your name?" wakes it and answers (first word 2.7 s); "Bye bye Mochi!" and 2 minutes of silence both put it to sleep.
- The mouth moves in time with the voice.
- During a session, background voices and noise get answered: a misheard sentence (probably a TV) and a bare "." both got replies.
- One transcription of 1.4 s of noise took 9.3 s instead of the usual 1.1 s, probably faster-whisper retrying at higher temperatures when it isn't confident.
- A long first sentence delays the first word (4.1 s for a reply about the Moon's distance), because each sentence is synthesized whole before it plays.

**Checks**

```bash
pip install -r backend/requirements.txt
python3 -m pytest backend/tests
python3 -m backend.chat /dev/ttyACM0            # "Hey Mochi!" to start, "Bye bye Mochi!" to end
```

#### M7 — Servo control

Three servos (body yaw, head yaw, head pitch) driven at 50 Hz through a PCA9685 over I2C. Each joint is clamped to its limits before any pulse is sent.

**Wiring** (I2C; pins and address configurable in menuconfig → *aibot motion*):

| PCA9685 pin | ESP32-S3 | Purpose |
|---|---|---|
| VCC | 3V3 | Logic power |
| GND | GND | Common ground |
| SDA | GPIO 8 | I2C data |
| SCL | GPIO 9 | I2C clock |
| V+ (side header pin) | — | Separate 5 V 5 A supply for the servos |

- **Servo power:** feed the 5 V supply into the **V+ pin on the side header**, not the screw terminal. On this board the terminal reads 5 V but doesn't power the servo rows (likely a faulty reverse-polarity protection part). To diagnose, measure V+ to GND on a servo header row, not at the terminal. Don't power the servos from the ESP32's 5V pin. Connect the supply ground to the ESP32 ground.
- **Polarity:** the side V+ pin skips the reverse-polarity protection, so double-check + and − before powering up. Use thick wires.
- **Address:** 0x40 (default, no address jumpers soldered).
- **Channels:** plug each servo in with its signal wire (usually yellow or orange) toward the PWM pin.

| Joint | Channel | Limits (placeholder) |
|---|---|---|
| `body_yaw` | 0 | −90° to 90° |
| `head_yaw` | 1 | −60° to 60° |
| `head_pitch` | 2 | −20° to 30° |

**Bring-up checks** (commands in `docs/CLI.md`):

1. The `boot` message shows `"pca9685":true`.
2. `i2cscan` lists `[64]` (0x40; the firmware turns off the 0x70 all-call address at startup).
3. `pulse <channel> 1500` centers each servo; check it moves and holds.
4. `servo <joint> <deg>` moves each joint within its limits; `relax` makes them go limp.

After M9, we implement autonomous behaviors.

#### M10 — Autonomous behavior framework

The robot should be able to perform actions without explicit user commands.

```
IDLE
  │
  ├── Blink every few seconds
  │
  ├── Occasionally look left/right
  │
  └── Return to neutral
         │
         ▼
LISTENING
  │
  ├── Stop idle motion
  ├── Display listening expression
  └── Capture audio
         │
         ▼
THINKING
  │
  ├── Tilt head slightly
  └── Wait for AI response
         │
         ▼
SPEAKING
  │
  ├── Play generated speech
  ├── Animate expression
  └── Perform gestures
         │
         ▼
IDLE
```

All of this can be tested without a physical robot body.

### 7. Bench software testing strategy

Since software is developed before the mechanics, we add a software-only actuator simulator. The motion controller supports two output modes:

**Hardware mode**

```
Motion Controller
       │
       ▼
PCA9685
       │
       ▼
Physical Servos
```

**Simulation mode**

```
Motion Controller
       │
       ▼
Simulated Servos
       │
       ▼
Python Visualization
```

Commanded joint angles and trajectories are visualized in Python. The joint vector:

$$
q =
\begin{bmatrix}
\theta_{\text{body yaw}}\\
\theta_{\text{head yaw}}\\
\theta_{\text{head pitch}}
\end{bmatrix}
$$

The simulator can plot:

- Joint position versus time
- Joint velocity versus time
- Joint acceleration versus time
- Command tracking
- Joint-limit violations

Because standard hobby servos generally don't provide position feedback, initial hardware tests verify commanded motion rather than true closed-loop joint tracking. Feedback-capable actuators can be added later if necessary.

This also allows the autonomy framework to be developed and tested before all the electronics are installed.

### 8. First implementation step

**Milestone M1: ESP32-S3 firmware bring-up.**

Establish a reliable development environment and a minimal application that:

1. Initializes the ESP32-S3.
2. Starts FreeRTOS tasks.
3. Prints periodic telemetry over USB.
4. Accepts commands from a Python application.
5. Reports system uptime and available memory.

Servo integration (PCA9685) comes later, in M7.

Development tools:

- Ubuntu Linux
- VS Code
- ESP-IDF
- Python 3
- Git

A single Git repository holds firmware, backend, simulation, and documentation.
