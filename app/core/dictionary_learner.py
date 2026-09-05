from __future__ import annotations

import difflib
import re


class DictionaryLearner:
    """Detect conservative word-level corrections in edited transcriptions."""

    @staticmethod
    def _word_tokens(text: str) -> list[str]:
        """Extract words while ignoring punctuation and whitespace."""
        return re.findall(
            r"[\w]+(?:[-’'][\w]+)*",
            text,
            flags=re.UNICODE,
        )

    @classmethod
    def find_corrections(
        cls,
        original: str,
        edited: str,
    ) -> list[tuple[str, str]]:
        """
        Find actual word replacements.

        Punctuation-only and whitespace-only changes are ignored.
        Insertions/deletions are ignored to keep the dictionary clean.
        Each detected replacement is returned as (recognized, corrected).
        """
        old_words = cls._word_tokens(original)
        new_words = cls._word_tokens(edited)

        if not old_words or not new_words:
            return []

        matcher = difflib.SequenceMatcher(
            a=[word.casefold() for word in old_words],
            b=[word.casefold() for word in new_words],
        )

        candidates: list[tuple[str, str]] = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue

            # Only one-to-one word replacements are safe to learn.
            if (i2 - i1) != (j2 - j1):
                continue

            for old, new in zip(old_words[i1:i2], new_words[j1:j2], strict=False):
                if old.casefold() != new.casefold():
                    candidates.append((old, new))

        unique: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for source, replacement in candidates:
            key = (source.casefold(), replacement.casefold())
            if key in seen:
                continue
            seen.add(key)
            unique.append((source, replacement))

        return unique

