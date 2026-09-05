# Saydo dictionary logic separation

Moved word-correction detection from `app/ui/dashboard.py` into
`app/core/dictionary_learner.py`.

The UI now only:
- receives the edited text;
- asks the core learner for correction candidates;
- shows the confirmation dialog;
- persists the user's choice.

The core learner handles word tokenization and conservative word-level diffing.
Punctuation-only changes are ignored.
