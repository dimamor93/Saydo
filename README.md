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
```

The code is split into independent components for hotkeys, audio, STT,
text processing, LLM processing, injection and UI.

See [`architecture.md`](architecture.md) for the current architecture and
design rules.

## Requirements

- Windows
- Python 3.12+
- A working microphone
- For local GigaAM inference, a compatible PyTorch installation
- Optional: Ollama with a local model for AI mode

The current dependency configuration is intentionally kept compatible with
the working GigaAM-v3 environment used during development.

## Running

Create and activate a virtual environment, install the project dependencies,
then run:

```powershell
python main.py
```

For development quality checks, the repository contains configuration for
Ruff and mypy. These tools are development tooling and are not required for
running the application.

## License

Saydo is distributed under the **MIT License**, which permits use, modification,
distribution and commercial use subject to the license notice.

## Development

The project is developed in vertical slices with priority given to the core
voice-input loop, reliable transcription, reliable text injection and
demo-ready UX.

New functionality should preserve the existing hotkey, realtime transcription,
hands-free, dictionary, snippets and AI processing behavior.
