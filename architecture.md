# Saydo — Architecture

## 1. Project Overview

**Saydo** is a Windows-first AI voice input application inspired by modern AI dictation tools such as Wispr Flow.

The primary interaction is:

**Press → Speak → Release → Text appears**

The application is designed around a short local voice-input pipeline with optional AI text processing.

The current implementation prioritizes:

- low-latency voice input;
- local speech recognition;
- reliable text injection;
- hands-free dictation;
- conservative text correction;
- Windows desktop integration;
- measurable and testable core logic.

---

## 2. Current Architecture

The current application pipeline is:

```text
                    ┌──────────────────────┐
                    │      Right Ctrl      │
                    │     Global Hotkey    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Audio Recorder    │
                    │                      │
                    │ microphone capture   │
                    │ realtime audio       │
                    │ silence trimming     │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      GigaAM-v3       │
                    │      e2e-CTC         │
                    │     Local STT        │
                    └──────────┬───────────┘
                               │
                         raw transcript
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Text Processor    │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Dictionary / Snippets│
                    └──────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
                INSTANT                  AI
                    │                     │
                    │              ┌──────┴──────┐
                    │              │ LLM Router  │
                    │              └──────┬──────┘
                    │                     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Text Injector     │
                    │   Clipboard + Paste  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Active Window     │
                    │ Browser / IDE / etc. │
                    └──────────────────────┘
3. Design Principles
3.1 Local-first

The primary STT implementation is local.

The application must remain useful without an internet connection when using local processing.

3.2 Low latency

The voice-input path should contain as few heavyweight operations as possible.

The default AI path does not use extended model reasoning/thinking because latency is more important than deep reasoning for dictation cleanup.

3.3 Component isolation

Core functionality is separated into:

hotkey handling;
audio recording;
speech recognition;
text processing;
dictionary;
snippets;
LLM processing;
text injection;
persistent storage;
Windows integration;
UI.

Components should communicate through simple interfaces and data rather than depending on each other's implementation details.

3.4 Testability

Business logic must be testable without requiring:

a physical microphone;
a real global keyboard hook;
a running LLM;
a downloaded STT model;
a graphical desktop session.

External systems are mocked in unit tests.

4. Hotkey System

The global hotkey is currently:
Right Ctrl   
The HotkeyManager implements three interaction patterns.

Normal dictation
Right Ctrl down
       │
       ▼
 wait 200 ms
       │
       ▼
 recording starts
       │
       ▼
Right Ctrl up
       │
       ▼
 recording stops

The 200 ms threshold prevents accidental taps from starting dictation.

Double tap

A second press within the configured double-tap window can activate hands-free mode.

press → release → press
             │
             ▼
        hands-free
Hands-free

Hands-free mode allows the user to dictate without continuously holding the hotkey.

The system stops automatically after the configured silence/pause condition.

Hotkey guarantees

The manager:

ignores events from other keys;
ignores repeated down events while the key is held;
ignores stray up events;
cancels pending timers when a new interaction starts;
prevents duplicate recording starts;
supports clean shutdown.
5. Audio Subsystem

app/audio/recorder.py owns microphone capture.

Responsibilities:

open the selected microphone;
capture audio;
maintain recording state;
provide realtime audio data;
finalize recordings;
trim leading and trailing silence.

The recorder is thread-safe.

Silence trimming

Silence trimming is applied only to the beginning and end of a recording.

Internal pauses are preserved.

This is important for natural speech because pauses inside a sentence can carry meaningful timing and should not be removed aggressively.

Current trimming parameters are configured around:

Silence threshold: -42 dB
Analysis frame:     20 ms
Padding:            120 ms

The exact implementation remains isolated inside the audio subsystem.

6. Speech Recognition
Current STT

The project uses:

GigaAM-v3 e2e-CTC

as the local speech recognition engine.

The GigaAM project is maintained by Salute Developers:

https://github.com/salute-developers/GigaAM

The previous Whisper implementation has been removed from the application architecture.

There is intentionally no active Whisper provider in the current STT pipeline.

STT responsibilities

The STT subsystem is responsible for:

loading the speech recognition model;
selecting the available hardware;
processing audio;
producing transcription text;
handling model/runtime errors;
supporting realtime transcription.

The rest of the application should not depend on GigaAM-specific model internals.

7. Hardware Selection

Local AI components use the available hardware where possible.

The application supports:

CUDA GPU
   │
   └── preferred when available

CPU
   │
   └── fallback

Hardware detection is isolated from the higher-level application logic.

A missing or unavailable CUDA environment should not make the application unusable when CPU execution is possible.

8. Realtime Transcription

Saydo supports realtime transcription while recording.

The intended flow is:

Microphone
    │
    ├── audio chunk
    │
    ▼
GigaAM-v3
    │
    ▼
partial transcription
    │
    ▼
UI / recording state

Realtime transcription is used to reduce perceived latency and provide feedback while the user is speaking.

The final transcription is still treated as the authoritative text for the processing pipeline.

9. Text Processing

app/text/processor.py provides lightweight text processing.

The processor is intentionally inexpensive because it is part of the default voice-input path.

The text processing stage sits between raw STT output and the final dictionary/snippet/AI processing.

The architecture avoids requiring an LLM for basic dictation cleanup.

10. Dictionary

The user dictionary is a local persistent component.

Responsibilities:

store user-defined replacements;
apply known corrections to transcriptions;
preserve user terminology;
support learning from manual corrections.

Dictionary processing belongs to the Instant path and therefore does not require an LLM.

Conservative learning

When the user manually edits a transcription, Saydo can compare the original recognized text with the edited version.

Only conservative word-level replacements are considered.

Punctuation and whitespace changes alone do not create dictionary entries.

Duplicate corrections are avoided.

The learning logic is isolated in:

app/core/dictionary_learner.py
11. Snippets

Snippets provide reusable text expansions.

They are stored locally and can be applied during text processing.

The snippets subsystem is independent from the STT and LLM providers.

12. Processing Modes

Saydo currently supports two main processing modes.

INSTANT

The low-latency path:

STT
 ↓
Text Processor
 ↓
Dictionary / Snippets
 ↓
Injection

The goal is minimal delay between speech and text insertion.

AI

The AI path adds LLM processing:

STT
 ↓
Text Processor
 ↓
Dictionary / Snippets
 ↓
LLM
 ↓
Injection

AI mode is intended for more sophisticated cleanup and formatting.

13. LLM Subsystem

The LLM subsystem is separated from the main application pipeline.

Current architecture:

                    ┌──────────────────┐
                    │    LLM Router    │
                    └────────┬─────────┘
                             │
                    strategy selection
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
             Local LLM               Cloud LLM
                 │
                 ▼
               Ollama
Local LLM

Local processing is provided through Ollama.

The application communicates with the local Ollama service rather than embedding a specific LLM implementation into the UI.

Routing

The LLM strategy supports the concepts:

AUTO
LOCAL
CLOUD

AUTO allows the application to select the appropriate available provider.

The router is responsible for provider selection.

The rest of the application should not contain provider-specific routing logic.

Thinking

Extended LLM thinking is disabled by default.

For voice dictation, response latency is generally more important than additional reasoning depth.

14. Text Styles

AI mode supports custom text styles.

Styles define how the LLM should format the final text.

Examples of possible style intents include:

neutral;
professional;
concise;
custom user-defined formatting.

Styles are applied only where AI processing is enabled.

They are not part of the low-latency Instant path.

15. Text Injection

app/injection/text_injector.py is responsible for inserting final text into the currently focused application.

The current strategy is:

Final text
    │
    ▼
Clipboard
    │
    ▼
Ctrl+V
    │
    ▼
Active application

Before injection, Saydo preserves the existing clipboard contents.

After the paste operation, the previous clipboard contents are restored.

This keeps the voice-input operation transparent to the rest of the user's workflow.

16. History

Saydo maintains local dictation history.

History records contain information needed to display and analyze previous utterances, including:

timestamp;
transcription text;
raw transcription where applicable;
duration;
word count;
words per minute.

The history is stored locally.

History is also used by the dictionary-learning workflow when the user edits previous transcriptions.

17. Statistics

Saydo collects local dictation statistics.

Current metrics include:

Words
Duration
WPM
Timestamp

Statistics can be exported to CSV from the application settings.

The generated CSV is user data and should not be committed to the source repository.

18. Persistent User Data

User-specific data is stored separately from application source code.

Examples include:

data/
├── history.json
├── dictionary.json
└── ...

These files contain user-specific state and should not be committed to the repository.

Generated statistics exports are also considered local user data.

19. Windows Integration

Saydo is currently Windows-first.

Single instance

The application uses a Windows named mutex to prevent multiple application instances from running simultaneously.

If another Saydo instance is already running, the user receives a Windows notification instead of starting a second main instance.

Autostart

Saydo can register itself in the current user's Windows startup settings.

The implementation uses the per-user Windows Run registry key.

The setting is exposed through the dashboard.

Tray

The tray provides persistent application access while Saydo is running.

Overlay

The recording overlay provides visual feedback without taking focus away from the active application.

20. Application UI

The UI is implemented with PySide6.

Main UI responsibilities are separated into:

Dashboard
Overlay
Tray
Dashboard

The dashboard provides:

application settings;
dictation mode selection;
AI configuration;
dictionary management;
snippets;
styles;
history;
statistics export;
Windows autostart.
Overlay

The overlay provides lightweight visual recording feedback.

It should remain non-intrusive and must not steal focus from the application where the user is dictating.

Tray

The tray provides persistent access to the application while the dashboard is closed.

21. Logging

Saydo uses Python's standard logging system.

The logging subsystem provides:

configurable log level;
console logging;
rotating file logging;
UTF-8 log files;
separate application logging from business logic.

Logs are written to:

logs/saydo.log

Log files are rotated to prevent unlimited growth.

22. Runtime

app/runtime.py contains runtime/environment configuration shared by application components.

Runtime configuration includes environment-specific behavior such as hardware/runtime setup.

The application should keep runtime-specific configuration separate from business logic.

23. Error Handling

External dependencies must fail gracefully where possible.

Examples:

CUDA unavailable
      ↓
CPU fallback

LLM unavailable
      ↓
AI processing error / fallback handling

Clipboard failure
      ↓
restore attempt + error logging

Missing model
      ↓
explicit startup error

An external provider failure should not corrupt persistent user data.

24. Testing Architecture

The project uses automated tests for core application logic.

The test suite currently covers the major deterministic components, including:

audio recording logic;
silence trimming;
hotkey state handling;
dictionary;
dictionary learning;
snippets;
styles;
processing modes;
pipeline;
LLM routing/settings;
autostart;
single-instance logic;
logging;
text injection;
runtime helpers.

External systems are mocked where appropriate.

Examples:

Real microphone      → mocked
Global keyboard hook → mocked
Windows registry     → mocked
Windows mutex        → mocked
Clipboard            → mocked
LLM service          → mocked
STT model loading    → mocked
Timers / system time → controlled in tests

Tests should verify observable behavior rather than implementation details.

The hotkey tests use controlled monotonic time instead of real sleeps so that timing-dependent tests remain fast and deterministic.

25. Current Project Structure
Saydo/
│
├── app/
│   ├── audio/
│   │   └── recorder.py
│   │
│   ├── core/
│   │   ├── autostart.py
│   │   ├── dictionary.py
│   │   ├── dictionary_learner.py
│   │   ├── logging.py
│   │   ├── modes.py
│   │   ├── pipeline.py
│   │   ├── single_instance.py
│   │   ├── snippets.py
│   │   └── style.py
│   │
│   ├── hotkey/
│   │   └── manager.py
│   │
│   ├── injection/
│   │   └── text_injector.py
│   │
│   ├── llm/
│   │   ├── base.py
│   │   ├── hardware.py
│   │   ├── local.py
│   │   ├── ollama.py
│   │   ├── router.py
│   │   └── settings.py
│   │
│   ├── stt/
│   │   └── local_gigaam.py
│   │
│   ├── text/
│   │   └── processor.py
│   │
│   ├── ui/
│   │   ├── dashboard.py
│   │   ├── overlay.py
│   │   └── tray.py
│   │
│   └── runtime.py
│
├── data/
│   ├── dictionary.json
│   └── history.json
│
├── logs/
│
├── models/
│
├── tests/
│
├── main.py
├── requirements.txt
├── README.md
└── architecture.md

The exact file structure may evolve. The functional boundaries between subsystems are more important than individual filenames.

26. Dependency Boundaries

The intended dependency direction is:

UI
 │
 ▼
Application / Core
 │
 ├── Audio
 ├── STT
 ├── Text Processing
 ├── Dictionary
 ├── Snippets
 ├── LLM
 └── Injection

Infrastructure-specific implementations should not leak into unrelated components.

For example:

the UI should not call GigaAM directly;
the UI should not contain Ollama request logic;
the STT layer should not manipulate the clipboard;
the LLM layer should not control the global hotkey;
dictionary learning should not depend on PySide6 widgets.
27. Performance Priorities

For the main dictation path, priority is:

1. Perceived latency
2. Transcription quality
3. Injection reliability
4. Resource usage
5. Advanced processing

Heavy processing should not be introduced into the Instant path without a measurable benefit.

The project should prefer measurable optimizations over speculative micro-optimizations.

Important benchmark dimensions include:

transcription latency;
end-to-end latency;
CPU usage;
GPU usage;
memory usage;
transcription quality.
28. Hackathon Strategy

The primary goal is to maximize similarity to the interaction model of modern AI dictation products, especially Wispr Flow.

The core demonstration should remain simple:

Press Right Ctrl
      ↓
Speak
      ↓
Release
      ↓
Clean text appears in the active application

Additional functionality exists to improve this core experience:

Realtime transcription
Hands-free mode
Dictionary
Snippets
AI cleanup
Styles
History
Statistics
Windows integration

Features should be prioritized by their impact on:

dictation speed;
perceived latency;
transcription quality;
reliability;
user experience.
29. Current Limitations

The current implementation is Windows-first.

Some architecture concepts may support future cloud providers or additional AI backends, but only implemented providers should be considered production features.

The current local STT architecture is based on GigaAM-v3.

The previous Whisper implementation is intentionally no longer part of the application.

The UI contains substantially more code than the deterministic core because it combines dashboard, settings, history, dictionary, snippets, styles and Windows desktop integration.

30. Architectural Rule

The most important rule of the project is:

Keep the voice-input path fast, reliable and understandable.

The architecture should serve the interaction:

Press → Speak → Release → Text appears

rather than adding abstraction for its own sake.            