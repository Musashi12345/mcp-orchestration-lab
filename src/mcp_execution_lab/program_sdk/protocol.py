"""Bounded JSON frames over inherited pipes, without sockets or host paths."""

import asyncio
import json
import math
import struct

DEFAULT_LIMIT = 4 * 1024 * 1024


class ProtocolError(ValueError):
    pass


def _constant(value):
    raise ProtocolError("Non-finite JSON numbers are not allowed.")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("Duplicate JSON keys are not allowed.")
        result[key] = value
    return result


def decode(payload):
    try:
        value = json.loads(payload, parse_constant=_constant, object_pairs_hook=_object)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("Invalid JSON frame.") from exc
    if not isinstance(value, dict):
        raise ProtocolError("A protocol frame must be an object.")
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise ProtocolError("JSON frame nesting exceeded its limit.")
        if isinstance(item, float) and not math.isfinite(item):
            raise ProtocolError("Non-finite JSON numbers are not allowed.")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def encode(value, limit=DEFAULT_LIMIT):
    if not isinstance(value, dict):
        raise ProtocolError("A protocol frame must be an object.")
    try:
        payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProtocolError("The frame is not finite JSON.") from exc
    if not 0 < len(payload) <= limit:
        raise ProtocolError("Protocol frame exceeded its byte limit.")
    # Apply identical nesting checks to outgoing messages.
    decode(payload)
    return struct.pack("!I", len(payload)) + payload


def _length(header, limit):
    size = struct.unpack("!I", header)[0]
    if not 0 < size <= limit:
        raise ProtocolError("Protocol frame exceeded its byte limit.")
    return size


def _exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError("Protocol pipe ended before a complete frame.")
        data.extend(chunk)
    return bytes(data)


def read(stream, limit=DEFAULT_LIMIT):
    return decode(_exact(stream, _length(_exact(stream, 4), limit)))


async def read_async(stream, limit=DEFAULT_LIMIT):
    try:
        size = _length(await stream.readexactly(4), limit)
        return decode(await stream.readexactly(size))
    except asyncio.IncompleteReadError as exc:
        raise EOFError("Protocol pipe ended before a complete frame.") from exc
