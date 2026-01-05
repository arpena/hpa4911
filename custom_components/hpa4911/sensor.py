"""Sensor platform for HPA4911 device info."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import ( 
    DeviceInfo,
    EntityCategory,
)

from .hpa4911_client import DeviceStatus
from .const import DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)
# Global shared client for all devices
_device_entities: Dict[str, List] = {}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HPA4911 sensors."""
    # Import here to avoid circular import and ensure climate is loaded first
    from .climate import _shared_client
    global _device_entities

    # Get device MAC and name from config
    device_mac = config_entry.data.get("mac", "unknown")
    device_name = config_entry.data.get("name", "HPA-4911")

    _LOGGER.debug(f"Setting up sensors for device {device_name} (MAC: {device_mac})")
    
    # Create sensor entities
    sensors = [
        HPA4911FirmwareSensor(device_name, device_mac),
        HPA4911BatterySensor(device_name, device_mac),
    ]
    async_add_entities(sensors, True)
    _device_entities[device_mac] = sensors
    _shared_client.set_sensor_callback(_handle_shared_device_info_update)

def _handle_shared_device_info_update(status: DeviceStatus, source_ip: str) -> None:
    """Handle status update from shared client and route to correct entity."""
    global _device_entities
    from .climate import _device_ip_to_mac
    
    # Route status update based on source IP address
    if source_ip in _device_ip_to_mac:
        device_mac = _device_ip_to_mac[source_ip]
        if device_mac in _device_entities:
            for entity in _device_entities[device_mac]:
                entity._handle_status_update(status)
            _LOGGER.debug("Routed status update from %s to device %s", source_ip, device_mac)
            return
    
    # Log status update if not found (shouldn't happen)
    _LOGGER.warning("Could not route status update from %s", source_ip)

class HPA4911FirmwareSensor(SensorEntity):
    """Firmware version sensor."""
    
    def __init__(self, name: str, mac: str):
        self._mac = mac.lower()  # Normalize MAC to lowercase
        self._attr_friendly_name = f"Firmware"
        self._attr_name = f"{name} Firmware"
        self._attr_unique_id = f"{mac}_firmware"
        self._attr_icon = "mdi:chip"
        self._attr_should_poll = False  # Disable polling. It is handled in the climate entity
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
        # Use the same device identifier as the climate entity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def _handle_status_update(self, status: DeviceStatus) -> None:
        """Handle status update from shared client."""
        # Update state with firmware version from status
        if status.firmware is not None:
            self._attr_native_value = status.firmware
            self._attr_extra_state_attributes = {"firmware_info": status.firmware_info}
            self.async_write_ha_state()
            _LOGGER.debug(f"Updated firmware sensor for device {self._mac} to {status.firmware}")

class HPA4911BatterySensor(SensorEntity):
    """IR module battery sensor."""
    
    def __init__(self, name: str, mac: str):
        self._mac = mac.lower()  # Normalize MAC to lowercase
        self._original_mac = mac  # Keep original format for device ID
        self._attr_friendly_name = f"IR Battery"
        self._attr_name = f"{name} IR Battery"
        self._attr_unique_id = f"{mac}_ir_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_should_poll = False  # Disable polling. It is handled in the climate entity
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Use the same device identifier as the climate entity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        ) 

    def _handle_status_update(self, status: DeviceStatus) -> None:
        """Handle status update from shared client."""
        # Update state with firmware version from status
        if status.battery_level is not None:
            self._attr_native_value = status.battery_level
            self.async_write_ha_state()
            _LOGGER.debug(f"Updated battery sensor for device {self._mac} to {status.battery_level}")
    
    @property
    def icon(self) -> str:
        level = self.state
        if level is None:
            return "mdi:battery-unknown"
        if level == 0:
            return "mdi:battery-outline"
        if level > 75:
            return "mdi:battery"
        if level > 50:
            return "mdi:battery-70"
        if level > 25:
            return "mdi:battery-30"
        return "mdi:battery-10"
