# Firmware

ESP-IDF (C++, FreeRTOS) firmware for the ESP32-S3 DevKitC-1-N8R8. Built with ESP-IDF v6.1 (installed at `~/esp/esp-idf`).

## Current state: M4 audio input done (mic wired and recording)

- Starts a command task and a telemetry task.
- Sends telemetry once a second: uptime, free heap, minimum free heap, free internal RAM, free PSRAM, task count, display fps and frame time, speaker buffer and dropouts, and mic peak level and overruns.
- Accepts commands from the host over USB serial.
- Drives the GC9A01 round LCD at 80 MHz SPI with an animated face (two eyes and a mouth) at 30 fps: random blinks, idle glances, smooth changes between expressions, and a talking mouth for testing.
- Plays 16 kHz audio through a MAX98357A amplifier: test tones, and speech streamed from the PC by `tools/say.py` (Piper TTS). The mouth moves with the sound.
- Records from an INMP441 microphone at 16 kHz and streams it to the PC on `mic on`; `tools/record.py` saves it as a WAV file.
- The serial link runs at 921600 baud once the app starts (boot messages are at 115200).
- Servo control (M7) was written early and is not yet tested on hardware: drives three servos through a PCA9685 at 50 Hz. Each joint is clamped to its limits before any pulse is sent.
- Servos stay limp at boot until commanded. A `servo` command jumps straight to the target at full speed; smooth moves come in M8.

## Wiring: LCD (M2)

| LCD pin | ESP32-S3 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| DIN | GPIO 11 |
| CLK | GPIO 12 |
| CS | GPIO 10 |
| DC | GPIO 13 |
| RST | GPIO 14 |
| BL | GPIO 21 |

- **Changing pins, SPI speed, orientation or colour order:** use `idf.py menuconfig` → *aibot display*. The defaults (invert on, mirror X on, red/blue swapped) are right for the bench module.
- **Power:** the module runs bright from the ESP32's 3V3; no separate supply is needed. A dim, faintly glowing or blank screen usually means a poor ground. If you do power the LCD from a separate supply, its ground must also connect to the ESP32's GND, or the panel can't read the data lines.

## Face previews on the PC

The face renderer (`components/display/face.cpp`) has no ESP-IDF dependencies, so it also builds on the host:

```bash
cmake -S components/display/host -B build-host
cmake --build build-host
ctest --test-dir build-host          # unit tests
build-host/face_preview /tmp/faces   # one PNG per expression, plus sheet, sheet_eyes_only, talking, blink, gaze, transition and animation strips
```

## Wiring: speaker (M3)

| MAX98357A pin | Connect to | Notes |
|---|---|---|
| VIN | External 5 V supply | The board's 5V pin read 1.2 V when powered from the COM port. On many ESP32-S3 boards that pin only gets USB power once the IN-OUT solder jumper next to it is bridged |
| GND | External supply GND and one ESP32 GND, tied at a single point | All grounds must be shared, or the amp plays noise |
| BCLK | GPIO 4 | Bit clock |
| LRC | GPIO 5 | Word select (left/right clock) |
| DIN | GPIO 6 | Audio data |
| GAIN | leave unconnected | 9 dB gain |
| SD | leave unconnected | Amp on, plays (left + right) / 2 |
| Speaker + / − | Amp's + / − speaker terminals | 4 Ω 3 W speaker. Never connect either speaker wire to GND |

- **Changing pins or the boot volume:** `idf.py menuconfig` → *aibot audio*.
- **Power:** at full volume the speaker can draw several hundred mA. If the board resets on loud sounds, lower `vol` or power the amp from a separate 5 V supply that shares GND with the ESP32.
- **Faint or garbled noise instead of sound,** which clears up when you touch the BCLK pin: the bit clock is ringing on the wire. The firmware already sets the I2S pins to their weakest drive. Keep the I2S wires short (a long BCLK jumper caused noisy speech on the bench; a shorter one fixed it). If it persists, run a GND wire alongside them and add a 33–100 Ω resistor in series on BCLK, close to the ESP32.
- **One crack when a program opens the serial port:** opening the port resets the board, and the amp, powered separately, plays the glitch on the I2S pins during boot. Harmless. To silence it, wire SD to a spare GPIO with a 10 kΩ pull-down and have the firmware enable the amp after I2S starts.

## Wiring: microphone (M4)

| INMP441 pin | Connect to | Notes |
|---|---|---|
| VDD | ESP32 3V3 | 3.3 V only |
| GND | ESP32 GND | |
| SCK | GPIO 15 | Bit clock. Keep it short |
| WS | GPIO 16 | Word select |
| SD | GPIO 17 | Audio data |
| L/R | GND | Mic sends on the left slot |

- **Changing pins or the boot gain:** `idf.py menuconfig` → *aibot audio*. The gain (default 18 dB) can also be changed at run time with `mic gain`.
- **All zeros when recording:** the mic isn't sending. Check VDD, SD on GPIO 17 and L/R on GND. The firmware pulls SD down, so a missing mic records silence rather than noise.

## Wiring: servos (M7)

| ESP32-S3 | PCA9685 |
|---|---|
| 3V3 | VCC (logic) |
| GND | GND |
| GPIO 8 | SDA |
| GPIO 9 | SCL |

- **Servo power:** connect the 5 V 5 A supply to the **V+ pin on the PCA9685's side header**, not the screw terminal. On this board the terminal reads 5 V but doesn't power the servo rows (likely a faulty reverse-polarity protection part). To diagnose, measure V+ to GND on a servo header row, not at the terminal. Don't power the servos from the ESP32's 5V pin.
- **Polarity:** the side V+ pin skips the reverse-polarity protection, so double-check + and − before powering up. Use thick wires.
- **Ground:** the supply ground and the ESP32 ground must be connected.
- **Channels:** body yaw on 0, head yaw on 1, head pitch on 2.
- **Changing pins or address:** use `idf.py menuconfig` → *aibot motion*.

## Build and flash

Plug into the board's **COM** port (not the one marked USB). Its CH343 serial chip shows up as `/dev/ttyACM0`.

```bash
. $HOME/esp/esp-idf/export.sh       # wherever ESP-IDF is installed
cd firmware
idf.py set-target esp32s3           # first time only
idf.py -p /dev/ttyACM0 flash monitor   # Ctrl-] exits the monitor
```

The monitor runs at 921600 baud, so the first few boot lines (sent at 115200) look garbled; everything after the app starts is readable.

## Talk to it from Python

```bash
pip install -r tools/requirements.txt
python3 tools/robot_cli.py /dev/ttyACM0
```

Type `ping`, `status`, `expr happy`, `beep` and so on. It only prints replies to your commands, plus errors and boot messages. Add `--telemetry` to see the periodic telemetry, or `--logs` to see ESP_LOG lines. Close `idf.py monitor` first, because only one program can hold the port at a time.

## Make it talk

```bash
python3 tools/say.py /dev/ttyACM0 "Hello, I'm aibot."
python3 tools/say.py /dev/ttyACM0 --wav clip.wav     # any 16-bit WAV
```

`say.py` makes speech with Piper on the PC, resamples it to 16 kHz and streams it to the robot. The first run downloads the voice (about 60 MB) into `tools/voices/`. It prints how long playback took and the robot's dropout count, which should stay 0. Close `robot_cli.py` first.

## Record from the mic

```bash
python3 tools/record.py /dev/ttyACM0 -s 5 -o hello.wav   # speak during the 5 s
python3 tools/say.py /dev/ttyACM0 --wav hello.wav        # hear it back on the robot
```

`record.py` turns the mic stream on, shows a live level bar, and saves 16 kHz mono audio. It then reports gaps (should be 0), peak and average level, and clipping, and warns if the audio is all zeros. `--gain <0-40>` sets the mic gain in dB first. Close `robot_cli.py` first.

## Serial protocol (v0)

- **Host → robot:** one plain-text command per line.
- **Robot → host:** one JSON object per line, always with a `"type"` field.
- **Logs:** ESP_LOG output shares the same UART. Any line that doesn't start with `{` is a log.

| Command | Reply |
|---|---|
| `ping` | `{"type":"pong","uptime_ms":…}` |
| `status` | one `telemetry` message immediately. Includes `fps` (animation rate), `drawn_fps` (frames actually redrawn), `frame_us` (draw time), `audio_ms` (audio queued), `dropouts` (times audio ran dry mid-stream since boot), `mic_peak` (loudest mic sample since the last report, 0–1) and `mic_overruns` (mic blocks lost) |
| `rate <ms>` | sets the telemetry period (100–60000 ms), replies `{"type":"ack","cmd":"rate","period_ms":…}` |
| `reboot` | `{"type":"ack","cmd":"reboot"}`, then restarts |
| `i2cscan` | `{"type":"i2cscan","found":[64]}`: decimal addresses (a PCA9685 shows as 64 = 0x40; the firmware turns off its 0x70 all-call address at startup) |
| `servo <joint> <deg>` | joint is `body_yaw`, `head_yaw`, `head_pitch` or `0`–`2`. Replies `{"type":"ack","cmd":"servo","joint":…,"deg":…,"pulse_us":…,"clamped":…}` |
| `pulse <ch> <us>` | raw pulse (500–2500 µs) on any of the 16 channels, for calibration. Ignores joint limits |
| `relax [joint]` | stops pulses so the servo goes limp. Relaxes every joint if no joint is given |
| `expr <name>` | blends to an expression: `neutral`, `happy`, `sad`, `angry`, `surprised`, `sleepy`, `listening`, `thinking`. Replies `{"type":"ack","cmd":"expr","name":…}` |
| `look <x> <y>` | points the eyes, -1..1 each axis, and stops idle eye movement. Replies `{"type":"ack","cmd":"look","x":…,"y":…,"auto":false}` |
| `blink` | blinks once now |
| `eyes [auto on\|off]` | shows or sets idle blinking and eye movement. Replies `{"type":"ack","cmd":"eyes","auto":true\|false}` |
| `talk [on\|off]` | shows or sets the test talking mouth (random syllables). Replies `{"type":"ack","cmd":"talk","on":true\|false}` |
| `beep [hz] [ms]` | plays a tone, default 880 Hz for 300 ms (50–8000 Hz, 10–2000 ms) |
| `vol [0-100]` | sets or shows the speaker volume (%) |
| `pcm <base64>` | queues up to 380 16-bit little-endian mono samples at 16 kHz. Replies `{"type":"pcm","buffered":…,"capacity":32768,"dropped":…}` so the sender can pace itself |
| `pcm end` / `pcm stop` | marks the end of a stream / drops everything queued |
| `mic [on\|off]` | shows the mic state, or starts/stops streaming it. Replies `{"type":"ack","cmd":"mic","on":…,"gain_db":…}`. While on, the robot also sends `{"type":"mic","seq":…,"data":…}` every 20 ms: 320 16-bit little-endian samples at 16 kHz, base64. A jump in `seq` means blocks were lost |
| `mic gain <0-40>` | sets the mic gain in dB |
| `lcdtest [image]` | test image: `pattern` (default: red top, green right, blue bottom, white ring), or solid `red`, `green`, `blue`, `white`, `black`. Pauses the face until the next face command |
| `lcdcfg [setting 0\|1]` | shows or changes `invert`, `mirror_x`, `mirror_y`, `swap_rb` until reboot, then redraws the pattern |
| `bright [0-100]` | sets or shows backlight brightness (%) |
| anything else | `{"type":"error","msg":"unknown command","cmd":…}` |

The robot sends `{"type":"boot","reset_reason":…,"idf":…,"pca9685":true|false,"lcd":true|false,"audio":true|false,"mic":true|false}` on startup and streams `telemetry` messages periodically.
