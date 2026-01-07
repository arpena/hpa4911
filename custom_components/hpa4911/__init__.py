"""Local BGH Smart integration for Home Assistant."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN
from .coordinator import get_coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Local BGH Smart from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Get or create the shared coordinator
    coordinator = await get_coordinator(hass)
    
    # Add this device to the coordinator
    coordinator.add_device(entry)
    
    # Store the coordinator reference for this entry
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Remove this device from the coordinator
        coordinator.remove_device(entry)
        
        # If no more devices, shutdown the coordinator
        if not coordinator.devices:
            await coordinator.async_shutdown()
    return unload_ok