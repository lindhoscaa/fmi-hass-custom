"""Support for weather service from FMI (Finnish Meteorological Institute) for sensor platform."""

# Import homeassistant platform dependencies
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_TIME,
)

from homeassistant.components.sensor import (
    SensorStateClass
)

from homeassistant.const import CONF_NAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_LIGHTNING,
    _LOGGER,
    ATTRIBUTION,
    DOMAIN,
    COORDINATOR
)

SENSOR_MAREO_TYPES = {
    "sea_level": ["Sea Level", "cm"]
}

PARALLEL_UPDATES = 1

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the FMI Sensor, including Best Time Of the Day sensor."""
    name = config_entry.data[CONF_NAME]

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]

    entity_list = []

    for sensor_type in SENSOR_MAREO_TYPES:
        entity_list.append(
            FMIMareoSensor(name, coordinator, sensor_type))

    async_add_entities(entity_list, False)


class FMIMareoSensor(CoordinatorEntity):
    """Implementation of a FMI sea water level sensor."""

    def __init__(self, name, coordinator, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.client_name = name
        self._name = SENSOR_MAREO_TYPES[sensor_type][0]
        self._state = None
        self._icon = "mdi:waves"
        self.type = sensor_type
        self._unit_of_measurement = SENSOR_MAREO_TYPES[sensor_type][1]
        self._fmi = coordinator

        try:
            self._fmi_name = coordinator.current.place
        except:
            self._fmi_name = None

        self.update()

    @property
    def name(self):
        """Return the name of the sensor."""

        if self._fmi_name is not None:
            return f"{self._fmi_name} {self._name}"
        else:
            return f"{self.client_name} {self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""

        self.update()
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""

        mareo_data = self._fmi.mareo_data.sea_levels

        if mareo_data is None:
            return []

        if len(mareo_data) > 1:
            pass
        elif len(mareo_data) > 0:
            return {
                ATTR_TIME: mareo_data[0][0],
                "FORECASTS": [],
                ATTR_ATTRIBUTION: ATTRIBUTION
            }
        else:
            return []

        return {
            ATTR_TIME: mareo_data[0][0],
            "FORECASTS": [
                {"time": item[0], "height": item[1]} for item in mareo_data[1:]
            ],
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    def update(self):
        """Get the latest data from FMI and updates the states."""

        mareo_data = self._fmi.mareo_data.sea_levels

        try:
            self._state = mareo_data[0][1]
        except:
            _LOGGER.debug("FMI: Sensor Mareo is unavailable")
            self._state = "Unavailable"

        return
