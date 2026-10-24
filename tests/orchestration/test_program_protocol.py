import asyncio
import io
import struct

import pytest

from mcp_execution_lab.program_sdk.protocol import (
    ProtocolError,
    decode,
    encode,
    read,
    read_async,
)


def test_frames_preserve_unicode_and_do_not_consume_the_next_message():
    stream = io.BytesIO(encode({"id": 1, "value": "₹"}) + encode({"id": 2}))
    assert read(stream) == {"id": 1, "value": "₹"}
    assert read(stream) == {"id": 2}
    with pytest.raises(EOFError):
        read(stream)


@pytest.mark.parametrize(
    "payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b"[]", b"\xff"]
)
def test_frames_reject_ambiguous_or_invalid_json(payload):
    with pytest.raises(ProtocolError):
        decode(payload)


def test_length_is_checked_before_reading_or_allocating_the_payload():
    with pytest.raises(ProtocolError):
        read(io.BytesIO(struct.pack("!I", 4096)), limit=32)
    with pytest.raises(ProtocolError):
        encode({"value": "x" * 40}, limit=32)
    with pytest.raises(EOFError):
        read(io.BytesIO(struct.pack("!I", 4) + b"{}"))


def test_large_numbers_and_deep_structures_are_protocol_errors():
    with pytest.raises(ProtocolError):
        decode(b'{"n":' + b"9" * 5000 + b"}")
    with pytest.raises(ProtocolError):
        encode({"nested": [[[[{}]]]]}, limit=8)
    with pytest.raises(ProtocolError):
        decode(b'{"n":' + b"[" * 66 + b"0" + b"]" * 66 + b"}")


async def test_async_pipe_reader_handles_fragmented_frames_and_truncation():
    reader = asyncio.StreamReader()
    frame = encode({"id": 1})
    reader.feed_data(frame[:2])
    pending = asyncio.create_task(read_async(reader))
    await asyncio.sleep(0)
    reader.feed_data(frame[2:])
    assert await pending == {"id": 1}
    reader.feed_eof()
    with pytest.raises(EOFError):
        await read_async(reader)
