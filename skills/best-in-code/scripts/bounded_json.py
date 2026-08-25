#!/usr/bin/env python3
"""Bounded, fail-closed JSON loading for Harness control files."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
	result: dict[str, Any] = {}
	for key, value in pairs:
		if key in result:
			raise ValueError(f"duplicate JSON key: {key}")
		result[key] = value
	return result


def load_bounded_json(path: Path, *, max_bytes: int, label: str) -> tuple[Any, list[str]]:
	"""Read one regular JSON file through a bounded descriptor snapshot."""
	try:
		if path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)()):
			return None, [f"{label} cannot be a symlink or junction: {path}"]
		initial = path.lstat()
		if not stat.S_ISREG(initial.st_mode) or initial.st_nlink > 1:
			return None, [f"{label} must be one regular non-hard-linked file: {path}"]
		if initial.st_size > max_bytes:
			return None, [f"{label} exceeds {max_bytes} bytes"]
		flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
		descriptor = os.open(path, flags)
		try:
			metadata = os.fstat(descriptor)
			if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink > 1:
				return None, [f"{label} must be one regular non-hard-linked file: {path}"]
			if (initial.st_dev, initial.st_ino) != (metadata.st_dev, metadata.st_ino):
				return None, [f"{label} changed while opening: {path}"]
			if metadata.st_size > max_bytes:
				return None, [f"{label} exceeds {max_bytes} bytes"]
			chunks: list[bytes] = []
			remaining = max_bytes + 1
			while remaining > 0:
				chunk = os.read(descriptor, min(64 * 1024, remaining))
				if not chunk:
					break
				chunks.append(chunk)
				remaining -= len(chunk)
			raw = b"".join(chunks)
			final = os.fstat(descriptor)
			if not stat.S_ISREG(final.st_mode) or final.st_nlink > 1:
				return None, [f"{label} must remain one regular non-hard-linked file: {path}"]
			if (metadata.st_dev, metadata.st_ino) != (final.st_dev, final.st_ino):
				return None, [f"{label} changed while reading: {path}"]
		finally:
			os.close(descriptor)
		if len(raw) > max_bytes:
			return None, [f"{label} exceeds {max_bytes} bytes"]
		data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
	except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError, MemoryError) as exc:
		return None, [f"could not read {label}: {exc}"]
	return data, []
