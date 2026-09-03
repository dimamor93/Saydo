# Saydo — Architecture

## 1. Project

**Saydo** is a Windows-first AI voice input application inspired by the interaction model of modern AI dictation tools.

Core principle:

> Saydo turns spoken intent into clean text or, later, actions — not merely raw speech-to-text.

The first hackathon target is a working vertical slice:

**Global Hotkey → Record → STT → Text → Clipboard → Paste**

The architecture must allow local and cloud AI providers without coupling the core application to a specific model or vendor.

---

## 2. Goals

### MVP goals

- Global hotkey starts/stops recording.
- Microphone audio is captured reliably.
- Speech is converted to text.
- Result is inserted into the currently focused application.
- Local STT is supported.
- Cloud STT is supported through a provider abstraction.
- Russian and English are supported.
- The application remains usable when a provider fails.

### Non-goals for MVP

- Cross-platform support.
- Full feature parity with Wispr Flow.
- Complex autonomous computer control.
- Multiple cloud vendors.
- Advanced user analytics.
- Mobile applications.

---

## 3. High-Level Architecture

```text
                         ┌──────────────────┐
                         │      User        │
                         └────────┬─────────┘
                                  │
                             Global Hotkey
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Session/Core   │
                         └────────┬─────────┘
                                  │
                             Record Audio
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Audio Engine   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   STT Adapter    │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
             ┌──────────────┐           ┌──────────────┐
             │  Local STT   │           │  Cloud STT   │
             │ faster-whisper│          │    API       │
             └──────────────┘           └──────────────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  │
                              Transcript
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Post-processing  │
                         │      LLM         │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Text Injection   │
                         └────────┬─────────┘
                                  │
                           Clipboard / Paste
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Active App       │
                         │ Browser / IDE /  │
                         │ Word / Terminal  │
                         └──────────────────┘
```

---

## 4. Core Components

### 4.1 Session / Core

Owns the lifecycle of a dictation session.

State machine:

```text
IDLE
  │
  │ hotkey pressed
  ▼
RECORDING
  │
  │ hotkey released
  ▼
PROCESSING
  │
  ├── success ──► INJECTING ──► IDLE
  │
  └── error ───► ERROR ───────► IDLE
```

The Core must not know implementation details of individual STT or LLM providers.

---

### 4.2 Hotkey Manager

Responsibilities:

- Register global hotkey.
- Detect press/release.
- Start and stop the current session.
- Prevent duplicate sessions.

The hotkey implementation is isolated from the Core.

---

### 4.3 Audio Engine

Responsibilities:

- Select microphone.
- Capture audio.
- Convert to the STT-compatible format.
- Maintain an in-memory recording buffer.
- Stop recording cleanly.

Target format:

```text
Sample rate: 16 kHz
Channels:    Mono
Encoding:    PCM
```

Optional later additions:

- Voice Activity Detection.
- Noise suppression.
- Input level monitoring.
- Automatic silence trimming.

---

## 5. Speech-to-Text Provider Architecture

STT is a replaceable provider.

Conceptual interface:

```python
class STTProvider:
    def transcribe(
        self,
        audio,
        language=None
    ) -> TranscriptionResult:
        ...
```

Result:

```python
class TranscriptionResult:
    text: str
    language: str
    duration: float
    confidence: float | None
```

### Local provider

Initial implementation:

```text
faster-whisper
        +
Whisper Large V3 Turbo
```

The exact model must remain configurable.

### Cloud provider

A cloud STT implementation must expose the same interface as Local STT.

The Core must not contain cloud-specific logic.

---

## 6. LLM Post-processing

STT output is considered raw transcription.

Post-processing is a separate pipeline:

```text
Raw transcript
      │
      ▼
Filler removal
      │
      ▼
Self-correction resolution
      │
      ▼
Punctuation
      │
      ▼
Dictionary / terminology
      │
      ▼
Context / mode formatting
      │
      ▼
Final text
```

The LLM layer must preserve user intent and must not invent information.

Potential provider architecture:

```text
LLMProvider
   ├── Local
   │    └── Ollama / llama.cpp
   │
   └── Cloud
        └── API
```

This is not required for the first vertical slice but must be compatible with the architecture.

---

## 7. Text Injection

The final text is inserted into the currently focused application.

Preferred strategy:

```text
Text
 │
 ▼
Clipboard
 │
 ▼
Paste
```

Potential fallback mechanisms:

- Keyboard simulation / SendInput.
- Windows accessibility APIs.

The injection mechanism must be isolated behind an interface.

---

## 8. UI

### Tray

Persistent application entry point.

Responsibilities:

- Application status.
- Settings access.
- Provider selection.
- Microphone selection.
- Exit.

### Overlay

Small non-intrusive recording indicator.

States:

```text
Idle
Recording
Processing
Error
```

The overlay must not block interaction with the active application.

---

## 9. Provider Configuration

The architecture supports:

```text
STT:
    Local
    Cloud

LLM:
    Local
    Cloud
```

Future mode:

```text
Auto / Hybrid
```

Example:

```text
STT → Local
LLM → Cloud
```

or:

```text
STT → Cloud
LLM → Local
```

Provider selection belongs to configuration, not Core logic.

---

## 10. Modes

The application will eventually support context-aware modes.

### Normal

Natural language dictation.

### Coding

Optimized for:

- File paths.
- Function names.
- camelCase.
- snake_case.
- CLI commands.
- Programming terminology.

### Command

Voice commands that produce application actions instead of text.

Example:

```text
"new paragraph"
"press enter"
"copy that"
```

Command mode is a later feature and is not part of MVP-01.

---

## 11. Project Structure

Target structure:

```text
saydo/
│
├── app/
│   ├── core/
│   │   ├── session.py
│   │   ├── state.py
│   │   └── events.py
│   │
│   ├── audio/
│   │   └── recorder.py
│   │
│   ├── stt/
│   │   ├── base.py
│   │   ├── local_whisper.py
│   │   └── cloud.py
│   │
│   ├── llm/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── cloud.py
│   │
│   ├── injection/
│   │   └── text_injector.py
│   │
│   ├── hotkey/
│   │   └── manager.py
│   │
│   └── ui/
│       ├── tray.py
│       ├── overlay.py
│       └── settings.py
│
├── models/
│
├── data/
│   ├── dictionary/
│   └── history/
│
├── tests/
│
├── main.py
├── requirements.txt
├── README.md
└── architecture.md
```

The exact module layout may change during implementation if a simpler structure is proven better. Architectural boundaries are more important than filenames.

---

## 12. Development Priorities

### MVP-01 — Voice → Text

Acceptance criteria:

- [ ] Application starts.
- [ ] Global hotkey works.
- [ ] Pressing the hotkey starts recording.
- [ ] Releasing it stops recording.
- [ ] Audio reaches STT.
- [ ] Whisper returns text.
- [ ] Text reaches clipboard.
- [ ] Text is pasted into the active application.
- [ ] Errors do not crash the application.

### MVP-02 — AI Cleanup

- [ ] Cloud STT provider.
- [ ] Local/cloud STT switch.
- [ ] LLM post-processing.
- [ ] Punctuation.
- [ ] Filler removal.
- [ ] Self-correction handling.

### MVP-03 — Product Demo

- [ ] Polished overlay.
- [ ] Tray UI.
- [ ] Settings.
- [ ] Microphone selection.
- [ ] Provider selection.
- [ ] Coding mode.
- [ ] Demo-ready reliability.

---

## 13. Architecture Rules

1. Core must not depend directly on a specific AI vendor.
2. STT providers must implement a common interface.
3. LLM providers must implement a common interface.
4. UI must not contain business logic.
5. Provider failures must be recoverable.
6. Local operation must remain possible without internet access.
7. The MVP path must remain short and synchronous from the user's perspective.
8. New providers should be addable without modifying Core.
9. Do not add abstractions without a concrete use case.
10. During the hackathon, a working vertical slice has priority over architectural perfection.

---

## 14. Hackathon Strategy

The project is built in vertical slices.

Priority order:

```text
1. Working voice input
2. Reliable transcription
3. Reliable text injection
4. AI cleanup
5. Local/cloud choice
6. UX polish
7. Differentiating features
```

Do not spend significant time on features that do not improve the live demo before the core loop is reliable.

The primary demo loop is:

```text
Press → Speak → Release → Text appears
```

Everything else supports this loop.
