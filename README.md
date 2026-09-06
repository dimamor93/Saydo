# Saydo

Saydo is a Windows-first AI voice input application inspired by modern AI
dictation tools such as Wispr Flow.

The main interaction loop is:

**Press → Speak → Release → Text appears**

## Current capabilities

- Global `Right Ctrl` hotkey for dictation.
- 200 ms minimum hold threshold to ignore accidental taps.
- Double-tap `Right Ctrl` hands-free mode.
- Realtime speech transcription while recording.
- Automatic hands-free stop after a pause without new realtime transcription.
- Local speech recognition with GigaAM-v3 e2e-CTC.
- Instant and AI processing modes.
- Local LLM processing through Ollama.
- User dictionary with conservative correction learning.
- Text snippets.
- AI-only custom text styles.
- Recording overlay, tray integration and desktop dashboard.
- Clipboard-based text injection into the active application.
- Local history and settings.

## Architecture

```text
Global Hotkey
      ↓
Audio Recorder
      ↓
GigaAM-v3 STT
      ↓
Text Processor
      ↓
Dictionary / Snippets
      ↓
Instant or AI processing
      ↓
Clipboard / Paste
      ↓
Active application
The code is split into independent components for hotkeys, audio, STT,
text processing, LLM processing, injection and UI.

See architecture.md for the current architecture and
design rules.

Requirements
Windows
Python 3.12+
A working microphone
A compatible PyTorch installation for local GigaAM-v3 inference
Optional: Ollama with a local model for AI mode

Saydo uses
GigaAM-v3
for local speech recognition.

The current dependency configuration is intentionally kept compatible with
the working GigaAM-v3 environment used during development.

Installation and running

Clone the repository:
git clone https://github.com/dimamor93/Saydo.git
cd Saydo
Create and activate a virtual environment:
python -m pip install --upgrade pip
pip install -r requirements.txt
Then start Saydo:
python main.py
or Saydo.vbs in /Saydo
On first run, the local GigaAM-v3 model may need to be downloaded.

For AI mode, install
Ollama
and make sure a compatible local model is available.
Development

The project contains tests and development tooling for code quality.

Run the test suite:
pytest -q
Run tests with coverage:
python -m pytest --cov=app --cov-report=term-missing
Run Ruff:
ruff check .
Run mypy:
mypy app
License

Saydo is distributed under the MIT License, which permits use, modification,
distribution and commercial use subject to the license notice.

Development

The project is developed in vertical slices with priority given to the core
voice-input loop, reliable transcription, reliable text injection and
demo-ready UX.

New functionality should preserve the existing hotkey, realtime transcription,
hands-free, dictionary, snippets and AI processing behavior.
