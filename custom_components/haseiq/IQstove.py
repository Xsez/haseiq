import asyncio
import base64
import logging

import websockets
from websockets.exceptions import (
    ConnectionClosedError,
    InvalidHandshake,
    InvalidMessage,
    InvalidURI,
)

_LOGGER = logging.getLogger(__name__)


class IQstove:
    class Commands:
        state = [
            "appPhase",
            "appT",
            "appAufheiz",
            "appP",
            "appErr",
            "_ledBri",
        ]

        statistics = [
            "appPTx",
            "appP30Tx",
            "appPT[0;59]",
            "appP30T[0;29]",
            "appIQDarst",
        ]

        info = [
            "_oemdev",
            "_oemver",
            "_wversion",
            "_oemser",
        ]

        unknown = [
            "appNach",
        ]

        all = []
        all.extend(state)
        all.extend(statistics)
        all.extend(info)
        all.extend(unknown)

    def __init__(self, ip, port):
        self.uri = f"ws://{ip}:{port}"
        self.websocket = None
        self.values = {}
        self.listenerTask = None
        _LOGGER.debug("IQstove initialized with URI: %s", self.uri)

    @property
    def connected(self):
        """Checks if the WebSocket connection is currently open."""
        status = self.websocket is not None and self.websocket.open
        _LOGGER.debug("Checking connection status: %s", status)
        return status

    def _createB64RequestString(self, command):
        request = "_req=" + command
        encoded = base64.b64encode(request.encode("ascii")).decode("ascii") + "\r"
        _LOGGER.debug("Encoded request for '%s': %s", command, encoded.strip())
        return encoded

    def _createB64SetString(self, command, value):
        request = f"{command}={int(value)}"
        encoded = base64.b64encode(request.encode("ascii")).decode("ascii") + "\r"
        _LOGGER.debug("Encoded set for '%s': %s", command, encoded.strip())
        return encoded

    async def connect(self):
        """Establishes a connection to the WebSocket server."""
        try:
            _LOGGER.debug("Attempting to connect to stove at %s", self.uri)
            self.websocket = await websockets.connect(self.uri)
            self.listenerTask = asyncio.create_task(self.listen())
            _LOGGER.debug("Successfully connected to stove at %s", self.uri)
        except (
            ConnectionClosedError,
            InvalidURI,
            InvalidHandshake,
            InvalidMessage,
        ) as e:
            _LOGGER.error("WebSocket connection error: %s", e)
            raise IQStoveConnectionError from e
        except Exception as e:
            _LOGGER.exception("Unexpected error during connection:")
            raise UnknownException from e

    async def listen(self):
        """Listens for messages and responds to pings with pongs."""
        if self.websocket and self.websocket.open:
            try:
                _LOGGER.debug("Starting listen task.")
                await self.websocket.send(
                    self._createB64RequestString("_oemdev")
                    + self._createB64RequestString("_oemver")
                    + self._createB64RequestString("_wversion")
                    + self._createB64RequestString("_oemser")
                )
                _LOGGER.debug("Sent initial info requests.")

                while self.websocket and self.websocket.open:
                    message = await self.websocket.recv()
                    _LOGGER.debug("Received raw message: %s", message)

                    if isinstance(message, bytes) and message == b"\x89":
                        await self.websocket.pong()
                        _LOGGER.debug("Received ping, sent pong")
                    else:
                        try:
                            decoded = base64.b64decode(message).decode("ascii")
                            _LOGGER.debug("Decoded message: %s", decoded)
                            for cmd in self.Commands.all:
                                if decoded.startswith(cmd + "="):
                                    value = decoded[len(cmd) + 1 :]
                                    self.values[cmd] = value
                                    _LOGGER.debug("Updated value: %s = %s", cmd, value)
                        except Exception as decode_error:
                            _LOGGER.warning("Error decoding message: %s", decode_error)

            except websockets.ConnectionClosed:
                _LOGGER.warning("WebSocket connection closed.")
            except Exception as e:
                _LOGGER.error("Error in listen loop: %s", e)

    async def sendPeriodicRequest(self, interval):
        """Periodically sends a request to the server."""
        _LOGGER.debug("Starting periodic request loop with interval: %s", interval)
        while self.websocket and self.websocket.open:
            try:
                await self.websocket.send(
                    self._createB64RequestString("appT")
                    + self._createB64RequestString("appPhase")
                    + self._createB64RequestString("appP")
                    + self._createB64RequestString("appAufheiz")
                    + self._createB64RequestString("appErr")
                )
                _LOGGER.debug("Sent periodic request batch.")
            except Exception as e:
                _LOGGER.warning("Error sending periodic request: %s", e)
            await asyncio.sleep(interval)

    async def sendRequest(self, command):
        if self.websocket and self.websocket.open:
            try:
                await self.websocket.send(self._createB64RequestString(command))
                _LOGGER.debug("Sent request: %s", command)
            except Exception as e:
                _LOGGER.warning("Error sending request '%s': %s", command, e)

    async def sendSet(self, command, value):
        if self.websocket and self.websocket.open:
            try:
                await self.websocket.send(self._createB64SetString(command, value))
                _LOGGER.debug("Sent set command: %s = %s", command, value)
            except Exception as e:
                _LOGGER.warning("Error sending set command '%s': %s", command, e)

    def getValue(self, command):
        _LOGGER.debug("getValue called for: %s", command)
        task = asyncio.create_task(self.sendRequest(command))
        task.add_done_callback(self._handle_task_error)
        return task

    def setValue(self, command, value):
        """Set a value on the stove by sending a command and value."""
        _LOGGER.debug("setValue called for: %s = %s", command, value)
        task = asyncio.create_task(self.sendSet(command, value))
        task.add_done_callback(self._handle_task_error)
        return task

    def _handle_task_error(self, task):
        if task.exception():
            _LOGGER.error("Task failed with exception: %s", task.exception())


class IQStoveConnectionError(Exception):
    """Error to indicate we cannot connect."""


class UnknownException(Exception):
    """Error to indicate unknown exception occurred."""
