"""Streaming: SSE/NDJSON decoders (incl. split + oversized-line safety) and the
end-to-end ``bp.chat.stream`` iterable."""

from __future__ import annotations

import pytest

from roadie import Roadie
from roadie._streaming import (
    MAX_BUFFERED_CHARS,
    NDJSONDecoder,
    SSEDecoder,
    StreamBufferLimitError,
)
from roadie.errors import APIConnectionError

from conftest import sse_response


def _drain(decoder, *byte_chunks):
    events = []
    for chunk in byte_chunks:
        events.extend(decoder.push(chunk))
    events.extend(decoder.flush())
    return events


def test_sse_decoder_parses_data_frames():
    decoder = SSEDecoder()
    payload = (
        b'data: {"type":"message_start","model":"m"}\n\n'
        b'data: {"type":"content_delta","index":0,"delta":"Hi"}\n\n'
        b"data: [DONE]\n\n"
    )
    events = _drain(decoder, payload)

    assert [e.kind for e in events] == ["event", "event", "done"]
    assert events[0].data == {"type": "message_start", "model": "m"}
    assert events[1].data == {"type": "content_delta", "index": 0, "delta": "Hi"}


def test_sse_decoder_reassembles_frames_split_across_chunks():
    # A frame split mid-JSON AND a multi-byte UTF-8 codepoint ("€" == 3 bytes)
    # split across the chunk boundary must both be reassembled.
    full = 'data: {"type":"content_delta","index":0,"delta":"€uro"}\n\n'.encode("utf-8")
    # Split at an awkward byte offset that lands in the middle of the euro sign.
    euro_start = full.index(b"\xe2\x82\xac")
    parts = [full[: euro_start + 1], full[euro_start + 1 : euro_start + 2], full[euro_start + 2 :]]

    decoder = SSEDecoder()
    events = _drain(decoder, *parts)

    assert len(events) == 1
    assert events[0].data == {"type": "content_delta", "index": 0, "delta": "€uro"}


def test_sse_decoder_joins_multiline_data_and_ignores_comments():
    decoder = SSEDecoder()
    payload = b":heartbeat\n" b'data: {"a":1,\n' b'data: "b":2}\n' b"\n"
    events = _drain(decoder, payload)

    assert len(events) == 1
    assert events[0].data == {"a": 1, "b": 2}


def test_sse_decoder_oversized_line_raises_before_ooming():
    decoder = SSEDecoder()
    # A single `data:` line that never terminates must not buffer without bound.
    giant = b"data: " + (b"x" * (MAX_BUFFERED_CHARS + 10))
    with pytest.raises(StreamBufferLimitError):
        decoder.push(giant)


def test_ndjson_decoder_parses_lines():
    decoder = NDJSONDecoder()
    payload = b'{"type":"content_delta","delta":"a"}\n\n{"type":"message_end"}\n'
    events = _drain(decoder, payload)

    assert [e.data for e in events] == [
        {"type": "content_delta", "delta": "a"},
        {"type": "message_end"},
    ]


def test_ndjson_decoder_oversized_line_raises():
    decoder = NDJSONDecoder()
    with pytest.raises(StreamBufferLimitError):
        decoder.push(b"x" * (MAX_BUFFERED_CHARS + 10))


def test_chat_stream_end_to_end_sse(mock_server):
    frames = [
        'data: {"type":"message_start","model":"openai/gpt-4o-mini"}\n\n',
        'data: {"type":"content_delta","index":0,"delta":"Hello"}\n\n',
        'data: {"type":"content_delta","index":0,"delta":" world"}\n\n',
        'data: {"type":"message_end","finish_reason":"stop",'
        '"usage":{"input_tokens":5,"output_tokens":2,"total_tokens":7,"source":"provider"}}\n\n',
        "data: [DONE]\n\n",
    ]
    mock_server.respond_with(sse_response(frames, headers={"x-request-id": "req_stream"}))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    stream = bp.chat.stream(model="smart", messages=[{"role": "user", "content": "Hi"}])
    events = list(stream)

    assert [e.type for e in events] == [
        "message_start",
        "content_delta",
        "content_delta",
        "message_end",
    ]
    text = "".join(e["delta"] for e in events if e.type == "content_delta")
    assert text == "Hello world"
    end = events[-1]
    assert end["finish_reason"] == "stop"
    assert end["usage"]["total_tokens"] == 7
    assert stream.request_id == "req_stream"

    # The stream request negotiated SSE and set stream: true.
    request = mock_server.captured[0]
    assert request.headers.get("accept") == "text/event-stream"
    assert request.json()["stream"] is True


def test_chat_stream_malformed_frame_raises_connection_error(mock_server):
    frames = ["data: {not valid json}\n\n"]
    mock_server.respond_with(sse_response(frames))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    with pytest.raises(APIConnectionError):
        list(bp.chat.stream(model="smart", messages=[{"role": "user", "content": "Hi"}]))


def test_chat_stream_cannot_be_consumed_twice(mock_server):
    mock_server.respond_with(sse_response(["data: [DONE]\n\n"]))
    bp = Roadie(api_key="rd_sk_test_key", base_url=mock_server.base_url)

    stream = bp.chat.stream(model="smart", messages=[{"role": "user", "content": "Hi"}])
    list(stream)
    with pytest.raises(APIConnectionError):
        list(stream)
