   from homeassistant.config_entries import ConfigEntry
   from homeassistant.core import HomeAssistant
   
   async def async_setup(hass: HomeAssistant, config: dict) -> bool:
       return True
   
   async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
       return True
