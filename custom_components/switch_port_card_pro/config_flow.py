import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN, CONF_COMMUNITY, CONF_PORTS, DEFAULT_PORTS

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @vol.Schema({
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_COMMUNITY): str,
        vol.Optional(CONF_NAME, default="Switch Port Card Pro"): str,
        vol.Optional(CONF_PORTS, default=DEFAULT_PORTS): vol.All(vol.Coerce(list), [vol.Range(min=1, max=64)]),
    })
    async def async_step_user(user_input: dict) -> FlowResult:
        return config_entries.ConfigEntry(
            title=user_input[CONF_NAME],
            data=user_input
        )
