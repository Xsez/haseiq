# Hase IQ Stove Home Assistant integration
Custom component to integrate [Hase IQ Stoves](https://www.hase.de/iq-technologie) into Home Assistant. 

This allows you to monitor various states(current phase, temperature, performance) of the stove at all times and for example create a notification, when the stove needs to be refilled.

## Installation

### Requirements

- **Home Assistant**: Version 2024.11 or higher

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

3. **Restart Home Assistant**:
   - Go to **Settings** > **System** > **Restart** and restart Home Assistant.

### Manual Installation

1. **Clone the repository**:
   - Navigate to the `custom_components` directory of your Home Assistant installation:
     ```
     /config/custom_components/
     ```
   - Clone the repository:
     ```bash
     git clone https://github.com/Xsez/haseiq haseiq
     ```

2. **Restart Home Assistant**:
   - Go to **Settings** > **System** > **Restart** and restart Home Assistant.

## Configuration

This integration uses a **Config Flow**, so no manual `configuration.yaml` changes are necessary.

1. **Add the integration**:
   - Go to **Settings** > **Devices & Services** > **Integrations**.
   - Click the **+** icon at the bottom right.
   - Search for `Hase IQ` and select it.

2. **Enter connection details**:
   - Input the stove IP address.
   - Click **Submit**.

3. **Verify connection**:
   - If successful, the stove device and sensors will be automatically added.

## Available Sensors

![Screenshot of a haseiq device with all entities](images/haseiq%20entities.png)

### General Stove Information

- **Serial Number**
- **Firmware Version**
- **Hardware Model**
- **Model Designation**

### Current State Information

- **Temperature**
- **Performance**
- **Phase**
- **Error**
- **Heatup**