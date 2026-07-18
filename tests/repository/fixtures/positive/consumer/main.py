"""Fixture consumer using only the public module."""

from app.public import normalize


def normalized_example() -> str:
    return normalize(" Example ")
