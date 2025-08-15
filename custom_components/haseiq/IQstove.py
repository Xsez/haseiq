"""Hase IQ stove websocket client (listener-only, no internal polling).

This module provides the `IQstove` client class and the `IQStoveConnectionError`
exception. It is designed to match the original integration flow where the
*coordinator* controls what to request by calling `IQstove.getValue(cmd)`.
The client:

- sends exactly one `_req=<cmd>` for each `getValue` call,
- receives base64-encoded frames of the form `key=value`,
- updates a public `values` dictionary with parsed results.

No periodic/background polling happens here; scheduling is owned by the
coordinator.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from aiohttp import ClientSession, WSMsgType

__all__ = ["IQstove", "IQStoveConnectionError"]

_LOGGER = logging.getLogger(__name__)


class IQStoveConnectionError(Exception):
    """Raised when the websocket cannot be established or used."""


@dataclass(frozen=True)
class _Commands:
    """Command groups expected by the coordinator (names must match the original)."""

    # Device info (kept as STRINGS in `values` so entities can apply their own mapping)
    info: List[str] = (
        "_oemdev",
        "_oemver",
        "_wversion",
        "_oemser",
        "_ledBri",
    )

    # Live state
    state: List[str] = (
        "appPhase",  # phase/state code
        "appT",  # temperature
        "appAufheiz",  # heating up (0/1 or percentage)
        "appP",  # performance
        "appNach",
        "appErr",
    )

    # Statistics / history
    statistics: List[str] = (
        "appPTx",
        "appP30Tx",
        "appPT[0;59]",
        "appP30T[0;29]",
        "appIQDarst",
    )


class IQstove:
    """Hase IQ stove WebSocket client.

    Protocol
    -------
    Incoming frames:
        base64("key=value")

    Requests:
        base64("_req=<key>")

    (Optional) Sets:
        base64("_set=<key>;<value>")

    Behavior
    --------
    The *coordinator* calls `getValue(cmd)` for each key it needs. This class
    only sends that request and updates `self.values` when corresponding frames
    arrive. There is no internal polling or scheduling here.
    """

    Commands = _Commands()

    def __init__(
        self,
        host: str,
        port: int = 8080,
        path: str = "/",
        *,
        session: Optional[ClientSession] = None,
        origin: Optional[str] = None,
        heartbeat: int = 30,
        connect_timeout: float = 10.0,
        max_msg_size: int = 2**20,
    ) -> None:
        """Initialize the client.

        Args:
            host: Device hostname or IP.
            port: Device websocket port (default 8080).
            path: Websocket path (leading slash optional).
            session: Optional external aiohttp ClientSession.
            origin: Value for the `Origin` header (some embedded servers require it).
            heartbeat: Ping interval in seconds for aiohttp's ws connection.
            connect_timeout: Time in seconds to wait for the initial connection.
            max_msg_size: Maximum message size accepted by the websocket.
        """
        self._host = host
        self._port = port
        self._path = path if path.startswith("/") else f"/{path}"
        self._origin = origin or f"http://{host}:{port}"
        self._heartbeat = heartbeat
        self._connect_timeout = connect_timeout
        self._max_msg_size = max_msg_size

        self._ext_session = session
        self._session: Optional[ClientSession] = session
        self._ws = None

        self._runner_task: Optional[asyncio.Task] = None
        self._closing = asyncio.Event()

        # Public store read by coordinator/entities. Keys mirror device keys,
        # with a few convenience aliases (see `_store_value`).
        self.values: Dict[str, Any] = {}

        # Optional subscribers (useful for diagnostics)
        self._listeners: List[
            Callable[[Dict[str, Any]], Union[Awaitable[None], None]]
        ] = []

    # ── lifecycle ───────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        """Return True if the websocket is currently open."""
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """Connect and start the receive loop (no internal polling)."""
        if self._runner_task and not self._runner_task.done():
            await self._wait_connected()
            return
        self._closing.clear()
        self._runner_task = asyncio.create_task(self._run(), name="IQstoveRunner")
        await self._wait_connected()

    async def close(self) -> None:
        """Stop background task and close network resources."""
        self._closing.set()
        if self._runner_task:
            self._runner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_task
            self._runner_task = None
        await self._close_ws()
        await self._close_session()

    # ── coordinator-facing API ──────────────────────────────────────────────────

    def getValue(self, cmd: str) -> asyncio.Task:
        """Send a single `_req=<cmd>` (base64 text).

        The coordinator controls cadence. A Task is returned so callers may
        `await` or fire-and-forget.

        Args:
            cmd: Device key to request (e.g., "appT").

        Returns:
            An asyncio Task that completes when the request frame is sent.
        """
        return asyncio.create_task(self._send_req(cmd))

    def setValue(self, cmd: str, value: Union[int, float, str]) -> asyncio.Task:
        """Send `_set=<cmd>;<value>` (optional, for writable entities).

        Args:
            cmd: Device key to set.
            value: Value to send (will be formatted as a string).

        Returns:
            An asyncio Task that completes when the set frame is sent.
        """
        return asyncio.create_task(self._send_set(cmd, value))

    def add_listener(
        self,
        cb: Callable[[Dict[str, Any]], Union[Awaitable[None], None]],
    ) -> None:
        """Subscribe to snapshots of `self.values` after each update.

        Args:
            cb: Callback invoked with `{"values": snapshot, "last": {key: value}}`.
        """
        self._listeners.append(cb)

    # ── internals ───────────────────────────────────────────────────────────────

    def _url(self) -> str:
        """Return the websocket URL."""
        return f"ws://{self._host}:{self._port}{self._path}"

    async def _wait_connected(self, timeout: float = 5.0) -> None:
        """Wait briefly for the connection to become ready.

        Raises:
            IQStoveConnectionError: If the socket did not become connected in time.
        """
        step = 0.05
        waited = 0.0
        while not self.connected and waited < timeout:
            await asyncio.sleep(step)
            waited += step
        if not self.connected:
            raise IQStoveConnectionError("Failed to establish websocket connection")

    async def _ensure_session(self) -> ClientSession:
        """Return an aiohttp session, creating one if necessary."""
        if self._session and not self._session.closed:
            return self._session
        if self._ext_session:
            self._session = self._ext_session
            return self._session
        self._session = ClientSession()
        return self._session

    async def _close_session(self) -> None:
        """Close the aiohttp session if this class created it."""
        if self._ext_session:
            return
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _close_ws(self) -> None:
        """Close the websocket if open."""
        if self._ws is not None:
            with contextlib.suppress(Exception):
                if not self._ws.closed:
                    await self._ws.close()
        self._ws = None

    async def _run(self) -> None:
        """Main loop: connect and pump incoming frames until closed."""
        while not self._closing.is_set():
            try:
                await self._connect_and_pump()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("IQstove: connection error: %s", exc, exc_info=True)
                # brief pause before retry
                try:
                    await asyncio.wait_for(self._closing.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
        await self._close_ws()

    async def _connect_and_pump(self) -> None:
        """Open the websocket and process incoming frames until it closes."""
        session = await self._ensure_session()
        headers = {"Origin": self._origin}

        _LOGGER.info("IQstove: connecting to %s", self._url())
        try:
            self._ws = await session.ws_connect(
                self._url(),
                heartbeat=self._heartbeat,
                compress=0,  # embedded WS servers are finicky; keep simple
                headers=headers,
                autoping=True,
                timeout=self._connect_timeout,
                max_msg_size=self._max_msg_size,
            )
        except Exception as exc:  # noqa: BLE001
            raise IQStoveConnectionError(str(exc)) from exc

        _LOGGER.info("IQstove: connected")

        try:
            async for msg in self._ws:
                if msg.type == WSMsgType.TEXT:
                    await self._on_text(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await self._on_text(msg.data.decode("utf-8", errors="replace"))
                elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    _LOGGER.info("IQstove: server closed connection")
                    break
                elif msg.type == WSMsgType.ERROR:
                    _LOGGER.warning("IQstove: websocket error: %s", msg.exception())
                    break
        finally:
            await self._close_ws()

    async def _send_req(self, key: str) -> None:
        """Send base64('_req=KEY') as a text frame.

        Args:
            key: Device key to request.
        """
        if not self.connected:
            raise IQStoveConnectionError("WebSocket not connected")
        line = f"_req={key}"
        encoded = base64.b64encode(line.encode("ascii")).decode("ascii")
        await self._ws.send_str(encoded)

    async def _send_set(self, key: str, value: Union[int, float, str]) -> None:
        """Send base64('_set=KEY;VALUE') as a text frame.

        Args:
            key: Device key to set.
            value: Value to send.
        """
        if not self.connected:
            raise IQStoveConnectionError("WebSocket not connected")
        line = f"_set={key};{value}"
        encoded = base64.b64encode(line.encode("ascii")).decode("ascii")
        await self._ws.send_str(encoded)

    # ── RX handling ─────────────────────────────────────────────────────────────

    async def _on_text(self, data_text: str) -> None:
        """Handle an incoming base64 text frame.

        Args:
            data_text: Raw base64 string sent by the device.
        """
        data_text = data_text.strip()
        try:
            decoded = base64.b64decode(data_text, validate=True).decode(
                "utf-8", "replace"
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("IQstove: invalid base64 frame: %r", data_text)
            return

        if "=" not in decoded:
            _LOGGER.debug("IQstove: missing '=' in %r", decoded)
            return

        key, value = decoded.split("=", 1)
        key = key.strip()
        value = value.strip()

        self._store_value(key, value)

        # Notify optional listeners with a snapshot
        snapshot = dict(self.values)
        for cb in list(self._listeners):
            try:
                result = cb({"values": snapshot, "last": {key: value}})
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                _LOGGER.exception("IQstove: listener failure")

    # ── storage / parsing ───────────────────────────────────────────────────────

    def _store_value(self, key: str, value: str) -> None:
        """Store a single `key=value` pair into `self.values`.

        Info keys are kept as strings; numeric keys are coerced to int/float.
        History arrays are parsed into lists and grouped under their base key.

        Also mirrors a few convenience aliases used by entities:
        - `temperature`  ← appT
        - `performance`  ← appP
        - `phase`/`state`← appPhase
        - `heatup`       ← appAufheiz
        - `error`        ← appErr

        Args:
            key: The decoded key from the device.
            value: The decoded value from the device.
        """
        now = _iso_now()

        # Info (strings only)
        if key in {"_oemdev", "_oemver", "_wversion", "_oemser"}:
            self.values[key] = value  # KEEP AS STRING
            if key == "_oemver":
                self.values["oem_version"] = value
            elif key == "_wversion":
                self.values["firmware"] = value
            elif key == "_oemser":
                self.values["serial"] = value
            self.values["_last_updated"] = now
            return

        # Simple numerics / live state
        if key == "_ledBri":
            self.values[key] = _to_int(value)
        elif key == "appP":
            perf = _to_int(value)
            self.values["appP"] = perf
            self.values["performance"] = perf
        elif key == "appT":
            temp = _to_float(value)
            self.values["appT"] = temp
            self.values["temperature"] = temp
        elif key == "appPhase":
            phase = _to_int(value)
            self.values["appPhase"] = phase
            self.values["phase"] = phase
            self.values["state"] = phase
        elif key == "appErr":
            err = _to_int(value)
            self.values["appErr"] = err
            self.values["error"] = err
        elif key == "appNach":
            self.values["appNach"] = _to_int(value)
        elif key == "appAufheiz":
            heat = _to_float(value)
            self.values["appAufheiz"] = heat
            self.values["heatup"] = heat
        elif key in {"appPTx", "appP30Tx", "appIQDarst"}:
            self.values[key] = _to_int(value)

        # History arrays
        elif key.startswith("appPT[") and key.endswith("]"):
            rng = _extract_bracket_range(key)  # e.g. "0;59"
            series = _parse_semicolon_numbers(value)
            self.values.setdefault("appPT", {})[rng] = series
        elif key.startswith("appP30T[") and key.endswith("]"):
            rng = _extract_bracket_range(key)  # e.g. "0;29"
            series = _parse_semicolon_numbers(value)
            self.values.setdefault("appP30T", {})[rng] = series

        # Unknown → keep raw
        else:
            self.values.setdefault("_other", {})[key] = value

        self.values["_last_updated"] = now


# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────
def _iso_now() -> str:
    """Return a UTC ISO-8601 timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def _extract_bracket_range(key: str) -> str:
    """Extract the `a;b` part from keys like `name[a;b]`.

    Args:
        key: A key that contains a single bracketed range.

    Returns:
        The content between brackets, or an empty string if not found.
    """
    try:
        return key[key.index("[") + 1 : key.rindex("]")].strip()
    except Exception:  # noqa: BLE001
        return ""


def _parse_semicolon_numbers(value: str) -> List[Union[int, float]]:
    """Parse a semicolon-separated series of numbers into a list.

    Args:
        value: String like `"1;2;3"` (whitespace/newlines tolerated).

    Returns:
        A list of ints/floats for each numeric token found.
    """
    out: List[Union[int, float]] = []
    for part in value.replace("\r", "").replace("\n", "").split(";"):
        token = part.strip()
        if not token:
            continue
        number: Optional[Union[int, float]] = _to_int(token)
        if number is None:
            number = _to_float(token)
        if number is not None:
            out.append(number)
    return out


def _to_int(v: Any) -> Optional[int]:
    """Try to coerce a value to int; return None on failure."""
    try:
        return int(str(v).strip())
    except Exception:  # noqa: BLE001
        return None


def _to_float(v: Any) -> Optional[float]:
    """Try to coerce a value to float; return None on failure."""
    try:
        return float(str(v).strip())
    except Exception:  # noqa: BLE001
        return None
