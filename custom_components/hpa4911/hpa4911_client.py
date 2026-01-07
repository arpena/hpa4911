#!/usr/bin/env python3
"""
Async HPA4911 UDP Client
"""

import asyncio
import struct
from typing import Optional, Callable
from dataclasses import dataclass

@dataclass
class HVACStatus:
    mode: int  # 1=Cool, 2=Heat, 3=Dry, 4=Fan, 254=Auto
    fan_mode: int
    flags: int
    measured_temp: float  # Current room temperature
    desired_temp: float   # Target temperature
    timer_on_minutes: int
    timer_off_minutes: int

@dataclass
class DeviceStatus:
    rssi: Optional[int] = None
    battery_level: Optional[int] = None
    ir_mac_address: Optional[str] = None
    firmware: Optional[str] = None
    firmware_info: Optional[str] = None

@dataclass
class DeviceResponse:
    command_id: int
    payload: bytes = b''
    hvac_status: Optional[HVACStatus] = None
    device_status: Optional[DeviceStatus] = None

class HPA4911AsyncClient:
    """Async UDP client for HPA4911 devices"""
    
    PORT_SERVER = 20911
    PORT_CLIENT = 20910
    BROADCAST_IP = "255.255.255.255"
    
    def __init__(self):
        self.transport = None
        self.protocol = None
        self.sequence = 0
        self._status_callback: Optional[Callable] = None
        self._device_info_callback: Optional[Callable] = None
        
        # Set up logger
        import logging
        self._logger = logging.getLogger(__name__)
    
    def set_climate_callback(self, callback: Callable):
        """Set callback for status updates"""
        self._climate_callback = callback
        
    def set_sensor_callback(self, callback: Callable):
        """Set callback for device info updates"""
        self._sensor_callback = callback
    
    async def connect(self):
        """Connect using asyncio UDP"""
        # We need to bind to server port, if not the integration will not receive all updates
        loop = asyncio.get_event_loop()
        try:
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: UDPProtocol(self._handle_response),
                local_addr=('0.0.0.0', self.PORT_SERVER),
                allow_broadcast=True
            )
            self._logger.info(f"UDP client connected on port {self.PORT_SERVER}")
        except OSError as e:
            self._logger.error(f"Failed to bind to port {self.PORT_SERVER}")
            raise

    def _handle_response(self, response: DeviceResponse, addr: str):
        """Handle decoded response"""
        if response.hvac_status and self._climate_callback:
            self._climate_callback(response.hvac_status, addr)
        elif response.device_status and self._sensor_callback:
            self._sensor_callback(response.device_status, addr)
    
    def _create_header(self, dest_mac: bytes, cmd_id: int, src_endpoint: int = 0, dest_endpoint: int = 0) -> bytes:
        """Create 17-byte UDP packet header"""
        header = bytearray(17)
        header[0] = 0  # Protocol version
        header[1:7] = b'\x00\x00\x00\x00\x00\x00'  # Source MAC
        header[7:13] = dest_mac  # Destination MAC
        header[13] = self.sequence  # Sequence number
        header[14] = src_endpoint  # Source endpoint
        header[15] = dest_endpoint  # Destination endpoint
        header[16] = cmd_id  # Command ID
        # add 1 to sequence number for next packet
        self.sequence = (self.sequence + 1) % 256
        return bytes(header)
    
    async def subscribe_hvac_status(self, device_mac: str, device_ip: str = None):
        """Request HVAC status from device"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        target_ip = device_ip or self.BROADCAST_IP
        
        # Step 1: Send JOIN command Subscribe
        join_header = self._create_header(mac_bytes, 161)  # CMD_JOIN
        join_data = bytes([12])  # JOIN subcommand 12 subscribe
        join_packet = join_header + join_data
        self.transport.sendto(join_packet, (target_ip, self.PORT_CLIENT))
        
        # Step 2: Poll HVAC endpoint for status
        broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
        poll_header = self._create_header(broadcast_mac, 228, dest_endpoint=1)  # CMD_POLL to endpoint 1
        self.transport.sendto(poll_header, (target_ip, self.PORT_CLIENT))

    async def trigger_hvac_status(self, device_mac: str, device_ip: str = None):
        """Trigger immediate HVAC status update (alias for subscribe_hvac_status)"""
        await self.subscribe_hvac_status(device_mac, device_ip)

    async def request_device_info(self, device_ip: str = None):
        """Send Join Enumerate request to get device firmware info"""
        if not self.transport:
            await self.connect()
        
        broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
        target_ip = device_ip or self.BROADCAST_IP
        
        # Step 1: Send JOIN command Enumerate All
        join_header = self._create_header(broadcast_mac, 161)  # CMD_JOIN
        join_data = bytes([4])  # JOIN subcommand enumerate all
        join_packet = join_header + join_data
        self.transport.sendto(join_packet, (target_ip, self.PORT_CLIENT))

        # Step 2: Poll HVAC endpoint for status
        poll_header = self._create_header(broadcast_mac, 228, dest_endpoint=1)  # CMD_POLL to endpoint 1
        self.transport.sendto(poll_header, (target_ip, self.PORT_CLIENT))
    
    async def request_battery_status(self, device_mac: str, device_ip: str = None):
        """Request HPA4911 battery and signal status"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        target_ip = device_ip or self.BROADCAST_IP
        
        # Step 1: Send CUSTOM command STATUS REQUEST
        header = self._create_header(mac_bytes, 162)  # CMD_CUSTOM
        packet = header + bytes([92])  # CUSTOM_STATUS_REQUEST
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
        
        # Step 2: Poll HVAC endpoint for status
        broadcast_mac = b'\xff\xff\xff\xff\xff\xff'
        poll_header = self._create_header(broadcast_mac, 228, dest_endpoint=1)  # CMD_POLL to endpoint 1
        self.transport.sendto(poll_header, (target_ip, self.PORT_CLIENT))
    
    async def set_hvac_mode(self, device_mac: str, mode: int, device_ip: str = None):
        """Set HVAC mode (1=Cool, 2=Heat, 3=Dry, 4=Fan, 254=Auto)"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 97, dest_endpoint=1)  # CMD_HVAC_SET_MODE
        packet = header + bytes([mode])
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_hvac_full(self, device_mac: str, mode: int, fan_mode: int, flags: int, temperature: float, device_ip: str = None):
        """Set HVAC mode, fan, and temperature in one command (like original app)"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 97, dest_endpoint=1)  # CMD_HVAC_SET_MODE
        
        # Convert temperature to 16-bit little endian (temp * 100)
        temp_raw = int(temperature * 100)
        temp_bytes = struct.pack('<h', temp_raw)
        
        # Create 5-byte payload: mode, fan_mode, flags, temp_low, temp_high
        payload = bytes([mode, fan_mode, flags]) + temp_bytes
        packet = header + payload
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_target_temperature(self, device_mac: str, temperature: int, device_ip: str = None):
        """Set target temperature (16-30°C typically)"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 98, dest_endpoint=1)  # CMD_HVAC_COMMAND
        packet = header + bytes([temperature, 0])  # temp, fan_speed=0
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_hvac_with_swing(self, device_mac: str, mode: int, fan_mode: int, temperature: float, 
                                 horizontal_swing: bool = False, vertical_swing: bool = False, device_ip: str = None):
        """Set HVAC mode, fan, temperature and swing in one command (HPA4911 method)"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 97, dest_endpoint=1)  # CMD_HVAC_SET_MODE
        
        # Convert temperature to 16-bit little endian (temp * 100)
        temp_raw = int(temperature * 100)
        temp_bytes = struct.pack('<h', temp_raw)
        
        # Set swing flags
        flags = 0
        if horizontal_swing:
            flags |= 16  # HVAC_FLAG_SWING_HORIZONTAL
        if vertical_swing:
            flags |= 32  # HVAC_FLAG_SWING_VERTICAL
        
        # Create 5-byte payload: mode, fan_mode, flags, temp_low, temp_high
        payload = bytes([mode, fan_mode, flags]) + temp_bytes
        packet = header + payload
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_hvac_swing_off(self, device_mac: str, mode: int, fan_mode: int, temperature: float, device_ip: str = None):
        """Turn OFF horizontal swing without affecting other settings"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 97, dest_endpoint=1)  # CMD_HVAC_SET_MODE
        
        # Convert temperature to 16-bit little endian (temp * 100)
        temp_raw = int(temperature * 100)
        temp_bytes = struct.pack('<h', temp_raw)
        
        # Use flags=231 (255-8-16) to clear both turbo and horizontal swing
        # This successfully turns off swing without activating turbo mode
        flags = 231
        
        # Create 5-byte payload: mode, fan_mode, flags, temp_low, temp_high
        payload = bytes([mode, fan_mode, flags]) + temp_bytes
        packet = header + payload
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_fan_level(self, device_mac: str, fan_level: int, device_ip: str = None):
        """Set fan level (0=Auto, 1-5=Speed levels)"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 98, dest_endpoint=1)  # CMD_HVAC_COMMAND
        packet = header + bytes([25, fan_level])  # temp=25°C, fan_level
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def toggle_vertical_swing(self, device_mac: str, device_ip: str = None):
        """Toggle vertical swing mode"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 98, dest_endpoint=1)  # CMD_HVAC_COMMAND
        packet = header + bytes([97])  # HVAC_CMD_SWING_VERTICAL_TOGGLE
        
        print(f"Sending vertical swing packet: {packet.hex()}")
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def toggle_horizontal_swing(self, device_mac: str, device_ip: str = None):
        """Toggle horizontal swing mode"""
        if not self.transport:
            await self.connect()
        
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 98, dest_endpoint=1)  # CMD_HVAC_COMMAND
        packet = header + bytes([81])  # HVAC_CMD_SWING_HORIZONTAL_TOGGLE
        
        print(f"Sending horizontal swing packet: {packet.hex()}")
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def set_temperature_offset(self, device_mac: str, offset: int, device_ip: str = None):
        """Set room temperature offset (-32768 to 32767)"""
        if not self.transport:
            await self.connect()
        
        import struct
        mac_bytes = bytes.fromhex(device_mac.replace(':', ''))
        header = self._create_header(mac_bytes, 162)  # CMD_CUSTOM
        data = struct.pack('<BH', 101, offset & 0xFFFF)  # CUSTOM_TEMP_OFFSET + offset
        packet = header + data
        
        target_ip = device_ip or self.BROADCAST_IP
        self.transport.sendto(packet, (target_ip, self.PORT_CLIENT))
    
    async def listen_for_responses(self, timeout: float = 30.0):
        """Listen for responses"""
        if not self.protocol:
            await self.connect()
        
        try:
            await asyncio.wait_for(self.protocol.wait_for_responses(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
    
    def close(self):
        """Close connection"""
        if self.transport:
            self.transport.close()

class UDPProtocol(asyncio.DatagramProtocol):
    """UDP Protocol handler"""
    
    def __init__(self, response_handler: Callable):
        self.response_handler = response_handler
        
        # Set up logger
        import logging
        self._logger = logging.getLogger(__name__)
    
    def datagram_received(self, data, addr):
        """Handle received data"""
        try:
            response = self._decode_response(data)
            if response:
                self.response_handler(response, addr[0])

                # Log otherwise unhandled messages 
                if response.command_id in [128, 129]:
                    self._logger.debug(f"Response from {addr[0]} Command {response.command_id} - ACK/NACK")
                elif response.command_id in [245, 242, 251]:
                    # Try to decode ASCII parts
                    ascii_data = response.payload.decode('ascii', errors='ignore')
                    if ascii_data.strip():
                        self._logger.debug(f"Command {response.command_id} ASCII: {repr(ascii_data)}")
                    else:
                        self._logger.debug(f"Command {response.command_id} HEX: {response.payload.hex()}")
            else:
                self._logger.debug(f"Unhandled packet from {addr[0]} HEX: {data.hex()}")
                
        except Exception as e:
            self._logger.debug(f"Decode error: {e}")
    
    def _decode_response(self, data: bytes) -> Optional[DeviceResponse]:
        """Decode UDP response packet"""
        if len(data) < 17:
            return None
        
        # Extract MAC from packet header (bytes 4-10)
        mac_address = ':'.join(f'{b:02X}' for b in data[1:7])
        command_id = data[16]
        payload = data[17:] if len(data) > 17 else b''
        
        response = DeviceResponse(command_id=command_id, payload=payload)
        
        # Decode HVAC status (command 253)
        if command_id == 253 and len(payload) >= 12:
            status_type = payload[0]
            if status_type == 6:  # HVAC status type
                mode, fan_mode, flags = struct.unpack('<BBB', payload[1:4])
                measured_temp_raw = struct.unpack('<h', payload[4:6])[0]
                desired_temp_raw = struct.unpack('<h', payload[6:8])[0]
                timer_on = struct.unpack('<H', payload[8:10])[0]
                timer_off = struct.unpack('<H', payload[10:12])[0]
                
                response.hvac_status = HVACStatus(
                    mode=mode,
                    fan_mode=fan_mode,
                    flags=flags,
                    measured_temp=measured_temp_raw / 100.0,
                    desired_temp=desired_temp_raw / 100.0,
                    timer_on_minutes=timer_on,
                    timer_off_minutes=timer_off
                )
                self._logger.debug(f"HVAC Status Response from {mac_address}: {response.hvac_status}")
        
        # Decode HPA4911 status (command 162 response)
        elif command_id == 162 and len(payload) >= 8:
            custom_cmd = payload[0]
            if custom_cmd == 92:  # Battery status response
                rssi = payload[1]
                battery = (payload[3] << 8 | payload[2])
                ir_mac_formatted = ':'.join(f'{b:02X}' for b in payload[6:13])
                
                response.device_status = DeviceStatus(
                    rssi=rssi,
                    battery_level=battery,
                    ir_mac_address=ir_mac_formatted
                )
                self._logger.debug(f"Device Info Response from {mac_address}: {response.device_status}")
        
        # Decode Join Enumerate Response (command 161, subcommand 2)
        elif command_id == 161 and len(payload) >= 1:
            subcommand = payload[0]
            if subcommand == 2:  # Enumerate Response
                # Extract firmware info from payload[1:]
                try:
                    firmware_info = payload[1:].decode('utf-8', errors='ignore').rstrip('\x00')
                    if ',' in firmware_info:
                        parts = firmware_info.split(',')
                        firmware = parts[1] if len(parts) > 1 else ""
                        response.device_status = DeviceStatus(
                            firmware=firmware,
                            firmware_info=firmware_info
                        )
                        self._logger.debug(f"Device Info Response from {mac_address}: Firmware Info={firmware_info}")
                except Exception as e:
                    self._logger.warning(f"Error decoding Join response: {e}")
        
        return response