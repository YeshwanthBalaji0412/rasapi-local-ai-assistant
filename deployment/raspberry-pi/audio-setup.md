# RasaPi — Raspberry Pi Audio Setup (Phase 7)

End-to-end audio setup for push-to-talk voice on a Raspberry Pi 5. The
backend works without any of this — voice is **opt-in** and disabled by
default. Follow these steps only when you want spoken interaction.

> Phase 7 is **push-to-talk only**. There is no wake word, no
> always-listening mode, no browser microphone, and no cloud speech
> service. Audio never leaves the Pi.

### Hardware quality note

Bluetooth headsets in **HSP/HFP** mode (the only mode that gives mic
capture) drop the sample rate dramatically and add noise. They work,
but Whisper accuracy is noticeably lower than with wired audio.

For best results: **USB microphone + a separate speaker** (3.5mm jack
or HDMI). Bluetooth is fine for casual use; treat it as the "I'm on
the couch" setup, not the "production demo" setup.

---

## 1. List your audio devices

```bash
arecord -l            # capture (microphones)
aplay -l              # playback (speakers / HDMI / 3.5 mm jack)
```

Note the **card** and **device** numbers, e.g. `card 1, device 0`. You'll
need these as `plughw:1,0` later.

## 2. Add your user to the `audio` group

```bash
sudo usermod -aG audio "$USER"
newgrp audio
```

Log out and back in if `groups` doesn't show `audio` after `newgrp`.

## 3. Test the microphone (5-second capture)

```bash
arecord -D plughw:1,0 -d 5 -f S16_LE -c 1 -r 16000 /tmp/test.wav
```

Speak during the recording. If `arecord` errors with "device busy", check
that nothing else is holding the mic (`lsof /dev/snd/* 2>/dev/null`).

## 4. Test playback

```bash
aplay -D plughw:0,0 /tmp/test.wav
```

You should hear yourself. If silent, try `alsamixer` to raise output gain.

## 5. Install a TTS engine

**Recommendation:** Piper sounds dramatically better than espeak-ng and
is the recommended TTS engine. Use espeak-ng as a reliable fallback if
Piper has trouble installing.

### Option A — espeak-ng (lightweight, reliable fallback)

```bash
sudo apt install -y espeak-ng
espeak-ng "Hello, I am RasaPi"
```

Robotic-sounding but rock-solid and ~5 MB.

### Option B — Piper TTS (recommended)

```bash
# In the project venv:
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate
pip install piper-tts

# Download a voice model (~50 MB). amy-low is a good default — small
# and clear. See https://github.com/rhasspy/piper#voices for alternatives.
mkdir -p ~/piper-voices && cd ~/piper-voices
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/low/en_US-amy-low.onnx.json

# Smoke-test outside RasaPi first:
echo "Hello, I am RasaPi" | piper --model ~/piper-voices/en_US-amy-low.onnx --output_file /tmp/piper.wav
paplay /tmp/piper.wav    # paplay routes Bluetooth correctly on PipeWire
# (or `aplay /tmp/piper.wav` if you don't have paplay)
```

The shipped `PiperTTS` adapter assumes the `piper` binary is on `PATH`.
Some installs put it under `~/.local/bin` — make sure that's in your `$PATH`.

**No wrapper script is needed** for RasaPi to pass `--model`. As of Phase 10
the adapter reads `VOICE_PIPER_MODEL_PATH` from `.env` and constructs the
command itself.

**The `.onnx.json` config file must sit beside the `.onnx` model** (same
directory, same basename + `.json`). That's the default Piper layout — the
two wget lines above already do this correctly. If you need to keep them
apart, set `VOICE_PIPER_CONFIG_PATH` explicitly.

## 6. Install whisper.cpp for local STT (optional, takes ~10 min on Pi 5)

```bash
cd ~
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make

# Smallest English-only model — fastest on Pi:
bash ./models/download-ggml-model.sh tiny.en

# Test:
./build/bin/whisper-cli -m ./models/ggml-tiny.en.bin -f /tmp/test.wav -otxt -of /tmp/test
cat /tmp/test.txt
```

The shipped `WhisperCppSTT` adapter calls `whisper-cli`. Symlink it onto
your `$PATH`, e.g.:

```bash
sudo ln -s "$HOME/whisper.cpp/build/bin/whisper-cli" /usr/local/bin/whisper-cli
```

**No symlink under `backend/models/` is needed** as of Phase 10. The
adapter reads `VOICE_WHISPER_MODEL_PATH` from `.env` and passes it to
whisper-cli via `-m`. Point the env var at wherever you downloaded the
model.

For better accuracy at higher CPU cost, swap to `base.en` (~150 MB):

```bash
bash ./models/download-ggml-model.sh base.en
# Then in .env:  VOICE_WHISPER_MODEL_PATH=/home/<PI_USER>/whisper.cpp/models/ggml-base.en.bin
```

## 7. Configure `.env` to use real engines

Recommended Raspberry Pi setup (Phase 10 polish):

```env
ENABLE_VOICE=true
VOICE_RECORDER_ENGINE=arecord
VOICE_STT_ENGINE=whisper
VOICE_TTS_ENGINE=piper

# `pulse` works with PipeWire / Bluetooth headsets.
VOICE_DEVICE_INPUT=pulse
VOICE_DEVICE_OUTPUT=

# Model paths — adjust to match your install.
VOICE_WHISPER_MODEL_PATH=/home/<PI_USER>/whisper.cpp/models/ggml-tiny.en.bin
VOICE_PIPER_MODEL_PATH=/home/<PI_USER>/piper-voices/en_US-amy-low.onnx
VOICE_PIPER_CONFIG_PATH=

# `auto` prefers paplay; falls back to aplay if paplay isn't installed.
VOICE_TTS_PLAYBACK_COMMAND=auto

VOICE_RECORD_SECONDS=5
VOICE_SAVE_AUDIO=false
```

If you start with espeak-ng instead of Piper, set
`VOICE_TTS_ENGINE=espeak` and skip the two `PIPER_*` settings.

```bash
chmod 600 .env
sudo systemctl restart rasapi
```

## 8. Run the voice CLI

From inside the project venv:

```bash
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate

python -m voice.cli status
python -m voice.cli tts-test "Hello, I am RasaPi"

# The big one:
python -m voice.cli once
```

`once` runs:
1. Record 5s
2. Transcribe locally
3. Send transcript to the same router `/ask` uses
4. Speak the response

You should hear an answer through your speaker.

## 9. Run a single voice cycle from the dashboard host

```bash
curl -X POST http://127.0.0.1:8000/voice/session-once
```

Returns the transcript, intent, and assistant response as JSON.

---

## Troubleshooting

### `arecord` says "device or resource busy"

Another process holds the mic. Likely PulseAudio or an old `arecord` you
forgot to Ctrl-C. Find it:

```bash
fuser /dev/snd/* 2>/dev/null
```

Stop PulseAudio if you're not using it:

```bash
systemctl --user stop pulseaudio.service pulseaudio.socket || true
```

### No input level from the mic

Open `alsamixer` and:
- Press F4 to switch to capture view.
- Use arrow keys to raise the **Mic** or **Capture** level.
- Press Space to enable capture (an "L"/"R" indicator appears).
- Press Esc to exit. Run `sudo alsactl store` to persist.

### `aplay` outputs silence (Bluetooth or PipeWire setup)

`aplay` is an ALSA-only tool. On Pi distributions running PipeWire or
PulseAudio (most modern setups, especially with Bluetooth headsets), it
often lands on the wrong card — HDMI instead of your headset, for example.

Switch RasaPi's playback to `paplay`:

```env
VOICE_TTS_PLAYBACK_COMMAND=paplay
```

Or use `auto` (the default), which prefers `paplay` when it's available.

Make sure `paplay` is installed:

```bash
which paplay || sudo apt install pulseaudio-utils
```

If you really do want raw ALSA output:

```bash
aplay -L | head -20
```

Try `default` instead of an explicit `plughw:` line. Update
`VOICE_DEVICE_OUTPUT` accordingly and set
`VOICE_TTS_PLAYBACK_COMMAND=aplay`.

### Piper says "Piper model not found"

You've set `VOICE_TTS_ENGINE=piper` but `VOICE_PIPER_MODEL_PATH` is empty
or points at a file that doesn't exist.

```bash
ls -la $(grep ^VOICE_PIPER_MODEL_PATH ~/rasapi-local-ai-assistant/.env | cut -d= -f2-)
```

Fix the path in `.env`, then `sudo systemctl restart rasapi`.

### Whisper says "Whisper model not found"

Same story:

```bash
ls -la $(grep ^VOICE_WHISPER_MODEL_PATH ~/rasapi-local-ai-assistant/.env | cut -d= -f2-)
```

Set `VOICE_WHISPER_MODEL_PATH` to a real `.bin` file (e.g.
`~/whisper.cpp/models/ggml-tiny.en.bin`).

### Whisper inference is slow

`tiny.en` is the fastest model that still produces useful transcripts
on a Pi 5 CPU. If it's still too slow:

- Lower the recording duration: `VOICE_RECORD_SECONDS=3`
- Run Whisper on a faster machine and call its server. (Out of scope
  for Phase 7 — would need a network adapter.)

### Piper voice file not found

Make sure the `.onnx` file *and* its `.onnx.json` config sit in the same
directory and are readable. The Piper binary loads both.

### `EngineNotAvailable` from the CLI

The configured engine binary isn't on `$PATH`. Re-check step 5/6 and that
the `voice` group is active for your user:

```bash
groups
which arecord whisper-cli espeak-ng piper aplay
```

### High CPU during STT

Whisper is CPU-intensive. The Pi 5 will run hot. A small heatsink or
case-fan helps. Consider `tiny.en` and shorter recordings.

### Voice CLI runs but the dashboard "Voice" card still shows "disabled"

You changed `.env` but didn't restart the service. Run:

```bash
sudo systemctl restart rasapi
```

Then refresh the dashboard.

---

## What stays out of scope (per Phase 7 charter)

- ❌ Wake word ("Hey RasaPi" etc.)
- ❌ Always-listening / continuous capture
- ❌ Browser microphone, WebRTC, live streaming
- ❌ Cloud speech APIs (Google, Azure, Whisper API)
- ❌ Always-on voice systemd worker (separate from the existing `rasapi.service`)
- ❌ Remote voice access (no public exposure)

These are tracked in `docs/roadmap.md` for future phases.
