"""Streaming helpers for JSON chunk arrays."""
import json
from pathlib import Path
from typing import Iterator


def iter_json_array_items(path: Path, read_size: int = 64 * 1024) -> Iterator[dict]:
    """Yield objects from a top-level JSON array without loading it fully."""
    decoder = json.JSONDecoder()
    buffer = ""
    pos = 0
    started = False
    eof = False

    def fill() -> None:
        nonlocal buffer, eof
        if eof:
            return
        chunk = f.read(read_size)
        if chunk:
            buffer += chunk
        else:
            eof = True

    def compact() -> None:
        nonlocal buffer, pos
        if pos > read_size:
            buffer = buffer[pos:]
            pos = 0

    with open(path, "r", encoding="utf-8") as f:
        while True:
            while pos >= len(buffer) and not eof:
                fill()
            while pos < len(buffer) and buffer[pos].isspace():
                pos += 1
                compact()
                while pos >= len(buffer) and not eof:
                    fill()

            if pos >= len(buffer):
                if eof:
                    if started:
                        raise json.JSONDecodeError("Unterminated JSON array", buffer, pos)
                    raise json.JSONDecodeError("Empty JSON file", buffer, pos)
                continue

            if not started:
                if buffer[pos] != "[":
                    raise json.JSONDecodeError("Expected JSON array", buffer, pos)
                pos += 1
                started = True
                continue

            if buffer[pos] == "]":
                return
            if buffer[pos] == ",":
                pos += 1
                continue

            while True:
                try:
                    item, end = decoder.raw_decode(buffer, pos)
                    break
                except json.JSONDecodeError:
                    if eof:
                        raise
                    fill()
            if not isinstance(item, dict):
                raise json.JSONDecodeError("Expected object in JSON array", buffer, pos)
            pos = end
            compact()
            yield item


def iter_json_array_batches(path: Path, batch_size: int) -> Iterator[list[dict]]:
    """Yield object batches from a top-level JSON array."""
    batch_size = max(1, int(batch_size))
    batch: list[dict] = []
    for item in iter_json_array_items(path):
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def append_json_array_items(file_obj, items: list[dict], first_item: bool) -> bool:
    """Append JSON objects to an already-open array file."""
    for item in items:
        if not first_item:
            file_obj.write(",\n")
        json.dump(item, file_obj, ensure_ascii=False)
        first_item = False
    return first_item
