"""Climate platform for Local BGH Smart."""
import logging
import asyncio
from typing import Any, Dict

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .hpa4911_client import HPA4911AsyncClient, HVACStatus

from .const import DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)

# Global shared client for all devices
_shared_client: HPA4911AsyncClient = None
_device_entities: Dict[str, 'HPA4911Climate'] = {}
_device_ip_to_mac: Dict[str, str] = {}

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
    """Set up Local BGH Smart climate entities."""
    global _shared_client, _device_entities, _device_ip_to_mac
    
    config = hass.data[DOMAIN][config_entry.entry_id]
    _LOGGER.debug("Setting up HPA4911 device: %s", config)
    
    # Initialize shared client if not exists
    if _shared_client is None:
        _LOGGER.debug("Initializing shared HPA4911 client...")
        _shared_client = HPA4911AsyncClient()
        _shared_client.set_climate_callback(_handle_shared_climate_update)
        try:
            await _shared_client.connect()
            _LOGGER.debug("Shared HPA4911 client initialized successfully")
        except Exception as e:
            _LOGGER.error("Failed to initialize shared client: %s", e)
            raise
    else:
        _LOGGER.debug("Using existing shared HPA4911 client")
    
    # Create entity and register IP mapping
    entity = HPA4911Climate(config, _shared_client)
    _device_entities[config["mac"]] = entity
    _device_ip_to_mac[config["ip_address"]] = config["mac"]
    async_add_entities([entity])
    await entity.async_update()
    _LOGGER.debug("HPA4911 climate entity setup completed for %s", config["name"])

def _handle_shared_climate_update(status: HVACStatus, source_ip: str) -> None:
    """Handle status update from shared client and route to correct entity."""
    global _device_ip_to_mac, _device_entities
    
    # Route status update based on source IP address
    if source_ip in _device_ip_to_mac:
        device_mac = _device_ip_to_mac[source_ip]
        if device_mac in _device_entities:
            _device_entities[device_mac]._handle_status_update(status)
            _LOGGER.debug("Routed status update from %s to device %s", source_ip, device_mac)
            return
    
    # Log status update if not found (shouldn't happen)
    _LOGGER.warning("Could not route status update from %s", source_ip)

class HPA4911Climate(ClimateEntity):
    """Local BGH Smart climate entity."""
    
    def __init__(self, device_config: dict, shared_client: HPA4911AsyncClient) -> None:
        """Initialize the climate entity."""
        self._device_config = device_config
        self._attr_name = device_config["name"]
        self._attr_unique_id = device_config["mac"].replace(":", "")
        self._attr_should_poll = True
        
        # Debug: Log the current configuration
        _LOGGER.debug("Device config: %s", device_config)
        
        # Device info for creating a device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_config["mac"])},
            name=device_config["name"],
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        
        self._client = shared_client
        
        # Current state
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF
        self._attr_fan_mode = "auto"
        
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
        self._attr_swing_mode = SWING_OFF
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = 16
        self._attr_max_temp = 30
        self._attr_target_temperature_step = 1
        self._attr_available = False
        self._last_update_time = None 
    
    async def async_update(self) -> None:
        """Send request to receive new state data for this HVAC."""
        try:
            await self._client.subscribe_hvac_status(
                self._device_config["mac"],
                self._device_config.get("ip_address")
            )
            await self._client.request_device_info(
                self._device_config.get("ip_address")
            )
            await self._client.request_battery_status(
                self._device_config["mac"],
                self._device_config.get("ip_address")
            )
            if self._last_update_time is None or asyncio.get_event_loop().time() - self._last_update_time > 120:
                self._attr_available = False
            _LOGGER.debug("Status request sent to %s at %s", 
                        self._device_config["mac"], 
                        self._device_config.get("ip_address"))
        except Exception as e:
            _LOGGER.error("Error updating %s: %s", self._attr_name, e)
    
    def _handle_status_update(self, status: HVACStatus) -> None:
        """Handle status update from device."""
        _LOGGER.debug("Status update received for %s: mode=%s, temp=%s->%s, fan=%s, flags=%s", 
                    self._attr_name, status.mode, status.measured_temp, status.desired_temp, status.fan_mode, status.flags)
        
        self._last_update_time = asyncio.get_event_loop().time()
        self._attr_available = True
        self._attr_current_temperature = status.measured_temp
        self._attr_target_temperature = status.desired_temp
        self._attr_hvac_mode = HPA4911_TO_HA_MODE.get(status.mode, HVACMode.OFF)
        
        # Determine HVAC action
        if status.mode == 0:
            self._attr_hvac_action = HVACAction.OFF
        elif status.mode == 1:  # Cool
            self._attr_hvac_action = HVACAction.COOLING
        elif status.mode == 2:  # Heat
            self._attr_hvac_action = HVACAction.HEATING
        elif status.mode == 3:  # Dry
            self._attr_hvac_action = HVACAction.DRYING
        elif status.mode == 4:  # Fan
            self._attr_hvac_action = HVACAction.FAN
        elif status.mode == 254:  # Auto
            self._attr_hvac_action = HVACAction.HEATING if status.desired_temp > status.measured_temp else HVACAction.COOLING
        else:
            self._attr_hvac_action = HVACAction.IDLE
        
        # Update fan mode (using cloud implementation mapping)
        self._attr_fan_mode = HPA4911_TO_HA_FAN.get(status.fan_mode, "auto")
        
        # Update swing mode based on flags (using cloud implementation mapping)
        if hasattr(status, 'flags') and status.flags is not None:
            # Check if horizontal swing flag (16) is set
            swing_flags = 16 if (status.flags & 16) else 0
            self._attr_swing_mode = HPA4911_TO_HA_SWING.get(swing_flags, SWING_OFF)
        
        self.schedule_update_ha_state()
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode in HA_TO_HPA4911_MODE:
            mode = HA_TO_HPA4911_MODE[hvac_mode]
            await self._client.set_hvac_mode(
                self._device_config["mac"],
                mode,
                self._device_config.get("ip_address")
            )
    
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            # Use complete HVAC command with current mode and fan settings
            current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
            current_fan = HA_TO_HPA4911_FAN.get(self._attr_fan_mode, 1)
            
            await self._client.set_hvac_with_swing(
                self._device_config["mac"],
                current_mode,
                current_fan, 
                float(temperature),
                False,  # horizontal_swing
                False,  # vertical_swing
                self._device_config.get("ip_address")
            )
    
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode."""
        if fan_mode in HA_TO_HPA4911_FAN:
            # Use current mode and temperature, only change fan
            current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
            current_temp = self._attr_target_temperature or 24
            
            await self._client.set_hvac_full(
                self._device_config["mac"],
                current_mode,
                HA_TO_HPA4911_FAN[fan_mode],
                0,  # flags
                float(current_temp),
                self._device_config.get("ip_address")
            )
    
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set swing mode."""
        current_mode = HA_TO_HPA4911_MODE.get(self._attr_hvac_mode, 1)
        current_temp = self._attr_target_temperature or 24
        current_fan = HA_TO_HPA4911_FAN.get(self._attr_fan_mode, 254)
        
        if swing_mode == SWING_ON:
            # Turn horizontal swing ON using flags=16
            await self._client.set_hvac_with_swing(
                self._device_config["mac"], 
                current_mode, 
                current_fan, 
                float(current_temp),
                horizontal_swing=True,
                device_ip=self._device_config.get("ip_address")
            )
        elif swing_mode == SWING_OFF:
            # Turn horizontal swing OFF using our working method (flags=231)
            await self._client.set_hvac_swing_off(
                self._device_config["mac"],
                current_mode,
                current_fan, 
                float(current_temp),
                device_ip=self._device_config.get("ip_address")
            )
        
        # Update state 
        self._attr_swing_mode = swing_mode