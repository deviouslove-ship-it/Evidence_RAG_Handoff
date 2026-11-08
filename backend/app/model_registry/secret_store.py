"""Server-side store for AI API keys typed in the Admin Portal (``secret:<name>`` references).

A profile never holds a key: it holds ``env:NAME`` (the key lives in the process
environment) or ``secret:NAME`` (the key lives here, encrypted with the operating
system).  The key is written once, never returned by any API and never logged.

* Windows: each key is a file ``<store>/<name>.key`` protected with DPAPI under the
  account that runs the server, with an application-specific entropy.  Another account
  or another machine cannot decrypt it; copying the file elsewhere is useless.
* Any other platform: no protector, the store reports ``available = False`` and keys
  must be supplied as ``env:NAME``.  Nothing falls back to plain text.

The directory comes from deployment configuration (``EVIDENCE_SECRET_STORE_DIR``); no path
is built into the code.  When it is not configured the store is unavailable.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

SECRET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
SECRET_PREFIX = "secret:"
_MAGIC = b"EVSEC1\n"
_ENTROPY = b"evidence-rag/ai-api-key/v1"
_MAX_KEY_BYTES = 4096


class SecretStoreError(RuntimeError):
    """A coded failure; the message never contains a key or a path."""


Protector = tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]


def secret_name(ref: str) -> str | None:
    """The store name of a ``secret:`` reference, or None when it is not one."""

    if not ref.startswith(SECRET_PREFIX):
        return None
    name = ref[len(SECRET_PREFIX):]
    return name if SECRET_NAME.fullmatch(name) else None


def _dpapi() -> Protector | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    ui_forbidden = 0x1

    def blob(data: bytes) -> tuple[Blob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data, len(data))
        return Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    def run(function: str, data: bytes) -> bytes:
        source, keep_source = blob(data)
        entropy, keep_entropy = blob(_ENTROPY)
        out = Blob()
        call = getattr(crypt32, function)
        if function == "CryptProtectData":
            ok = call(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                      ui_forbidden, ctypes.byref(out))
        else:
            ok = call(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                      ui_forbidden, ctypes.byref(out))
        del keep_source, keep_entropy
        if not ok:
            raise SecretStoreError("MODEL_SECRET_UNAVAILABLE")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))

    return (lambda data: run("CryptProtectData", data),
            lambda data: run("CryptUnprotectData", data))


class SecretStore:
    def __init__(self, root: Path | None, protector: Protector | None = None) -> None:
        self.root = root
        self._protector = protector if protector is not None else (
            _dpapi() if root is not None else None)

    @classmethod
    def from_env(cls) -> SecretStore:
        value = os.getenv("EVIDENCE_SECRET_STORE_DIR", "").strip()
        return cls(Path(value) if value else None)

    @property
    def available(self) -> bool:
        return self.root is not None and self._protector is not None

    def _path(self, name: str) -> Path:
        if self.root is None or not SECRET_NAME.fullmatch(name):
            raise SecretStoreError("MODEL_SECRET_REF_INVALID")
        return self.root / f"{name}.key"

    def put(self, name: str, value: str) -> None:
        if not self.available or self._protector is None:
            raise SecretStoreError("SECRET_STORE_UNAVAILABLE")
        secret = value.strip().encode("utf-8")
        if not secret or len(secret) > _MAX_KEY_BYTES or b"\n" in secret or b"\r" in secret:
            raise SecretStoreError("MODEL_SECRET_INVALID")
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _MAGIC + self._protector[0](secret)
        # Write beside the target, then replace: a crash never leaves half a key.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".key")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
            os.replace(temporary, path)
        except OSError as exc:
            Path(temporary).unlink(missing_ok=True)
            raise SecretStoreError("SECRET_STORE_UNAVAILABLE") from exc

    def get(self, name: str) -> str | None:
        """The key, or None when this name has none.  A key that cannot be decrypted
        (other account, damaged file) raises instead of looking absent."""

        if not self.available or self._protector is None:
            raise SecretStoreError("SECRET_STORE_UNAVAILABLE")
        path = self._path(name)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SecretStoreError("MODEL_SECRET_UNAVAILABLE") from exc
        if not payload.startswith(_MAGIC):
            raise SecretStoreError("MODEL_SECRET_UNAVAILABLE")
        try:
            return self._protector[1](payload[len(_MAGIC):]).decode("utf-8")
        except (SecretStoreError, UnicodeDecodeError) as exc:
            raise SecretStoreError("MODEL_SECRET_UNAVAILABLE") from exc

    def has(self, name: str) -> bool:
        try:
            return self.available and self._path(name).is_file()
        except SecretStoreError:
            return False

    def delete(self, name: str) -> None:
        if self.root is not None:
            self._path(name).unlink(missing_ok=True)
