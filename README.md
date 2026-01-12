# Local BGH Smart Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

A **local** Home Assistant integration for controlling BGH Smart HVAC units with HPA4911 Smart Control Kit. This integration communicates directly with your devices on your local network without requiring cloud connectivity.

## Features

- **Local Control**: Direct communication with your BGH Smart devices via UDP protocol
- **Subscription-based Updates**: Real-time status updates using device subscriptions (2-minute intervals)
- **Full Climate Control**: Temperature, HVAC modes, fan speeds, and swing control
- **Device Sensors**: Firmware version and IR module battery level monitoring
- **Shared Coordinator**: Efficient single UDP client handling multiple devices
- **Config Flow**: Easy setup through Home Assistant UI

### Supported HVAC Features

- **HVAC Modes**: Off, Cool, Heat, Dry, Fan Only, Auto
- **Fan Modes**: Low, Medium, High, Auto
- **Swing Control**: Horizontal swing on/off
- **Temperature Control**: 16°C - 30°C range with 1°C steps
- **Current Temperature**: Real-time temperature readings
- **HVAC Actions**: Displays current activity (Cooling, Heating, Drying, Fan, Idle, Off)

### Additional Sensors

- **Firmware Version**: Device firmware information
- **IR Battery Level**: Battery percentage of the IR module

## Requirements

- BGH Smart HVAC unit with HPA4911 Smart Control Kit
- Home Assistant 2023.1 or later
- Local network connectivity to your BGH Smart devices

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the **⋮** menu in the top right corner
4. Select **Custom repositories**
5. Add this repository URL: `https://github.com/arpena/hpa4911`
6. Select **Integration** as the category
7. Click **Add**
8. Search for "Local BGH Smart" in HACS
9. Click **Download** and restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/arpena/hpa4911/releases)
2. Extract the `custom_components/hpa4911` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

This integration uses **Config Flow** for easy setup through the Home Assistant UI.

### Setup Steps

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Local BGH Smart"
4. Enter the required information:
   - **Name**: A friendly name for your device
   - **MAC Address**: The MAC address of your BGH Smart device (required)
   - **IP Address**: The IP address of your device (required for communication)

### Finding Your Device Information

To find your device's MAC address and IP:

1. Check your router's connected devices list
2. Look for devices with "BGH" or similar manufacturer names
3. The MAC address format should be like: `AA:BB:CC:DD:EE:FF`
4. Note the current IP address assigned to the device
5. You can also use network scanning tools to discover devices on your network

**Important**: Both MAC address and IP address are now required fields for proper device communication.

## Usage

Once configured, your BGH Smart device will appear as a climate entity in Home Assistant with the following controls:

### Climate Entity
- **Temperature Control**: Set target temperature (16°C - 30°C)
- **Mode Selection**: Choose between Off, Cool, Heat, Dry, Fan Only, and Auto
- **Fan Speed**: Select Low, Medium, High, or Auto fan speeds
- **Swing Control**: Toggle horizontal swing on/off
- **Current Status**: View current temperature and HVAC action

### Additional Sensors
- **Firmware Version**: Monitor device firmware information
- **IR Battery Level**: Track the battery percentage of the IR module

## Technical Details

- **Communication Protocol**: UDP-based local protocol with device subscriptions
- **Update Method**: Subscription-based updates (devices maintain subscriptions for 2 minutes)
- **Device Type**: Climate entity with diagnostic sensors
- **IoT Class**: Local Polling
- **Shared Resources**: Single UDP client handles multiple devices efficiently

## Troubleshooting

### Device Not Responding

- Ensure your BGH Smart device is connected to the same network as Home Assistant
- Verify both the MAC address and IP address are correct
- Check if the IP address is still valid (devices may get new IPs from DHCP)
- Ensure your network allows UDP communication between Home Assistant and the device

### Status Updates Not Working

- The integration uses subscription-based updates (2-minute subscription intervals)
- Check Home Assistant logs for any error messages
- Verify UDP communication is not blocked by firewall rules
- Try restarting the integration if subscriptions seem stuck

### Multiple Devices

- The integration uses a shared coordinator for efficient communication
- All devices share a single UDP client to minimize network overhead
- Each device maintains its own subscription with the coordinator

### Logs

Enable debug logging by adding this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.hpa4911: debug
```

## Technical Details

- **Communication Protocol**: UDP-based local protocol with device subscriptions
- **Update Method**: Subscription-based updates (devices maintain subscriptions for 2 minutes)
- **Device Type**: Climate entity with diagnostic sensors
- **IoT Class**: Local Polling
- **Shared Resources**: Single UDP client handles multiple devices efficiently

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests on the [GitHub repository](https://github.com/arpena/hpa4911).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This integration is not officially supported by BGH. Use at your own risk.
