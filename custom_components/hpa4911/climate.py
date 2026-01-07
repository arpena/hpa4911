"""Climate platform for Local BGH Smart."""
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
    SWING_ON,
    SWING_OFF,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HPA4911Coordinator
from .entity import HPA4911Entity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Local protocol mode mapping (matches cloud implementation)
HPA4911_TO_HA_MODE = {
    0: HVACMode.OFF,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    254: HVACMode.AUTO,
}

HA_TO_HPA4911_MODE = {v: k for k, v in HPA4911_TO_HA_MODE.items()}

# Fan mode mapping (matches cloud implementation)
HPA4911_TO_HA_FAN = {
    1: "low",
    2: "medium", 
    3: "high",
    254: "auto"
}

HA_TO_HPA4911_FAN = {v: k for k, v in HPA4911_TO_HA_FAN.items()}

# Swing mode mapping (matches cloud implementation)
HPA4911_TO_HA_SWING = {
    0: SWING_OFF,
    8: SWING_OFF,
    16: SWING_ON,
    24: SWING_ON,
    203: SWING_OFF
}

# status subscriptions are maintained for 2 minutes by the device
from datetime import timedelta
SCAN_INTERVAL = timedelta(minutes=2)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HPA4911 climate entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    mac = config_entry.data["mac"]
    
    # Set up the coordinator if not already done
    if coordinator.client is None:
        await coordinator._async_setup()
    
    # Create climate entity
    async_add_entities([HPA4911Climate(coordinator, mac)])
    _LOGGER.debug("HPA4911 climate entity setup completed for %s", config_entry.data["name"])

class HPA4911Climate(HPA4911Entity, ClimateEntity):
    """HPA4911 climate entity."""
    
    def __init__(self, coordinator: HPA4911Coordinator, mac: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, mac)
        
        self._attr_name = None  # Use device name
        self._attr_unique_id = f"{mac}_climate"
        
        # Initialize state attributes
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_fan_mode = "auto"
        self._attr_swing_mode = SWING_OFF
        
        # Supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.FAN_MODE |
            ClimateEntityFeature.SWING_MODE
        )
        
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
            HVACMode.AUTO,
        ]
        
        self._attr_fan_modes = ["low", "medium", "high", "auto"]
        self._attr_swing_modes = [SWING_OFF, SWING_ON]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 1
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device_data = self.coordinator.get_device_data(self.mac)
        if not device_data:
            return
            
        hvac_status = device_data.get("hvac_status")
        if hvac_status:
            self._attr_current_temperature = hvac_status.measured_temp
            self._attr_target_temperature = hvac_status.desired_temp
            self._attr_hvac_mode = HPA4911_TO_HA_MODE.get(hvac_status.mode, HVACMode.OFF)
            
            # Determine HVAC action
            if hvac_status.mode == 0:
                self._attr_hvac_action = HVACAction.OFF
            elif hvac_status.mode == 1:  # Cool
                self._attr_hvac_action = HVACAction.COOLING
            elif hvac_status.mode == 2:  # Heat
                self._attr_hvac_action = HVACAction.HEATING
            elif hvac_status.mode == 3:  # Dry
                self._attr_hvac_action = HVACAction.DRYING
            elif hvac_status.mode == 4:  # Fan
                self._attr_hvac_action = HVACAction.FAN
            elif hvac_status.mode == 254:  # Auto
                self._attr_hvac_action = HVACAction.HEATING if hvac_status.desired_temp > hvac_status.measured_temp else HVACAction.COOLING
            else:
                self._attr_hvac_action = HVACAction.IDLE
            
            # Update fan mode
            self._attr_fan_mode = HPA4911_TO_HA_FAN.get(hvac_status.fan_mode, "auto")
            
            # Update swing mode based on flags
            if hasattr(hvac_status, 'flags') and hvac_status.flags is not None:
                # Check if horizontal swing flag (16) is set
                swing_flags = 16 if (hvac_status.flags & 16) else 0
                self._attr_swing_mode = HPA4911_TO_HA_SWING.get(swing_flags, SWING_OFF)
        
        super()._handle_coordinator_update()
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode in HA_TO_HPA4911_MODE:
            mode = HA_TO_HPA4911_MODE[hvac_mode]
            await self.coordinator.async_set_hvac_mode(self.mac, mode)
    
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            # Use complete HVAC command with current mode and fan settings
            current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
            current_fan = HA_TO_HPA4911_FAN.get(self._attr_fan_mode, 1)
            
            await self.coordinator.async_set_hvac_with_swing(
                self.mac,
                current_mode,
                current_fan, 
                float(temperature),
                False,  # horizontal_swing
                False,  # vertical_swing
            )
    
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        if fan_mode in HA_TO_HPA4911_FAN:
            # Use current mode and temperature, only change fan
            current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
            current_temp = self._attr_target_temperature or 24
            
            await self.coordinator.async_set_hvac_full(
                self.mac,
                current_mode,
                HA_TO_HPA4911_FAN[fan_mode],
                0,  # flags
                float(current_temp),
            )
    
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set swing mode."""
        current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
        current_temp = self._attr_target_temperature or 24
        current_fan = HA_TO_HPA4911_FAN.get(self._attr_fan_mode, 254)
        
        if swing_mode == SWING_ON:
            # Turn horizontal swing ON using flags=16
            await self.coordinator.async_set_hvac_with_swing(
                self.mac,
                current_mode, 
                current_fan, 
                float(current_temp),
                horizontal_swing=True,
            )
        elif swing_mode == SWING_OFF:
            # Turn horizontal swing OFF using our working method (flags=231)
            await self.coordinator.async_set_hvac_swing_off(
                self.mac,
                current_mode,
                current_fan, 
                float(current_temp),
            )
        
        # Update state
        self._attr_swing_mode = swing_mode