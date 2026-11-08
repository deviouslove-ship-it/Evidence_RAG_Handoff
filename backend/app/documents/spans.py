"""Locate exact source text spans within one extracted PDF page."""


class PageTextLocator:
    def __init__(self, text: str) -> None:
        self.text = text
        chars: list[str] = []
        self._starts: list[int] = []
        self._ends: list[int] = []
        for index, char in enumerate(text):
            if char.isspace():
                if not chars:
                    continue
                if chars[-1] == " ":
                    self._ends[-1] = index + 1
                else:
                    chars.append(" ")
                    self._starts.append(index)
                    self._ends.append(index + 1)
            else:
                chars.append(char)
                self._starts.append(index)
                self._ends.append(index + 1)
        if chars and chars[-1] == " ":
            chars.pop()
            self._starts.pop()
            self._ends.pop()
        self._normalized = "".join(chars)

    def find(self, text: str) -> tuple[int, str] | None:
        """Unique match anywhere on the page, or None (ambiguous or absent)."""
        found = self.find_unique(text)
        return None if found is None else (found[0], found[1])

    def find_unique(self, text: str) -> tuple[int, str, int] | None:
        needle = " ".join(text.split())
        if not needle:
            return None
        start = self._normalized.find(needle)
        if start < 0 or self._normalized.find(needle, start + 1) >= 0:
            return None
        return self._result(start, len(needle))

    def find_from(self, text: str, cursor: int) -> tuple[int, str, int] | None:
        """First match at or after ``cursor`` (a position in normalized text).

        Nodes are parsed in reading order, so the next node's text is the first
        occurrence after where the previous node ended; repeated short lines such
        as "Điều 5" are then resolved by position instead of being rejected.
        Returns (original offset, exact original text, normalized end position).
        """
        needle = " ".join(text.split())
        if not needle:
            return None
        cursor = max(cursor, 0)
        start = self._normalized.find(needle, cursor)
        if start < 0:
            return None
        # Accept the position only when it directly follows the previous node:
        # nothing but whitespace or a page number in between.  Otherwise the
        # caller falls back to a unique match, so repeated text is never guessed.
        gap = self._normalized[cursor:start].strip()
        if gap and not (gap.isdigit() and len(gap) <= 4):
            return None
        return self._result(start, len(needle))

    def _result(self, start: int, length: int) -> tuple[int, str, int]:
        original_start = self._starts[start]
        original_end = self._ends[start + length - 1]
        return original_start, self.text[original_start:original_end], start + length
