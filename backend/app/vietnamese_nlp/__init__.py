"""Vietnamese text normalization helpers."""

from .unicode_norm import canonical_document_number, fold_text, normalize_text, unicode_nfc

__all__ = ["canonical_document_number", "fold_text", "normalize_text", "unicode_nfc"]
