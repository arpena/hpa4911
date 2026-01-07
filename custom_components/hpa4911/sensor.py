"""Sensor platform for HPA4911 device info."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .coordinator import HPA4911Coordinator
from .entity import HPA4911Entity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HPA4911 sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    mac = config_entry.data["mac"]
    
    # Create sensor entities
    sensors = [
        HPA4911FirmwareSensor(coordinator, mac),
        HPA4911BatterySensor(coordinator, mac),
    ]
    async_add_entities(sensors, True)
    _LOGGER.debug("HPA4911 sensor entities setup completed for %s", config_entry.data["name"])

class HPA4911FirmwareSensor(HPA4911Entity, SensorEntity):
    """Firmware version sensor."""
    
    def __init__(self, coordinator: HPA4911Coordinator, mac: str):
        super().__init__(coordinator, mac)
        self._attr_name = "Firmware"
        self._attr_unique_id = f"{mac}_firmware"
        self._attr_icon = "mdi:chip"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device_data = self.coordinator.get_device_data(self.mac)
        if not device_data:
            return
            
        device_status = device_data.get("device_status")
        if device_status and device_status.firmware is not None:
            self._attr_native_value = device_status.firmware
            self._attr_extra_state_attributes = {"firmware_info": device_status.firmware_info}
            _LOGGER.debug(f"Updated firmware sensor to {device_status.firmware}")
        
        super()._handle_coordinator_update()


class HPA4911BatterySensor(HPA4911Entity, SensorEntity):
    """IR module battery sensor."""
    
    def __init__(self, coordinator: HPA4911Coordinator, mac: str):
        super().__init__(coordinator, mac)
        self._attr_name = "IR Battery"
        self._attr_unique_id = f"{mac}_ir_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device_data = self.coordinator.get_device_data(self.mac)
        if not device_data:
            return
            
        device_status = device_data.get("device_status")
        if device_status and device_status.battery_level is not None:
            self._attr_native_value = device_status.battery_level
            _LOGGER.debug(f"Updated battery sensor to {device_status.battery_level}")
        
        super()._handle_coordinator_update()
    
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
