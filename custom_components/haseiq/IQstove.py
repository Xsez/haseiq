import asyncio
import base64

import websockets
from websockets.exceptions import ConnectionClosedError, InvalidHandshake, InvalidURI


class IQstove:
    class Commands:
        state = [
            "appPhase",  # current phase. enum: 0=idle 1=heating up 2=burning 3=add wood 4=dont add wood
            "appT",  # temperature in celsius
            "appAufheiz",  # heating percentage - on first heating it seems to correlate with target temperature 470c. doesnt seem to only correlate with temperature afterwards
            "appP",  # performance in percent
            "appErr",  # error state
        ]

        statistics = [
            "appPTx",  # length of availabe 1min performance history - should start at 0 on first heatup, goes to max 60
            "appP30Tx",  # length of availabe heating cycle performance - if 30 cycles are reached it should stay at 30
            "appPT[0;59]",  # performance history of last 60min
            "appP30T[0;29]",  # performance history of last 30 cycles
            "appIQDarst",  # ?intensity of iq logo during stop adding wood dialog in app?
        ]

        info = [
            "_oemdev",  # stove model - enum: 6=sila (plus)
            "_oemver",  # controller version
            "_wversion",  # wifi version
            "_oemser",  # serialnumber
            "_ledBri",  # led brightness
        ]

        unknown = [
            "appNach",  # ??? always zero?
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
        self.connected = False
        self.listenerTask = None

    def createB64RequestString(self, command):
        requestString = "_req=" + command
        requestB64Bytes = base64.b64encode(requestString.encode("ascii"))
        requestB64String = requestB64Bytes.decode("ascii") + "\r"
        return requestB64String

    async def connect(self):
        """Establishes a connection to the WebSocket server."""
        try:
            self.websocket = await websockets.connect(self.uri)
            self.listenerTask = asyncio.create_task(self.listen())
            self.connected = True
        except (ConnectionClosedError, InvalidURI, InvalidHandshake) as e:
            raise IQStoveConnectionError from e
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise UnknownException from e

        # self.listener_task = asyncio.create_task(self.listen())
        # self.connected = True
        # # print("Connected to the server.")
        # self.values["connected"] = True
        # self.values["appT"] = 123

    async def listen(self):
        """Listens for messages and responds to pings with pongs."""
        if self.websocket is not None and self.websocket.open:
            # print("Start listening for messages.")
            try:
                await self.websocket.send(
                    self.createB64RequestString("_oemdev")
                    + self.createB64RequestString("_oemver")
                    + self.createB64RequestString("_wversion")
                    + self.createB64RequestString("_oemser")
                )
                while self.websocket is not None and self.websocket.open:
                    message = await self.websocket.recv()
                    # print(f"Received message: {message}")

                    # Check if the message is a ping and respond with a pong
                    if (
                        isinstance(message, bytes) and message == b"\x89"
                    ):  # Ping opcode is 0x89
                        await self.websocket.pong()
                        print("Received ping, sent pong")
                    else:
                        # Decode and handle other messages
                        try:
                            message_b64 = base64.b64decode(message).decode("ascii")
                            for cmd in self.Commands.all:
                                if message_b64.startswith(cmd + "="):
                                    self.values[cmd] = message_b64[len(cmd) + 1 :]
                                    # print(f"Received and updated {cmd}: {self.values[cmd]}")
                        except Exception as decode_error:
                            print(f"Error decoding message: {decode_error}")

            except websockets.ConnectionClosed:
                self.connected = False
                print("Connection closed by the server.")
            except Exception as e:
                print(f"An error occurred: {e}")

    async def sendPeriodicRequest(self, interval):
        """Periodically sends a request to the server."""
        while self.websocket is not None and self.websocket.open:
            await self.websocket.send(
                self.createB64RequestString("appT")
                + self.createB64RequestString("appPhase")
                + self.createB64RequestString("appP")
                + self.createB64RequestString("appAufheiz")
                + self.createB64RequestString("appErr")
            )
            # print("Sent Periodic Request", self.values)
            await asyncio.sleep(interval)  # Send a ping every 5 seconds

    async def connectAndUpdate(self):
        """Main method to run the WebSocket client."""
        await self.connect()
        await asyncio.gather(self.listen(), self.sendPeriodicRequest())

    # drive the client connection
    async def sendRequest(self, command):
        """Send Request with provided command"""
        # open a connection to the server
        if self.websocket is not None and self.websocket.open:
            # send a message to server
            try:
                await self.websocket.send(self.createB64RequestString(command))
            except Exception as e:
                print(f"Error on send: {e}")

    def getValue(self, command):
        return asyncio.create_task(self.sendRequest(command))


class IQStoveConnectionError(Exception):
    """Error to indicate we cannot connect."""


class UnknownException(Exception):
    """Error to indicate we cannot connect."""