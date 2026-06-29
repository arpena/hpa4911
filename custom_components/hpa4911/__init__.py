"""Local BGH Smart integration for Home Assistant."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import HPA4911Coordinator, get_coordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

type HPA4911ConfigEntry = ConfigEntry[HPA4911Coordinator]

async def async_setup_entry(hass: HomeAssistant, entry: HPA4911ConfigEntry) -> bool:
    """Set up Local BGH Smart from a config entry."""
    # Get or create the shared coordinator
    coordinator = await get_coordinator(hass)
    
    # Add this device to the coordinator
    coordinator.add_device(entry)
    
    # Verify we can connect before proceeding
    try:
        await coordinator._async_setup()
    except Exception as err:
        coordinator.remove_device(entry)
        raise ConfigEntryNotReady(
            f"Unable to connect to device: {err}"
        ) from err
    
    # Store the coordinator reference in runtime_data
    entry.runtime_data = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: HPA4911ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = entry.runtime_data
        # Remove this device from the coordinator
        coordinator.remove_device(entry)
        
        # If no more devices, shutdown the coordinator
        if not coordinator.devices:
            await coordinator.async_shutdown()
    return unload_ok