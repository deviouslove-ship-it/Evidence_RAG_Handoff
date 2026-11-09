"""Shared request dependencies."""

from __future__ import annotations

from fastapi import Response

from .auth import get_principal

__all__ = ["get_principal", "no_store"]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
