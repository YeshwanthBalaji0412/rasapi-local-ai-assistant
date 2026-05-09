# RasaPi — Raspberry Pi Audio Setup (Phase 7)

End-to-end audio setup for push-to-talk voice on a Raspberry Pi 5. The
backend works without any of this — voice is **opt-in** and disabled by
default. Follow these steps only when you want spoken interaction.

> Phase 7 is **push-to-talk only**. There is no wake word, no
> always-listening mode, no browser microphone, and no cloud speech
> service. Audio never leaves the Pi.

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

### Option A — espeak-ng (lightweight, recommended for first run)

```bash
sudo apt install -y espeak-ng
espeak-ng "Hello, I am RasaPi"
```

Robotic-sounding but rock-solid and ~5 MB.

### Option B — Piper TTS (better quality, optional)

```bash
# In the project venv:
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate
pip install piper-tts

# Download a voice model (~50 MB):
mkdir -p ~/piper-voices && cd ~/piper-voices
# See https://github.com/rhasspy/piper#voices for the full list. Example:
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Test:
echo "Hello, I am RasaPi" | piper --model ~/piper-voices/en_US-lessac-medium.onnx --output_file /tmp/piper.wav
aplay /tmp/piper.wav
```

The shipped `PiperTTS` adapter assumes the `piper` binary is on `PATH`.
Some installs put it under `~/.local/bin` — make sure that's in your `$PATH`
or symlink it.

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

For better accuracy at higher CPU cost, swap to `base.en` (~150 MB):

```bash
bash ./models/download-ggml-model.sh base.en
```

## 7. Configure `.env` to use real engines

```env
ENABLE_VOICE=true
VOICE_RECORDER_ENGINE=arecord
VOICE_STT_ENGINE=whisper          # or 'mock' to skip STT during early testing
VOICE_TTS_ENGINE=espeak           # or 'piper' once you've set up a voice
VOICE_DEVICE_INPUT=plughw:1,0     # match your `arecord -l` output
VOICE_DEVICE_OUTPUT=plughw:0,0
VOICE_RECORD_SECONDS=5
VOICE_SAVE_AUDIO=false
```

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

### `aplay` outputs silence

Check the active card:

```bash
aplay -L | head -20
```

Try `default` instead of an explicit `plughw:` line. Update
`VOICE_DEVICE_OUTPUT` accordingly.

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
