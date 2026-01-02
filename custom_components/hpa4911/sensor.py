"""Sensor platform for HPA4911 device info."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .device_info import HPA4911DeviceInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HPA4911 sensors."""
    # Import here to avoid circular import and ensure climate is loaded first
    from .climate import _device_info
    
    # Get device MAC from config
    device_mac = config_entry.data.get("mac", "unknown")
    # Provisorial device name
    device_name = "HPA4911"
    
    # Wait for device info to be initialized
    if _device_info is None:
        _LOGGER.warning("Device info not initialized yet, sensors may show Unknown initially")
    else:
        device_name = _device_info.get_device_name(device_mac)

    _LOGGER.debug(f"Setting up sensors for device {device_name} (MAC: {device_mac})")
    
    # Create sensor entities
    sensors = [
        HPA4911FirmwareSensor(_device_info, device_name, device_mac),
        HPA4911BLEFirmwareSensor(_device_info, device_name, device_mac),
        HPA4911BatterySensor(_device_info, device_name, device_mac),
    ]
    
    async_add_entities(sensors, True)

class HPA4911FirmwareSensor(SensorEntity):
    """Firmware version sensor."""
    
    def __init__(self, info: HPA4911DeviceInfo, name: str, mac: str):
        self._info = info
        self._mac = mac.lower()  # Normalize MAC to lowercase
        self._original_mac = mac  # Keep original format for device ID
        self._attr_friendly_name = f"Firmware"
        self._attr_name = f"{name} Firmware"
        self._attr_unique_id = f"{mac}_firmware"
        self._attr_icon = "mdi:chip"
        self._attr_should_poll = True  # Enable polling
        
    @property
    def device_info(self) -> DeviceInfo:
        # Use the same device identifier as the climate entity
        return DeviceInfo(
            identifiers={(DOMAIN, self._original_mac)},
            name=f"HPA4911 {self._mac[-5:]}",
            manufacturer="BGH",
            model="HPA-4911",
        )
    
    @property
    def state(self) -> str:
        # Get device info dynamically
        from .climate import _device_info
        if _device_info:
            info = _device_info.get_device_info(self._mac)
            return info.get('main_firmware', 'Unknown')
        return 'Unknown'

class HPA4911BLEFirmwareSensor(SensorEntity):
    """BLE firmware version sensor."""
    
    def __init__(self, info: HPA4911DeviceInfo, name: str, mac: str):
        self._info = info
        self._mac = mac.lower()  # Normalize MAC to lowercase
        self._original_mac = mac  # Keep original format for device ID
        self._attr_friendly_name = f"BLE Firmware"
        self._attr_name = f"{name} BLE Firmware"
        self._attr_unique_id = f"{mac}_ble_firmware"
        self._attr_icon = "mdi:bluetooth"
        self._attr_should_poll = True  # Enable polling
        
    @property
    def device_info(self) -> DeviceInfo:
        # Use the same device identifier as the climate entity
        return DeviceInfo(
            identifiers={(DOMAIN, self._original_mac)},
            name=f"HPA4911 {self._mac[-5:]}",
            manufacturer="BGH",
            model="HPA-4911",
        )
    
    @property
    def state(self) -> str:
        # Get device info dynamically
        from .climate import _device_info
        if _device_info:
            info = _device_info.get_device_info(self._mac)
            return info.get('ble_firmware', 'Unknown')
        return 'Unknown'

class HPA4911BatterySensor(SensorEntity):
    """IR module battery sensor."""
    
    def __init__(self, info: HPA4911DeviceInfo, name: str, mac: str):
        self._info = info
        self._mac = mac.lower()  # Normalize MAC to lowercase
        self._original_mac = mac  # Keep original format for device ID
        self._attr_friendly_name = f"IR Battery"
        self._attr_name = f"{name} IR Battery"
        self._attr_unique_id = f"{mac}_ir_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_should_poll = True  # Enable polling
        
    @property
    def device_info(self) -> DeviceInfo:
        # Use the same device identifier as the climate entity
        return DeviceInfo(
            identifiers={(DOMAIN, self._original_mac)},
            name=f"HPA4911 {self._mac[-5:]}",
            manufacturer="BGH",
            model="HPA-4911",
        )
    
    @property
    def state(self) -> int:
        # Get device info dynamically
        from .climate import _device_info
        if _device_info:
            info = _device_info.get_device_info(self._mac)
            return info.get('ir_battery_level', 0)
        return 0
        
    @property
    def icon(self) -> str:
        level = self.state
        if level > 75:
            return "mdi:battery"
        elif level > 50:
            return "mdi:battery-70"
        elif level > 25:
            return "mdi:battery-30"
        else:
            return "mdi:battery-10"
