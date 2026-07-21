"""Incremental stream-frame decoders + the ``ChatStream`` iterable.

Mirrors the TS SDK's ``decoders.ts`` / ``chat-stream.ts``. Both decoders accept
raw byte chunks in the arbitrary boundaries the network delivers them — mid-frame,
mid-JSON, and mid-UTF-8-codepoint splits are all handled — and yield parsed frame
objects.

The buffer is BOUNDED (mirroring the gateway + adapter SSE parsers): a
never-terminating line, or an event whose accumulated ``data:`` payload never hits
a blank separator, would otherwise grow without limit — a buggy or compromised
upstream could exhaust client memory. Crossing :data:`MAX_BUFFERED_CHARS` raises
instead of buffering further.
"""

from __future__ import annotations

import codecs
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Mapping, Optional

from ._metadata import Headers, RateLimitInfo, parse_rate_limit, request_id_from
from .errors import APIConnectionError, APIConnectionTimeoutError, RoadieError

#: Upper bound on retained (unparsed) characters, matching the adapter parsers' 4 MiB.
MAX_BUFFERED_CHARS = 4 * 1024 * 1024

_READ_CHUNK_BYTES = 8192


class StreamBufferLimitError(Exception):
    """Raised by a decoder when a frame/line exceeds :data:`MAX_BUFFERED_CHARS`."""


@dataclass(frozen=True)
class DecodedChunk:
    """A decoded output: a parsed data frame (``kind='event'``) or the SSE ``[DONE]`` sentinel."""

    kind: str  # "event" | "done"
    data: Optional[Mapping[str, Any]] = None


_DONE = DecodedChunk(kind="done")


def _strip_cr(line: str) -> str:
    return line[:-1] if line.endswith("\r") else line


class SSEDecoder:
    """Server-Sent Events decoder.

    Accumulates ``data:`` field values within an event and dispatches on the
    blank-line separator (per the SSE spec); ``:`` lines are comments (heartbeats)
    and are ignored. A data payload of ``[DONE]`` yields the terminal sentinel.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._data_lines: List[str] = []
        self._data_chars = 0

    def push(self, chunk: bytes) -> List[DecodedChunk]:
        self._buffer += self._decoder.decode(chunk)
        self._assert_within_limit()
        return self._drain_lines(at_end=False)

    def flush(self) -> List[DecodedChunk]:
        self._buffer += self._decoder.decode(b"", final=True)
        self._assert_within_limit()
        return self._drain_lines(at_end=True)

    def _drain_lines(self, at_end: bool) -> List[DecodedChunk]:
        out: List[DecodedChunk] = []
        newline_index = self._buffer.find("\n")
        while newline_index != -1:
            line = _strip_cr(self._buffer[:newline_index])
            self._buffer = self._buffer[newline_index + 1 :]
            self._consume_line(line, out)
            newline_index = self._buffer.find("\n")
        # At end-of-stream a final event may have no trailing blank line: treat any
        # buffered partial line as the last line and dispatch what we have.
        if at_end:
            if self._buffer != "":
                self._consume_line(_strip_cr(self._buffer), out)
                self._buffer = ""
            self._dispatch(out)
        return out

    def _consume_line(self, line: str, out: List[DecodedChunk]) -> None:
        if line == "":
            self._dispatch(out)
            return
        if line.startswith(":"):
            return  # comment / heartbeat — ignored
        if line.startswith("data:"):
            # A single optional leading space after the colon is stripped (SSE spec).
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            self._data_lines.append(value)
            self._data_chars += len(value)
            self._assert_within_limit()
        # Other SSE fields (event:, id:, retry:) are not used by the gateway.

    def _dispatch(self, out: List[DecodedChunk]) -> None:
        if not self._data_lines:
            return
        payload = "\n".join(self._data_lines)
        self._data_lines = []
        self._data_chars = 0
        if payload == "[DONE]":
            out.append(_DONE)
            return
        out.append(DecodedChunk(kind="event", data=json.loads(payload)))

    def _assert_within_limit(self) -> None:
        if len(self._buffer) + self._data_chars > MAX_BUFFERED_CHARS:
            raise StreamBufferLimitError(
                f"SSE frame exceeded the {MAX_BUFFERED_CHARS}-character buffer limit."
            )


class NDJSONDecoder:
    """Newline-delimited JSON decoder.

    Each non-empty line is one frame; blank lines (NDJSON heartbeats) are skipped.
    EOF is the terminal signal, so there is no ``[DONE]`` sentinel.
    """

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""

    def push(self, chunk: bytes) -> List[DecodedChunk]:
        self._buffer += self._decoder.decode(chunk)
        self._assert_within_limit()
        return self._drain_lines()

    def flush(self) -> List[DecodedChunk]:
        self._buffer += self._decoder.decode(b"", final=True)
        self._assert_within_limit()
        out = self._drain_lines()
        rest = self._buffer.strip()
        if rest != "":
            out.append(DecodedChunk(kind="event", data=json.loads(rest)))
        self._buffer = ""
        return out

    def _drain_lines(self) -> List[DecodedChunk]:
        out: List[DecodedChunk] = []
        newline_index = self._buffer.find("\n")
        while newline_index != -1:
            line = _strip_cr(self._buffer[:newline_index]).strip()
            self._buffer = self._buffer[newline_index + 1 :]
            if line != "":
                out.append(DecodedChunk(kind="event", data=json.loads(line)))
            newline_index = self._buffer.find("\n")
        return out

    def _assert_within_limit(self) -> None:
        if len(self._buffer) > MAX_BUFFERED_CHARS:
            raise StreamBufferLimitError(
                f"NDJSON line exceeded the {MAX_BUFFERED_CHARS}-character buffer limit."
            )


class StreamEvent:
    """One decoded stream frame — a typed chunk object.

    Frames intentionally mix casing on the wire (``content_delta`` carries
    ``delta``; ``message_end`` carries snake_case ``finish_reason`` / ``usage`` /
    ``cost``); the SDK exposes them verbatim. Access ``event.type`` for the
    discriminator and ``event["delta"]`` / ``event.get("usage")`` for fields.
    """

    __slots__ = ("raw",)

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.raw = raw

    @property
    def type(self) -> Optional[str]:
        """The frame's ``type`` discriminator (e.g. ``content_delta``, ``message_end``)."""
        value = self.raw.get("type")
        return value if isinstance(value, str) else None

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self.raw

    def __repr__(self) -> str:
        return f"StreamEvent(type={self.type!r}, raw={dict(self.raw)!r})"


class StreamConnection:
    """A committed 2xx streaming response: incremental reader + headers + close."""

    def __init__(self, reader: Any, headers: Headers, close: Callable[[], None]) -> None:
        self._reader = reader
        self.headers = headers
        self._close = close

    def read(self, size: int) -> bytes:
        return self._reader.read(size)

    def close(self) -> None:
        self._close()


class ChatStream:
    """The iterable returned (without connecting) by ``roadie.chat.stream(...)``.

    The HTTP connection is established LAZILY on the first iteration, so the method
    returns an iterable immediately. It reads the SSE/NDJSON body incrementally,
    yields each unified frame as a :class:`StreamEvent`, and terminates on
    ``[DONE]`` (SSE) or EOF (NDJSON). A mid-stream ``error`` frame is yielded as a
    normal terminal event — nothing follows it.

    Use it directly in a ``for`` loop, or as a context manager to guarantee the
    socket is released even on early ``break``::

        with roadie.chat.stream(model="smart", messages=msgs) as stream:
            for event in stream:
                ...
    """

    def __init__(self, connect: Callable[[], StreamConnection], framing: str) -> None:
        self._connect = connect
        self._framing = framing
        self._consumed = False
        self._generator: Optional[Iterator[StreamEvent]] = None
        #: Gateway request id (``X-Request-Id``); populated once iteration connects.
        self.request_id: Optional[str] = None
        #: Rate-limit snapshot (``X-RateLimit-*``); populated once iteration connects.
        self.rate_limit: Optional[RateLimitInfo] = None

    def __iter__(self) -> Iterator[StreamEvent]:
        if self._consumed:
            raise APIConnectionError("This stream has already been consumed.")
        self._consumed = True
        self._generator = self._iterate()
        return self._generator

    def __enter__(self) -> "ChatStream":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Stop iteration and release the underlying socket. Idempotent."""
        if self._generator is not None:
            self._generator.close()
            self._generator = None

    def _iterate(self) -> Iterator[StreamEvent]:
        connection = self._connect()
        self.request_id = request_id_from(connection.headers)
        self.rate_limit = parse_rate_limit(connection.headers)
        decoder = NDJSONDecoder() if self._framing == "ndjson" else SSEDecoder()
        try:
            while True:
                try:
                    chunk = connection.read(_READ_CHUNK_BYTES)
                except TimeoutError as error:
                    raise APIConnectionTimeoutError(
                        "The request exceeded its timeout.", request_id=self.request_id
                    ) from error
                except OSError as error:
                    raise APIConnectionError(
                        "The response stream was interrupted.", request_id=self.request_id
                    ) from error
                if not chunk:
                    break
                for decoded in self._decode(lambda: decoder.push(chunk)):
                    if decoded.kind == "done":
                        return
                    yield StreamEvent(decoded.data or {})
            for decoded in self._decode(decoder.flush):
                if decoded.kind == "done":
                    return
                yield StreamEvent(decoded.data or {})
        finally:
            connection.close()

    def _decode(self, step: Callable[[], List[DecodedChunk]]) -> List[DecodedChunk]:
        """Run a decode step, re-wrapping any failure (malformed JSON, buffer overflow)
        as an :class:`APIConnectionError` so the stream only ever raises a ``RoadieError``.
        """
        try:
            return step()
        except RoadieError:
            raise
        except Exception as error:
            raise APIConnectionError(
                f"Failed to decode the response stream: {error}", request_id=self.request_id
            ) from error
