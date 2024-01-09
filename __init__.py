"""The FMI (Finnish Meteorological Institute) component."""

import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import fmi_weather_client as fmi
import requests
from async_timeout import timeout
from dateutil import tz
from fmi_weather_client.errors import ClientError, ServerError
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_OFFSET
from homeassistant.core import Config, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)

from .const import (
    _LOGGER, BASE_MAREO_FORC_URL, BASE_URL, BEST_COND_SYMBOLS,
    BEST_CONDITION_AVAIL, BEST_CONDITION_NOT_AVAIL,
    LIGHTNING_DAYS_LIMIT, CONF_MAX_HUMIDITY,
    CONF_MAX_PRECIPITATION, CONF_MAX_TEMP, CONF_MAX_WIND_SPEED,
    CONF_MIN_HUMIDITY, CONF_MIN_PRECIPITATION, CONF_MIN_TEMP,
    CONF_MIN_WIND_SPEED, CONF_DAILY_MODE, COORDINATOR, DOMAIN, LIGHTNING_LIMIT,
    MIN_TIME_BETWEEN_UPDATES, TIMEOUT_FMI_INTEG_IN_SEC,
    TIMEOUT_LIGHTNING_PULL_IN_SECS, TIMEOUT_MAREO_PULL_IN_SECS,
    UNDO_UPDATE_LISTENER, BOUNDING_BOX_HALF_SIDE_KM,
    LIGHTNING_LOOP_TIMEOUT_IN_SECS, CONF_LIGHTNING, CONF_FMISID,
)

from .utils import (
    get_bounding_box
)

PLATFORMS = ["sensor"]


def base_unique_id(fmisid):
    """Return unique id for entries in configuration."""
    return f"{fmisid}"


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up configured FMI."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass, config_entry) -> bool:
    """Set up FMI as config entry."""
    websession = async_get_clientsession(hass)

    coordinator = FMIDataUpdateCoordinator(
        hass, websession, config_entry
    )
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    undo_listener = config_entry.add_update_listener(update_listener)

    hass.data[DOMAIN][config_entry.entry_id] = {
        COORDINATOR: coordinator,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, component)
        )

    return True


async def async_unload_entry(hass, config_entry):
    """Unload an FMI config entry."""
    for component in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(config_entry, component)

    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()
    hass.data[DOMAIN].pop(config_entry.entry_id)

    return True


async def update_listener(hass, config_entry):
    """Update FMI listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)



class FMIMareoStruct():

    #def __init__(self, time_val=None, sea_level_now=None, sea_level_6hrs=None):
    def __init__(self, sea_levels=None):
        """Initialize the sea height data."""
        self.sea_levels = sea_levels


class FMIDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching FMI data API."""

    def __init__(self, hass, session, config_entry):
        """Initialize."""

        _LOGGER.debug("Using lat: %s and long: %s",
            config_entry.data[CONF_LATITUDE], config_entry.data[CONF_LONGITUDE])

        self.latitude = config_entry.data[CONF_LATITUDE]
        self.longitude = config_entry.data[CONF_LONGITUDE]
        self.fmisid = config_entry.data[CONF_FMISID]
        self.unique_id = str(self.fmisid)
        self.time_step = config_entry.options.get(CONF_OFFSET, 1)

        # Mareo
        self.mareo_data = None

        _LOGGER.debug("FMI: Data will be updated every %s min", MIN_TIME_BETWEEN_UPDATES)

        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=MIN_TIME_BETWEEN_UPDATES
        )

    async def _async_update_data(self):
        """Update data via Open API."""
        def update_mareo_data():
            """Get the latest mareograph forecast data from FMI and update the states."""

            _LOGGER.debug(f"FMI: mareo started")
            ## Format datetime to string accepted as path parameter in REST
            start_time = datetime.today()
            start_time = str(start_time).split(".")[0]
            start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            start_time = "starttime=" + str(start_time.date()) + "T" + str(start_time.time()) + "Z"

            ## Format location to string accepted as path parameter in REST
            loc_string = "latlon=" + str(self.latitude) + "," + str(self.longitude)

            base_mareo_url = BASE_MAREO_FORC_URL + loc_string + "&" + start_time + "&"
            _LOGGER.debug("FMI: Using Mareo url: %s", base_mareo_url)

            ## Fetch data
            response_mareo = requests.get(base_mareo_url, timeout=TIMEOUT_MAREO_PULL_IN_SECS)

            root_mareo = ET.fromstring(response_mareo.content)

            sealevel_tuple_list = []
            for n in range(len(root_mareo)):
                try:
                    if root_mareo[n][0][2].text == 'SeaLevel':
                        tuple_to_add = (root_mareo[n][0][1].text, root_mareo[n][0][3].text)
                        sealevel_tuple_list.append(tuple_to_add)
                    elif root_mareo[n][0][2].text == 'SeaLevelN2000':
                        continue
                    else:
                        _LOGGER.debug("Sealevel forecast unsupported record: %s", root_mareo[n][0][2].text)
                        continue
                except:
                    _LOGGER.debug(f"Sealevel forecast records not in expected format for index - {n} of locstring - {loc_string}")

            mareo_op = FMIMareoStruct(sea_levels=sealevel_tuple_list)
            self.mareo_data = mareo_op
            if len(sealevel_tuple_list) > 12:
                _LOGGER.debug("FMI: Mareo_data updated with data: %s %s", sealevel_tuple_list[0], sealevel_tuple_list[12])
            else:
                _LOGGER.debug("FMI: Mareo_data not updated. No data available!")

            _LOGGER.debug(f"FMI: mareo ended")
            return

        try:
            async with timeout(TIMEOUT_FMI_INTEG_IN_SEC):
                # Update mareograph data on sea level
                await self._hass.async_add_executor_job(
                    update_mareo_data
                )
                _LOGGER.debug("FMI: Mareograph sea level data updated!")

        except (ClientError, ServerError) as error:
            raise UpdateFailed(error) from error
        return {}
