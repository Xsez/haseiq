# Hase IQ Stove Home Assistant integration
Custom component to integrate [Hase IQ Stoves](https://www.hase.de/iq-technologie) into Home Assistant. 

This allows you to monitor various states (current phase, temperature, performance) of the stove at all times and for example create a notification when the stove needs to be refilled.

Two controller generations are supported:

- **Gen 1** – connected directly over your local network.
- **Gen 2** – HASE iQ controllers from November 2024 on (e.g. LIMA iQ). These have no local interface and are read through the HASE cloud, the same way the HASE iQ app does it. **Gen 2 support is in beta.**

## Installation

### Requirements

- **Home Assistant**: Version 2025.3 or higher

### HACS Installation

1. **Install HACS** (if not already installed):
   - Follow the official [HACS installation guide](https://hacs.xyz/docs/installation/prerequisite).

2. **Add the custom repository**:
   - Go to **HACS** in the Home Assistant interface.
   - Add a Custom Repository with the following url
repository URL:
     ```
     https://github.com/Xsez/haseiq
     ```
   - Select type **Integration**
   - Click **Add**.
   - Search for **Hase IQ** 
   - **install**
   - To try a beta version, enable **Show beta versions** for the repository in HACS.

3. **Restart Home Assistant**:
   - Go to **Settings** > **System** > **Restart** and restart Home Assistant.

### Manual Installation

1. **Copy the integration**:
   - Download this repository and copy the folder `custom_components/haseiq` into the `custom_components` directory of your Home Assistant installation, so you end up with:
     ```
     /config/custom_components/haseiq/
     ```

2. **Restart Home Assistant**:
   - Go to **Settings** > **System** > **Restart** and restart Home Assistant.

## Configuration

This integration uses a **Config Flow**, so no manual `configuration.yaml` changes are necessary.

1. **Add the integration**:
   - Go to **Settings** > **Devices & Services** > **Integrations**.
   - Click the **+** icon at the bottom right.
   - Search for `Hase IQ` and select it.

2. **Choose your stove generation**:
   - **Gen 1**: enter the IP address or hostname of the stove. Gen 1 stoves are also discovered automatically on your network.
   - **Gen 2**: in the HASE iQ app open your stove and use **"Ofen teilen" (share stove)**. The app shows a QR code that contains the share link. Scan it with your phone camera, or decode a screenshot with a QR decoder such as [this one](https://www.w3schools.com/tools/tool_qr_decoder.php), and paste the link (`https://iq-applink.web.app/new?data=…`). Treat this link like a key – anyone who has it can read your stove's data.

3. **Verify connection**:
   - If successful, the stove device and sensors will be automatically added.

The host (Gen 1) or share link (Gen 2) can be changed later with **Reconfigure** on the integration entry.

## Available Sensors

![Screenshot of a haseiq device with all entities](images/haseiq%20entities.png)

### Gen 1

- **Temperature**
- **Performance**
- **Phase** – off, heating up, burning, add wood, don't add wood
- **Error**
- **Heating up**
- **LED brightness** (adjustable)

Device information: serial number, firmware version, hardware model, model designation.

For Gen 2 the model name (e.g. "LIMA iQ") and a link to the technical-data sheet are looked up from the HASE cloud and shown on the device page.

### Gen 2 (beta)

- **Temperature**, **Load average temperature** (mean temperature since the last load of wood), **Controller temperature**
- **Phase** – off, kindling, burning, add wood, heating up, residual heat, don't add wood, error
- **ECO value** (the stove's 0–100 combustion-quality score) and **ECO rating** (ECO / ECO+ / ECO optimal, like the app's badge)
- **Error** – on when the stove reports a fault; the active faults (motor, temperature sensor, battery) are listed in its attributes
- **Window air**, **Grate air**, **Rear wall air** (%) – the three air flaps, matching the app. The stove sends a combined window/grate flap value (`PL`) plus the rear flap (`SL`); the split point is looked up per stove model, so window and grate are derived like the app does.
- **Refuel urgency** (0 while no wood is needed, then counts up the longer the stove waits for wood)
- **Signal LED brightness**, **Switch LED brightness** (adjustable; written to the HASE cloud like the app does)
- **Extra air** (button) – triggers the stove's air booster, like the app's "Extra air". The integration turns it off again after 5 minutes as a safety net; the stove normally ends it on its own.
- For the current or last firing: **Last firing start**, **duration**, **peak temperature**, **average temperature** and **wood loads**
- **Firings** – the number of firings the HASE cloud keeps
- **App notification** – an event each time the stove has the HASE iQ app notified (so far: when wood should be added)
- **Online** – off when the stove has not reported for 3 minutes; **Last connection**; **IP address** (informative only); the firmware version is shown on the device page
- **Firmware update** – on while an update waits to be installed, with the download progress as attribute
- **Last log entry** – the newest line of the stove's own log (restarts, firmware updates); the latest 20 lines are in its attributes
- Every other value the cloud delivers is added as a raw sensor (`Live …`, `Konstant …`, `App …`) to help work out what it means.

Field meanings for Gen 2 are still provisional.

## Diagnostics

**Download diagnostics** on the integration entry gives a dump of all values the stove reports, with the host, share-link data and cloud tokens removed. For Gen 2 stoves it also contains the stove's full error-code log (`error_log`), which can be a few MB. Please attach it when reporting an issue.

## Upgrading from 0.3

- The **Phase** sensor now reports translated states. Its internal values changed (e.g. `heating up` → `heating_up`, `don't add wood` → `dont_add_wood`, `idle` → `off`). Update automations or dashboards that compare the phase text.
- Entity IDs, history and customizations are kept. Internally the entities get new unique IDs based on the stove serial number, so several stoves can be added. Downgrading to 0.3 afterwards will create duplicate entities.
