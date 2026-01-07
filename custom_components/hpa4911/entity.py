"""Base entity for HPA4911 integration."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .coordinator import HPA4911Coordinator
from .const import DOMAIN, MANUFACTURER, MODEL


class HPA4911Entity(CoordinatorEntity[HPA4911Coordinator]):
    """Base entity for HPA4911 integration."""
    
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HPA4911Coordinator, mac: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        
        self.mac = mac
        device_config = coordinator.get_device_config(mac)
        
        # Set up device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=device_config.get("name", "HPA-4911"),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        
        # Store device config for easy access
        self.device_config = device_config
    
    async def async_update(self) -> None:
        """Update the entity.
        
        Override the default CoordinatorEntity.async_update() to prevent
        calling coordinator.async_request_refresh() since we handle updates
        via callbacks and background tasks.
        """
        # Do nothing - updates come from coordinator callbacks
        pass
        
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available if coordinator has recent data for this device
        if not self.coordinator.last_update_success:
            return False
            
        # Check if we have recent data for this specific device (within last 5 minutes)
        device_data = self.coordinator.get_device_data(self.mac)
        if device_data and device_data.get("last_update"):
            import asyncio
            current_time = asyncio.get_event_loop().time()
            last_update = device_data["last_update"]
            return (current_time - last_update) < 300  # 5 minutes
            
        return False