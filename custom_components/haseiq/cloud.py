"""Hase iQ Gen 2 cloud client (Firebase Realtime Database).

Gen 2 controllers have no local live interface. They publish to the Firebase
project used by the HASE iQ app, which is read with an anonymous Firebase
session over REST and Server-Sent Events.

This module does not depend on Home Assistant. The `IQstoveCloud` client keeps
a local copy of every RTDB node of one oven (see `NODES`) and notifies
listeners whenever one of them changes.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

__all__ = [
    "CloudAuthError",
    "CloudConnectionError",
    "FirebaseAuth",
    "HaseCloudError",
    "InvalidShareLink",
    "IQstoveCloud",
    "NODES",
    "decode_share_link",
]

_LOGGER = logging.getLogger(__name__)

# Build-time constants of the HASE iQ Android app.
API_KEY = "AIzaSyBwCFpwvTZLUDqIJA-UZm2pNUxSiXdiEIA"
ANDROID_HEADERS = {
    "X-Android-Package": "de.hase.haseiqapp",
    "X-Android-Cert": "B8A5D805A8986FCD77FD29E9E629EDE67FA8277D",
}
SHARE_LINK_KEY = bytes.fromhex("0c89e74a0f31d4d76184c13f04cd2970")

SIGN_UP_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
RTDB_URL = "https://hase-iq-default-rtdb.europe-west1.firebasedatabase.app"

# RTDB nodes streamed per oven: short name → path template.
NODES: Dict[str, str] = {
    "liveData": "temporaer/{oven_id}/liveData",
    "konstant": "konstant/{oven_id}",
    "konstant_app": "konstant_app/{oven_id}",
    "historienliste": "historienliste/{oven_id}",
}

OVEN_ID_RE = re.compile(r"^\d{22}$")

TOKEN_RENEW_MARGIN = 300  # renew the id token this many seconds before expiry
REQUEST_TIMEOUT = ClientTimeout(total=20)
# Firebase sends a keep-alive event every ~30 s; no data for this long = dead.
STREAM_TIMEOUT = ClientTimeout(total=None, sock_connect=20, sock_read=90)
BACKOFF_MAX = 300


class HaseCloudError(Exception):
    """Base error of the Gen 2 cloud client."""


class InvalidShareLink(HaseCloudError):
    """The share link could not be decoded into an ovenID."""


class CloudAuthError(HaseCloudError):
    """Firebase rejected the credentials or the request."""


class CloudConnectionError(HaseCloudError):
    """Firebase could not be reached or answered unexpectedly."""


# ── share link ──────────────────────────────────────────────────────────────────


def decode_share_link(text: str) -> str:
    """Return the ovenID encoded in a HASE iQ share link.

    Accepts the full link (`https://iq-applink.web.app/new?data=...`), the bare
    `data` value, or a 22-digit ovenID. The timestamp inside the link is only
    a client-side expiry and is discarded.

    Raises:
        InvalidShareLink: If no valid ovenID can be extracted.
    """
    text = text.strip()
    if OVEN_ID_RE.match(text):
        return text

    data = text
    if "data=" in text:
        query = urlparse(text).query or text.split("?", 1)[-1]
        values = parse_qs(query).get("data")
        if not values:
            raise InvalidShareLink("no data parameter")
        data = values[0].strip()

    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        decryptor = Cipher(algorithms.AES(SHARE_LINK_KEY), modes.ECB()).decryptor()
        padded = decryptor.update(raw) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plain = (unpadder.update(padded) + unpadder.finalize()).decode("ascii")
    except (binascii.Error, ValueError, UnicodeDecodeError) as err:
        raise InvalidShareLink("cannot decrypt share link") from err

    oven_id = plain.split(";", 1)[0]
    if not OVEN_ID_RE.match(oven_id):
        raise InvalidShareLink("share link does not contain an ovenID")
    return oven_id


def serial_from_oven_id(oven_id: str) -> str:
    """Return the stove serial number (the first 7 digits of the ovenID)."""
    return oven_id[:7]


# ── authentication ──────────────────────────────────────────────────────────────


class FirebaseAuth:
    """Anonymous Firebase session.

    Signs up once and afterwards renews the id token with the refresh token.
    Persist `refresh_token` (via `on_refresh_token`) to avoid creating a new
    anonymous user on every start.
    """

    def __init__(
        self,
        session: ClientSession,
        refresh_token: Optional[str] = None,
        on_refresh_token: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._session = session
        self._refresh_token = refresh_token
        self._on_refresh_token = on_refresh_token
        self._id_token: Optional[str] = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def refresh_token(self) -> Optional[str]:
        """Return the current refresh token."""
        return self._refresh_token

    @property
    def id_token(self) -> Optional[str]:
        """Return the current id token (may be expired), used for log redaction."""
        return self._id_token

    async def async_get_token(self, rejected: Optional[str] = None) -> str:
        """Return a valid id token, renewing it if needed.

        Args:
            rejected: A token the server just refused. It is renewed only if it
                is still the current one, so concurrent callers renew once.
        """
        async with self._lock:
            if (
                self._id_token is None
                or self._id_token == rejected
                or time.monotonic() > self._expires_at - TOKEN_RENEW_MARGIN
            ):
                await self._async_renew()
            assert self._id_token is not None
            return self._id_token

    async def _async_renew(self) -> None:
        """Refresh the session, falling back to a new anonymous sign-up."""
        if self._refresh_token:
            try:
                body = await self._async_post(
                    REFRESH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                )
                self._store(body["id_token"], body["refresh_token"], body["expires_in"])
                return
            except CloudAuthError as err:
                _LOGGER.info("Refresh token rejected (%s), signing up again", err)
        body = await self._async_post(SIGN_UP_URL, json={"returnSecureToken": True})
        _LOGGER.debug("Created a new anonymous Firebase session")
        self._store(body["idToken"], body["refreshToken"], body["expiresIn"])

    def _store(self, id_token: str, refresh_token: str, expires_in: Any) -> None:
        self._id_token = id_token
        self._expires_at = time.monotonic() + float(expires_in)
        if refresh_token != self._refresh_token:
            self._refresh_token = refresh_token
            if self._on_refresh_token:
                self._on_refresh_token(refresh_token)

    async def _async_post(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            async with self._session.post(
                url,
                params={"key": API_KEY},
                headers=ANDROID_HEADERS,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as resp:
                body = await resp.json(content_type=None)
                status = resp.status
        except (ClientError, asyncio.TimeoutError, ValueError) as err:
            raise CloudConnectionError(f"auth request failed: {err!r}") from err
        if status >= 500:
            raise CloudConnectionError(f"auth request failed: HTTP {status}")
        if status >= 400 or not isinstance(body, dict):
            message = ""
            if isinstance(body, dict):
                message = (body.get("error") or {}).get("message", "")
            raise CloudAuthError(f"HTTP {status} {message}".strip())
        return body


# ── RTDB tree helpers ───────────────────────────────────────────────────────────


def apply_event(tree: Any, event: str, path: str, data: Any) -> Any:
    """Apply an RTDB `put`/`patch` event to a local copy of a node.

    Returns the new tree (the given tree may be modified in place).
    """
    keys = [key for key in path.split("/") if key]
    if event == "put":
        return _set_path(tree, keys, data)
    if isinstance(data, dict):
        for child, value in data.items():
            tree = _set_path(tree, keys + [k for k in child.split("/") if k], value)
    return tree


def _set_path(tree: Any, keys: List[str], value: Any) -> Any:
    if not keys:
        return value
    if isinstance(tree, list):
        tree = {str(i): v for i, v in enumerate(tree) if v is not None}
    elif not isinstance(tree, dict):
        tree = {}
    head, rest = keys[0], keys[1:]
    child = _set_path(tree.get(head), rest, value)
    if child is None:
        tree.pop(head, None)
    else:
        tree[head] = child
    return tree if tree else None


class _SSEParser:
    """Incremental `text/event-stream` parser."""

    def __init__(self) -> None:
        self._buffer = b""
        self._event: Optional[str] = None
        self._data: List[str] = []

    def feed(self, chunk: bytes) -> List[Tuple[str, str]]:
        """Feed raw bytes, return completed `(event, data)` pairs."""
        self._buffer += chunk
        events: List[Tuple[str, str]] = []
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if not line:
                if self._event is not None or self._data:
                    events.append((self._event or "message", "\n".join(self._data)))
                self._event = None
                self._data = []
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            if field == "event":
                self._event = value
            elif field == "data":
                self._data.append(value)
        return events


class _RenewToken(Exception):
    """Internal: the stream ended because the id token must be renewed."""


# ── client ──────────────────────────────────────────────────────────────────────


class IQstoveCloud:
    """Gen 2 stove client.

    `data` holds one local tree per node in `NODES` (None until received or
    when the node is empty). `connected` tells per node whether its stream is
    currently up. Listeners are called with the node name after every change.
    """

    def __init__(
        self,
        session: ClientSession,
        oven_id: str,
        auth: FirebaseAuth,
        rtdb_url: str = RTDB_URL,
    ) -> None:
        self.oven_id = oven_id
        self.serial = serial_from_oven_id(oven_id)
        self._session = session
        self._auth = auth
        self._rtdb_url = rtdb_url.rstrip("/")

        self.data: Dict[str, Any] = {name: None for name in NODES}
        self.connected: Dict[str, bool] = {name: False for name in NODES}
        self._ready: Dict[str, asyncio.Event] = {name: asyncio.Event() for name in NODES}
        self._listeners: List[Callable[[str], None]] = []
        self._tasks: List[asyncio.Task] = []

    # ── lifecycle ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start streaming all nodes in the background."""
        if self._tasks:
            return
        for name, template in NODES.items():
            path = template.format(oven_id=self.oven_id)
            self._tasks.append(
                asyncio.create_task(
                    self._async_stream_forever(name, path), name=f"haseiq_{name}"
                )
            )

    async def async_wait_ready(self, timeout: float) -> bool:
        """Wait until every stream delivered its first snapshot.

        Returns True if all did; False on timeout (some may still be missing).
        """
        waiters = [event.wait() for event in self._ready.values()]
        try:
            await asyncio.wait_for(asyncio.gather(*waiters), timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def async_close(self) -> None:
        """Stop all streams."""
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for name in NODES:
            self.connected[name] = False

    def add_listener(self, callback: Callable[[str], None]) -> Callable[[], None]:
        """Register a change listener; returns a function that removes it."""
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    # ── REST ────────────────────────────────────────────────────────────────────

    async def async_get(self, path: str) -> Any:
        """Read a node once."""
        return await self._async_request("GET", path)

    async def async_add_keepalive(self, delta: int) -> None:
        """Change the keep-alive counter `k` by `delta` (server-side increment)."""
        await self._async_request(
            "PUT",
            f"konstant/{self.oven_id}/k",
            json={".sv": {"increment": delta}},
        )

    async def _async_request(self, method: str, path: str, **kwargs: Any) -> Any:
        rejected: Optional[str] = None
        for attempt in range(2):
            token = await self._auth.async_get_token(rejected)
            try:
                async with self._session.request(
                    method,
                    self._url(path),
                    params={"auth": token},
                    timeout=REQUEST_TIMEOUT,
                    **kwargs,
                ) as resp:
                    status = resp.status
                    body = await resp.json(content_type=None)
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                raise CloudConnectionError(self._redact(f"{method} failed: {err!r}")) from err
            if status == 401 and attempt == 0:
                rejected = token
                continue
            if status in (401, 403):
                raise CloudAuthError(f"{method} rejected: HTTP {status}")
            if status != 200:
                raise CloudConnectionError(f"{method} failed: HTTP {status}")
            return body
        raise CloudAuthError(f"{method} rejected")  # pragma: no cover

    def _url(self, path: str) -> str:
        return f"{self._rtdb_url}/{path}.json"

    def _redact(self, text: str) -> str:
        """Remove the ovenID and tokens from a message meant for the log."""
        text = text.replace(self.oven_id, f"{self.serial}…")
        for secret in (self._auth.id_token, self._auth.refresh_token):
            if secret:
                text = text.replace(secret, "<token>")
        return text

    # ── streaming ───────────────────────────────────────────────────────────────

    async def _async_stream_forever(self, name: str, path: str) -> None:
        backoff = 1
        rejected: Optional[str] = None
        while True:
            token: Optional[str] = None
            try:
                token = await self._auth.async_get_token(rejected)
                await self._async_stream(name, path, token)
            except asyncio.CancelledError:
                raise
            except _RenewToken:
                was_connected = self.connected[name]
                self._set_connected(name, False)
                immediate = was_connected or rejected is None
                rejected = token
                if immediate:
                    # Expired token: reconnect right away with a fresh one.
                    _LOGGER.debug("Stream %s: renewing token", name)
                    backoff = 1
                    continue
                _LOGGER.debug("Stream %s: token rejected after renewal", name)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Stream %s: %s", name, self._redact(repr(err)))
                rejected = token if isinstance(err, CloudAuthError) else None
                if self.connected[name]:
                    backoff = 1
                self._set_connected(name, False)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    async def _async_stream(self, name: str, path: str, token: str) -> None:
        async with self._session.get(
            self._url(path),
            params={"auth": token},
            headers={"Accept": "text/event-stream"},
            timeout=STREAM_TIMEOUT,
        ) as resp:
            if resp.status == 401:
                raise _RenewToken
            if resp.status != 200:
                raise CloudConnectionError(f"HTTP {resp.status}")
            parser = _SSEParser()
            async for chunk in resp.content.iter_any():
                for event, data in parser.feed(chunk):
                    self._handle_event(name, event, data)
        raise CloudConnectionError("stream closed by server")

    def _handle_event(self, name: str, event: str, data: str) -> None:
        if event in ("put", "patch"):
            message = json.loads(data)
            self.data[name] = apply_event(
                self.data[name], event, message.get("path", "/"), message.get("data")
            )
            self._ready[name].set()
            self.connected[name] = True
            self._notify(name)
        elif event == "auth_revoked":
            raise _RenewToken
        elif event == "cancel":
            raise CloudAuthError(f"stream cancelled: {data}")
        # "keep-alive" and unknown events are ignored

    def _set_connected(self, name: str, connected: bool) -> None:
        if self.connected[name] != connected:
            self.connected[name] = connected
            self._notify(name)

    def _notify(self, name: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(name)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener failure")
