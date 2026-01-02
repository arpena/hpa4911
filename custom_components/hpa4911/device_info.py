#!/usr/bin/env python3
"""
Home Assistant HPA4911 Device Info Enhancement
Adds firmware version and IR battery info to HA integration
"""

import socket
import struct
import json
from typing import Dict, Optional

class HPA4911DeviceInfo:
    def __init__(self):
        self.devices = {}
        
    def parse_device_info_payload(self, data: bytes) -> Optional[Dict]:
        """Parse device info payload (message type 0x03)"""
        if len(data) < 20 or data[14] != 0x03:
            return None
            
        # Extract MAC address
        mac = ':'.join(f'{b:02x}' for b in data[1:7])
        
        # Extract firmware info string
        payload_start = 18  # Skip header
        firmware_info = data[payload_start:].decode('ascii', errors='ignore')
        
        # Parse: "HPA-4911,1.0.0.17,HPA-4911-BLE,1.0.0.4"
        parts = firmware_info.split(',')
        if len(parts) >= 4:
            device_info = {
                'mac': mac,
                'device_model': parts[0],
                'main_firmware': parts[1],
                'ble_module': parts[2],
                'ble_firmware': parts[3]
            }
            
            # Store the device info
            if mac not in self.devices:
                self.devices[mac] = {}
            self.devices[mac].update(device_info)
            
            return device_info
        return None
    
    def parse_status_payload(self, data: bytes) -> Optional[Dict]:
        """Parse status payload (message type 0x08) for battery info"""
        if len(data) < 20 or data[14] != 0x08:
            return None
            
        mac = ':'.join(f'{b:02x}' for b in data[1:7])
        
        # Status bytes start at offset 18
        status_data = data[18:]
        if len(status_data) >= 9:
            # Byte 6-7 often contain battery level (0x00-0xFF scale)
            battery_raw = status_data[6] if len(status_data) > 6 else 0
            battery_percent = min(100, int((battery_raw / 255.0) * 100))
            
            status_info = {
                'mac': mac,
                'ir_battery_level': battery_percent,
                'ir_battery_raw': battery_raw
            }
            
            # Store the status info
            if mac not in self.devices:
                self.devices[mac] = {}
            self.devices[mac].update(status_info)
            
            return status_info
        return None
    
    def get_device_info(self, mac: str) -> Dict:
        """Get complete device info for Home Assistant"""
        # Return stored info if available, otherwise return known firmware versions
        stored_info = self.devices.get(mac, {})
        
        # If we don't have firmware info from packets, use known values from network analysis
        if 'main_firmware' not in stored_info:
            stored_info.update({
                'device_model': 'HPA-4911',
                'main_firmware': '1.0.0.17',
                'ble_module': 'HPA-4911-BLE', 
                'ble_firmware': '1.0.0.4'
            })
        
        return stored_info

    def get_device_name(self, mac: str) -> str:
        """Get device friendly name"""
        return self.devices.get(mac, {}).get('name', f"HPA-4911_{mac.replace(':', '')}")

    def set_device_info(self, mac: str, name: str, ip_address: str):
        """Set device friendly name and ip address"""
        if mac not in self.devices:
            self.devices[mac] = {}
        self.devices[mac]['name'] = name
        self.devices[mac]['ip_address'] = ip_address
    
    def get_all_devices(self) -> Dict:
        """Get all discovered devices"""
        return self.devices
