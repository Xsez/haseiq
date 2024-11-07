import asyncio
import websockets
import base64


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

    def createB64RequestString(self, command):
        requestString = "_req=" + command
        requestB64Bytes = base64.b64encode(requestString.encode("ascii"))
        requestB64String = requestB64Bytes.decode("ascii") + "\r"
        return requestB64String

    async def connect(self):
        """Establishes a connection to the WebSocket server."""
        self.websocket = await websockets.connect(self.uri)
        self.listener_task = asyncio.create_task(self.listen())
        self.connected = True
        # print("Connected to the server.")
        self.values["connected"] = True
        self.values["appT"] = 123

    async def listen(self):
        if self.websocket is not None and self.websocket.open:
            """Listens for messages and responds to pings with pongs."""
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

    async def sendPeriodicRequest(self):
        """Periodically sends a ping to the server."""
        while self.websocket is not None and self.websocket.open:
            await self.websocket.send(
                self.createB64RequestString("appT")
                + self.createB64RequestString("appPhase")
                + self.createB64RequestString("appP")
                + self.createB64RequestString("appAufheiz")
                + self.createB64RequestString("appErr")
            )
            # print("Sent Periodic Request", self.values)
            await asyncio.sleep(5)  # Send a ping every 5 seconds

    async def connectAndUpdate(self):
        """Main method to run the WebSocket client."""
        await self.connect()
        await asyncio.gather(self.listen(), self.sendPeriodicRequest())

    # drive the client connection
    async def sendRequest(self, command):
        # open a connection to the server
        if self.websocket is not None and self.websocket.open:
            # send a message to server
            try:
                await self.websocket.send(self.createB64RequestString(command))
            except Exception as e:
                print(f"Error on send: {e}")

            # # read message from server
            # try:
            #     message = await self.websocket.recv()
            #     messageb64 = base64.b64decode(message).decode("ascii")
            #     # report result
            #     # print(f"Received: {messageb64}")
            #     for command in self.Commands.all:
            #         if messageb64.find(command + "=") >= 0:
            #             self.values[command] = messageb64.removeprefix(command + "=")
            #             return self.values[command]
            # except Exception as e:
            #     print(f"Error on receive: {e}")

        # print('Disconnected')

    def getValue(self, command):
        return asyncio.create_task(self.sendRequest(command))


# # Example usage
# async def main():
#     stove = IQStove("192.168.1.158", 8080)  # Replace with your server's IP and port
#     await stove.connectAndUpdate()

# # Run the main function in an event loop
# if __name__ == "__main__":
#     asyncio.run(main())


# """Communication class for Hase iQ stoves."""

# import asyncio
# import base64

# import websockets


# class IQstove:
#     class Commands:
#         state = [
#             "appPhase",  # current phase. enum: 0=idle 1=heating up 2=burning 3=add wood 4=dont add wood
#             "appT",  # temperature in celsius
#             "appAufheiz",  # heating percentage - on first heating it seems to correlate with target temperature 470c. doesnt seem to only correlate with temperature afterwards
#             "appP",  # performance in percent
#             "appErr",  # error state
#         ]

#         statistics = [
#             "appPTx",  # length of availabe 1min performance history - should start at 0 on first heatup, goes to max 60
#             "appP30Tx",  # length of availabe heating cycle performance - if 30 cycles are reached it should stay at 30
#             "appPT[0;59]",  # performance history of last 60min
#             "appP30T[0;29]",  # performance history of last 30 cycles
#             "appIQDarst",  # ?intensity of iq logo during stop adding wood dialog in app?
#         ]

#         info = [
#             "_oemdev",  # stove model - enum: 6=sila (plus)
#             "_oemver",  # controller version
#             "_wversion",  # wifi version
#             "_oemser",  # serialnumber
#             "_ledBri",  # led brightness
#         ]

#         unknown = [
#             "appNach",  # ??? always zero?
#         ]

#         all = []
#         all.extend(state)
#         all.extend(statistics)
#         all.extend(info)
#         all.extend(unknown)

#     def __init__(self, ip):
#         self.values = {}
#         self.ip = ip
#         self.websocket = None
#         self.model = None
#         self.serial = None
#         self.controllerVersion = None
#         self.wifiVersion = None
#         self.listener_task = None
#         self.request_queue = asyncio.Queue()

#     async def initialize(self):
#         """Asynchronously fetch values during initialization."""
#         self.serial = await self.getValue("_oemser")
#         self.controllerVersion = await self.getValue("_oemver")
#         self.wifiVersion = await self.getValue("_wversion")

#     async def connect(self):
#         """Establish the WebSocket connection if not connected."""
#         if not self.websocket or self.websocket.closed:
#             try:
#                 self.websocket = await websockets.connect(f"ws://{self.ip}:8080")
#                 print("Connected to the stove.")

#                 # Start the ping handler to keep the connection alive
#                 self.listener_task = asyncio.create_task(self._listen())
#             except Exception as e:
#                 print(f"Failed to connect: {e}")
#                 self.websocket = None

#     async def disconnect(self):
#         """Close the WebSocket connection if it is open."""
#         if self.websocket and not self.websocket.closed:
#             await self.websocket.close()
#             print("Disconnected from the stove.")
#             self.websocket = None

#         # Cancel the listener task if it is running
#         if self.listener_task:
#             self.listener_task.cancel()
#             try:
#                 await self.listener_task
#             except asyncio.CancelledError:
#                 pass
#             self.listener_task = None

#     def is_connected(self):
#         """Check if the WebSocket connection is active."""
#         return self.websocket and not self.websocket.closed

#     async def _listen(self):
#         """Listen for incoming messages and handle requests from the queue."""
#         try:
#             while self.is_connected():
#                 # Send any command from the queue
#                 if not self.request_queue.empty():
#                     command = await self.request_queue.get()
#                     await self.websocket.send(command)

#                 # Wait for the next message (ping, pong, or response)
#                 message = await self.websocket.recv()

#                 # Handle pings automatically
#                 if (
#                     isinstance(message, bytes) and message == b"\x89"
#                 ):  # Ping opcode is 0x89
#                     await self.websocket.pong()
#                     print("Received ping, sent pong")
#                     continue

#                 # Decode and process each message received
#                 message_b64 = base64.b64decode(message).decode("ascii")
#                 for cmd in self.Commands.all:
#                     if message_b64.startswith(cmd + "="):
#                         self.values[cmd] = message_b64[len(cmd) + 1 :]
#                         print(f"Received and updated {cmd}: {self.values[cmd]}")
#         except websockets.ConnectionClosed:
#             print("Connection closed by the server.")
#         except Exception as e:
#             print(f"Listener error: {e}")

#     def createB64RequestString(self, command):
#         requestString = "_req=" + command
#         requestB64Bytes = base64.b64encode(requestString.encode("ascii"))
#         requestB64String = requestB64Bytes.decode("ascii") + "\r"
#         return requestB64String

#     def createB64SetString(self, command, value):
#         setString = command + "=" + value
#         setB64Bytes = base64.b64encode(setString.encode("ascii"))
#         setB64String = setB64Bytes.decode("ascii") + "\r"
#         return setB64String

#     # def tryConnect(self) -> bool:
#     #     ws = websockets.connect(f"ws://{self.ip}:8080")
#     #     # print('Connected to server')

#     #     # send a message to server
#     #     try:
#     #         ws.send(self.createB64CommandString("_oemser"))
#     #     except Exception as e:
#     #         print(f"Error on send: {e}")

#     #     # read message from server
#     #     try:
#     #         message = ws.recv()
#     #         messageb64 = base64.b64decode(message).decode("ascii")
#     #         # report result
#     #         # print(f"Received: {messageb64}")
#     #         for command in self.Commands.all:
#     #             if messageb64.find(command + "=") >= 0:
#     #                 return True
#     #     except Exception as e:
#     #         print(f"Error on receive: {e}")

#     # drive the client connection
#     # async def sendRequest(self, command):
#     #     await self.connect()  # Ensure connection is open
#     #     if self.is_connected():
#     #         try:
#     #             await self.websocket.send(self.createB64RequestString(command))
#     #         except Exception as e:
#     #             print(f"Error on send: {e}")

#     #         # read message from server
#     #         try:
#     #             message = await self.websocket.recv()
#     #             messageb64 = base64.b64decode(message).decode("ascii")
#     #             # report result
#     #             # print(f"Received: {messageb64}")
#     #             for command in self.Commands.all:
#     #                 if messageb64.find(command + "=") >= 0:
#     #                     self.values[command] = messageb64.removeprefix(command + "=")

#     #                     return self.values[command]
#     #         except Exception as e:
#     #             print(f"Error on receive: {e}")
#     async def sendRequest(self, command):
#         """Queue a request command to be sent."""
#         await self.connect()  # Ensure connection is open
#         if self.is_connected():
#             await self.request_queue.put(self.createB64RequestString(command))

#     async def sendSet(self, command, value):
#         # open a connection to the server
#         async with websockets.connect(f"ws://{self.ip}:8080") as websocket:
#             # print('Connected to server')

#             # send a message to server
#             try:
#                 await websocket.send(self.createB64SetString(command, value))
#             except Exception as e:
#                 print(f"Error on send: {e}")

#             # read message from server
#             try:
#                 message = await websocket.recv()
#                 messageb64 = base64.b64decode(message).decode("ascii")
#                 # report result
#                 # print(f"Received: {messageb64}")
#                 for command in self.Commands.all:
#                     if messageb64.find(command + "=") >= 0:
#                         self.values[command] = messageb64.removeprefix(command + "=")

#                         return self.values[command]
#             except Exception as e:
#                 print(f"Error on receive: {e}")
#         # print('Disconnected')

#     async def getValue(self, command):
#         """Asynchronous method to fetch a value from the stove."""
#         if not self.is_connected():
#             await self.connect()
#             return self.values.get(command)

#     def setValue(self, command, value):
#         asyncio.run(self.sendSet(command, value))

#     @property
#     def temperature(self):
#         return self.getValue("appT")

#     @property
#     def performance(self):
#         return self.getValue("appP")

#     @property
#     def phase(self):
#         return self.getValue("appPhase")

#     @property
#     def heatingPercentage(self):
#         return self.getValue("appAufheiz")

#     @property
#     def error(self):
#         return self.getValue("appErr")
