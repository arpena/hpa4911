# Local BGH Smart Integration

A local Home Assistant integration for controlling BGH Smart HVAC units with HPA4911 Smart Control Kit.

## Key Features

- **Local Control**: Direct UDP communication with your BGH Smart devices
- **No Cloud Required**: Works entirely on your local network
- **Real-time Updates**: Automatic status polling every 30 seconds
- **Full Climate Control**: Temperature, modes, fan speeds, and swing control
- **Easy Setup**: Config Flow integration for simple configuration

## Installation

Install via HACS by adding this repository as a custom integration, or manually copy the files to your `custom_components/hpa4911` directory.

## Configuration

Use the Home Assistant UI to add the integration:
1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Local BGH Smart"
4. Enter your device's name, MAC address, and optionally IP address

## Requirements

- BGH Smart HVAC with HPA4911 Smart Control Kit
- Home Assistant 2025.12.1+
- Local network connectivity

For detailed setup instructions, troubleshooting, and technical information, see the [full README](https://github.com/arpena/hpa4911/blob/main/README.md).