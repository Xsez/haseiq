# Hase IQ Stove Home Assistant integration
Custom component to integrate Hase IQ Stoves into Home Assistant. This allows you to monitor the current temperature, phase and more.

## Installation

### Requirements

- **Home Assistant**: Version 2024.11 or higher

### HACS Installation

1. **Install HACS** (if not already installed):
   - Follow the official [HACS installation guide](https://hacs.xyz/docs/installation/prerequisite).

2. **Add the custom repository**:
   - Go to **HACS** in the Home Assistant interface.
   - Click on **Integrations** and then the **+** icon at the bottom right.
   - Search for `Xiaomi 5G CPE CB0401V2` or directly add the repository URL:
     ```
     https://github.com/Xsez/haseiq
     ```
   - Click **Add**.

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

2. **Enter credentials**:
   - Input the stove IP address.
   - Click **Submit**.

3. **Verify connection**:
   - If successful, the stove device and sensors will be automatically added.

## Available Sensors

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