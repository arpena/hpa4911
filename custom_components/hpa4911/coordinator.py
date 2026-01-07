"""DataUpdateCoordinator for HPA4911 integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Dict, Any, Optional, Set

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.config_entries import ConfigEntry

from .hpa4911_client import HPA4911AsyncClient, HVACStatus, DeviceStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Global shared coordinator instance
_shared_coordinator: Optional['HPA4911Coordinator'] = None

class HPA4911Coordinator(DataUpdateCoordinator):
    """Class to manage fetching data from all HPA4911 devices."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # No update_interval - we'll handle subscriptions with a background task
        )
        
        self.client: Optional[HPA4911AsyncClient] = None
        self.devices: Dict[str, Dict[str, Any]] = {}  # MAC -> device config
        self.device_data: Dict[str, Dict[str, Any]] = {}  # MAC -> device data
        self.ip_to_mac: Dict[str, str] = {}  # IP -> MAC mapping
        self._subscription_task: Optional[asyncio.Task] = None
        
    def add_device(self, config_entry: ConfigEntry) -> None:
        """Add a device to the coordinator."""
        device_config = config_entry.data
        mac = device_config["mac"]
        ip = device_config.get("ip_address")
        
        self.devices[mac] = device_config
        if ip:
            self.ip_to_mac[ip] = mac
            
        # Initialize device data
        self.device_data[mac] = {
            "hvac_status": None,
            "device_status": None,
            "last_update": None,
        }
        
        _LOGGER.debug("Added device %s (MAC: %s) to coordinator", device_config["name"], mac)
    
    def remove_device(self, config_entry: ConfigEntry) -> None:
        """Remove a device from the coordinator."""
        device_config = config_entry.data
        mac = device_config["mac"]
        ip = device_config.get("ip_address")
        
        self.devices.pop(mac, None)
        self.device_data.pop(mac, None)
        if ip and ip in self.ip_to_mac:
            self.ip_to_mac.pop(ip)
            
        _LOGGER.debug("Removed device %s (MAC: %s) from coordinator", device_config["name"], mac)
    
    def get_device_data(self, mac: str) -> Dict[str, Any]:
        """Get data for a specific device."""
        return self.device_data.get(mac, {})
    
    def get_device_config(self, mac: str) -> Dict[str, Any]:
        """Get config for a specific device."""
        return self.devices.get(mac, {})
        
    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        if self.client is None:
            self.client = HPA4911AsyncClient()
            # Set up callbacks to handle real-time updates
            self.client.set_climate_callback(self._handle_hvac_update)
            self.client.set_sensor_callback(self._handle_device_update)
            
            try:
                await self.client.connect()
                _LOGGER.debug("Shared HPA4911 client connected")
                
                # Start the background subscription refresh task
                self._subscription_task = asyncio.create_task(self._subscription_refresh_loop())
                
            except Exception as e:
                _LOGGER.error("Failed to connect HPA4911 client: %s", e)
                raise UpdateFailed(f"Failed to connect to device: {e}")

    async def _subscription_refresh_loop(self) -> None:
        """Background task to refresh subscriptions every 2 minutes."""
        while True:
            try:
                # First refresh, then wait
                await self._refresh_subscriptions()
                await asyncio.sleep(120)  # 2 minutes
            except asyncio.CancelledError:
                _LOGGER.debug("Subscription refresh task cancelled")
                break
            except Exception as e:
                _LOGGER.error("Error in subscription refresh loop: %s", e)
                # Continue the loop even if there's an error

    async def _refresh_subscriptions(self) -> None:
        """Refresh subscriptions for all devices."""
        _LOGGER.debug("Refreshing subscriptions for %d devices", len(self.devices))
        
        # Request subscriptions sequentially for each device
        for mac, device_config in self.devices.items():
            await self.client.subscribe_hvac_status(
                mac,
                device_config.get("ip_address")
            )
            
            await self.client.request_device_info(
                device_config.get("ip_address")
            )
            
            await self.client.request_battery_status(
                mac,
                device_config.get("ip_address")
            )

    def _handle_hvac_update(self, status: HVACStatus, source_ip: str) -> None:
        """Handle HVAC status update from device."""
        # Find device by IP
        mac = self.ip_to_mac.get(source_ip)
        if mac and mac in self.device_data:
            _LOGGER.debug("HVAC status update for device %s: %s", mac, status)
            self.device_data[mac]["hvac_status"] = status
            self.device_data[mac]["last_update"] = asyncio.get_event_loop().time()
            # Trigger update to all listening entities
            self.async_set_updated_data(self.device_data)

    def _handle_device_update(self, status: DeviceStatus, source_ip: str) -> None:
        """Handle device status update from device."""
        # Find device by IP
        mac = self.ip_to_mac.get(source_ip)
        if mac and mac in self.device_data:
            _LOGGER.debug("Device status update for device %s: %s", mac, status)
            self.device_data[mac]["device_status"] = status
            self.device_data[mac]["last_update"] = asyncio.get_event_loop().time()
            # Trigger update to all listening entities
            self.async_set_updated_data(self.device_data)

    async def async_set_hvac_mode(self, mac: str, mode: int) -> None:
        """Set HVAC mode for a specific device."""
        if self.client and mac in self.devices:
            device_config = self.devices[mac]
            await self.client.set_hvac_mode(
                mac,
                mode,
                device_config.get("ip_address")
            )

    async def async_set_hvac_full(self, mac: str, mode: int, fan_mode: int, flags: int, temperature: float) -> None:
        """Set HVAC mode, fan, and temperature for a specific device."""
        if self.client and mac in self.devices:
            device_config = self.devices[mac]
            await self.client.set_hvac_full(
                mac,
                mode,
                fan_mode,
                flags,
                temperature,
                device_config.get("ip_address")
            )

    async def async_set_hvac_with_swing(self, mac: str, mode: int, fan_mode: int, temperature: float, 
                                       horizontal_swing: bool = False, vertical_swing: bool = False) -> None:
        """Set HVAC with swing settings for a specific device."""
        if self.client and mac in self.devices:
            device_config = self.devices[mac]
            await self.client.set_hvac_with_swing(
                mac,
                mode,
                fan_mode,
                temperature,
                horizontal_swing,
                vertical_swing,
                device_config.get("ip_address")
            )

    async def async_set_hvac_swing_off(self, mac: str, mode: int, fan_mode: int, temperature: float) -> None:
        """Turn off HVAC swing for a specific device."""
        if self.client and mac in self.devices:
            device_config = self.devices[mac]
            await self.client.set_hvac_swing_off(
                mac,
                mode,
                fan_mode,
                temperature,
                device_config.get("ip_address")
            )

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self._subscription_task:
            self._subscription_task.cancel()
            try:
                await self._subscription_task
            except asyncio.CancelledError:
                pass
            self._subscription_task = None
            
        if self.client:
            self.client.close()
            self.client = None


async def get_coordinator(hass: HomeAssistant) -> HPA4911Coordinator:
    """Get or create the shared coordinator."""
    global _shared_coordinator
    
    if _shared_coordinator is None:
        _shared_coordinator = HPA4911Coordinator(hass)
        
    return _shared_coordinator