# Hase-iQ
Example communication to a Hase iQ Stove. https://www.hase.de/iq-technologie

## Sample Program
Python program ofen.py connects to the oven and request all known commands in different intervals. Displays all kown values to the console.
Example Output


> 2024-10-07 00:29:03.033109 {'appPhase': '4', 'appT': '36.2', 'appAufheiz': '0.0', 'appP': '69', 'appNach': '0', 'appErr': '0', 'appPTx': '60', 'appP30Tx': '30', 'appPT[0;59]': '96;98;100;100;100;100;100;100;100;100;100;100;100;100;100;100;100;96;85;72;57;50;53;65;64;63;63;63;63;63;64;64;64;64;64;65;65;65;65;66;66;66;66;66;66;67;67;67;67;67;68;68;68;68;68;68;69;69;69;69', 'appP30T[0;29]': '56;50;63;61;60;58;58;55;73;67;64;64;61;75;61;63;54;62;60;60;58;76;56;54;68;65;63;44;71;76', '_oemdev': '6', '_oemver': 'AAF_6177=13', '_wversion': '1.4', '_oemser': '7057373', 'appIQDarst': '3', '_ledBri': '100'}

## Communication
Communication is unencrypted websocket text. Text payload is ascii encoded base64.

Client sends a request for a command by sending "_req={cmd_name}". Server (the stove) sends back "{cmd_name}={value}". Example: Send "_req=appT" and you receive "appT=511.3".  See example down below for more details.

## Known Commands

commandsCurrentState

            "appPhase",         #current phase. enum: 0=idle 1=heating up 2=burning 3=add wood 4=dont add wood 
            "appT",             #temperature in celsius
            "appAufheiz",       #heating percentage - on first heating it seems to correlate with target temperature 475c. doesnt seem to only correlate with temperature afterwards
            "appP",             #performance in percent
            "appNach",          #??? always zero?
            "appErr",           #error state
                 

commandsStatistics

            "appPTx",           #length of availabe 1min performance history - should start at 0 on first heatup, goes to max 60
            "appP30Tx",         #length of availabe heating cycle performance - if 30 cycles are reached it should stay at 30
            "appPT[0;59]",      #performance history of last 60min
            "appP30T[0;29]",    #performance history of last 30 cycles
            "appIQDarst",       #?intensity of iq logo during stop adding wood dialog in app?
            

commandsInfo

            "_oemdev",          #stove model - enum: 6=sila (plus)
            "_oemver",          #controller version
            "_wversion",        #wifi version
            "_oemser",          #serialnumber
            "_ledBri",          #led brightness
             

### Example
Want to request current Phase by using command `appPhase`

Request should look like this: "_req=appPhase"

Encode this string in base64 ascii: "X3JlcT1hcHBQaGFzZQ=="

Add a ascii carriage return at the end: "X3JlcT1hcHBQaGFzZQ==\r"

Websocket raw text payload to send: "X3JlcT1hcHBQaGFzZQ==\r"
    
Answer from stove as payload text: "YXBwUGhhc2U9NA==\r"

Decoded from base64 ascii: "appPhase=4"
