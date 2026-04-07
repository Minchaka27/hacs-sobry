"""Sensor platform for Sobry Energy integration."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_ALL_PRICES,
    SENSOR_AVG_PRICE,
    SENSOR_CURRENT_PRICE,
    SENSOR_MAX_PRICE,
    SENSOR_MEDIAN_PRICE,
    SENSOR_MIN_PRICE,
    SENSOR_NEXT_HOUR_PRICE,
    SENSOR_TYPES,
)
from .coordinator import SobryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sobry Energy sensor based on a config entry."""
    coordinator: SobryDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for sensor_type in SENSOR_TYPES:
        entities.append(SobryPriceSensor(coordinator, sensor_type))

    async_add_entities(entities)


class SobryPriceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Sobry Energy price sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SobryDataUpdateCoordinator,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{sensor_type}"

        # Set name and icon based on sensor type
        self._attr_name = self._get_sensor_name()
        self._attr_icon = self._get_sensor_icon()
        self._attr_native_unit_of_measurement = self._get_sensor_unit()
        self._attr_state_class = (
            None if sensor_type == SENSOR_ALL_PRICES else SensorStateClass.MEASUREMENT
        )

    def _get_sensor_name(self) -> str:
        """Get the sensor name based on type."""
        names = {
            SENSOR_CURRENT_PRICE: "Prix actuel",
            SENSOR_MIN_PRICE: "Prix minimum",
            SENSOR_MAX_PRICE: "Prix maximum",
            SENSOR_AVG_PRICE: "Prix moyen",
            SENSOR_MEDIAN_PRICE: "Prix médian",
            SENSOR_NEXT_HOUR_PRICE: "Prix 15 min suivant",
            SENSOR_ALL_PRICES: "Prix du jour",
        }
        return names.get(self.sensor_type, self.sensor_type)

    def _get_sensor_icon(self) -> str:
        """Get the sensor icon based on type."""
        if self.sensor_type == SENSOR_ALL_PRICES:
            return "mdi:chart-line"
        return "mdi:flash"

    def _get_sensor_unit(self) -> str | None:
        """Get the sensor unit based on type."""
        if self.sensor_type == SENSOR_ALL_PRICES:
            return None  # JSON data has no unit
        return "€/kWh"

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class of the sensor."""
        if self.sensor_type == SENSOR_ALL_PRICES:
            return None  # JSON data is not a measurement
        return SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # Get the price field based on display mode
        price_field = self._get_price_field()

        if self.sensor_type == SENSOR_CURRENT_PRICE:
            price_data = self.coordinator.data.get("current_price") or {}
            return price_data.get(price_field)

        elif self.sensor_type == SENSOR_NEXT_HOUR_PRICE:
            price_data = self.coordinator.data.get("next_price") or {}
            return price_data.get(price_field)

        elif self.sensor_type == SENSOR_MIN_PRICE:
            return self.coordinator.data.get("statistics", {}).get("min")

        elif self.sensor_type == SENSOR_MAX_PRICE:
            return self.coordinator.data.get("statistics", {}).get("max")

        elif self.sensor_type == SENSOR_AVG_PRICE:
            return self.coordinator.data.get("statistics", {}).get("average")

        elif self.sensor_type == SENSOR_MEDIAN_PRICE:
            return self.coordinator.data.get("statistics", {}).get("median")

        elif self.sensor_type == SENSOR_ALL_PRICES:
            prices = self.coordinator.data.get("prices", [])
            if not prices:
                return None
            price_field = self._get_price_field()
            # Build a list of all prices with slot and timestamp (96 slots = 15 min intervals)
            all_prices = []
            for i, p in enumerate(prices):
                all_prices.append(
                    {
                        "slot": i,
                        "timestamp": p.get("timestamp"),
                        "price": p.get(price_field),
                        "spot_price": p.get("spot_price_eur_kwh"),
                    }
                )
            return json.dumps(all_prices, ensure_ascii=False)

        return None

    def _get_price_field(self) -> str:
        """Get the price field name based on coordinator configuration."""
        if not self.coordinator.data:
            return "price_ttc_eur_kwh"

        # Check if pricing metadata is available
        pricing_metadata = self.coordinator.data.get("pricing_metadata", {})

        if pricing_metadata.get("enabled"):
            display = pricing_metadata.get("display", "TTC")
            if display == "TTC":
                return "price_ttc_eur_kwh"
            else:
                return "price_ht_eur_kwh"

        # Try to auto-detect from first price data
        prices = self.coordinator.data.get("prices", [])
        if prices:
            first = prices[0]
            if "price_ttc_eur_kwh" in first:
                return "price_ttc_eur_kwh"
            elif "price_ht_eur_kwh" in first:
                return "price_ht_eur_kwh"
            elif "spot_price_eur_kwh" in first:
                return "spot_price_eur_kwh"
            elif "spot_price" in first:
                return "spot_price"

        # Default fallback
        return "price_ttc_eur_kwh"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {}

        if not self.coordinator.data:
            return attrs

        # Add pricing metadata
        pricing_metadata = self.coordinator.data.get("pricing_metadata", {})
        if pricing_metadata:
            attrs["pricing_enabled"] = pricing_metadata.get("enabled", False)
            attrs["turpe_option"] = pricing_metadata.get("turpe_option")
            attrs["profil"] = pricing_metadata.get("profil")
            attrs["display"] = pricing_metadata.get("display")
            attrs["tva_rate"] = pricing_metadata.get("tva_rate")
            attrs["accise_eur_kwh"] = pricing_metadata.get("accise_eur_kwh")

        # Add date and timezone
        attrs["date"] = self.coordinator.data.get("date")
        attrs["timezone"] = self.coordinator.data.get("timezone")
        attrs["last_updated"] = self.coordinator.data.get("last_updated")

        # Add all prices for all sensors
        prices = self.coordinator.data.get("prices", [])
        if prices:
            # Extract simplified price list (15-min slot and price)
            price_field = self._get_price_field()
            attrs["all_prices"] = [
                {
                    "slot": i,
                    "timestamp": p.get("timestamp"),
                    "price": p.get(price_field),
                    "spot_price": p.get("spot_price_eur_kwh"),
                }
                for i, p in enumerate(prices)
            ]
            attrs["prices_count"] = len(prices)

        # Add price details for current/next price sensors
        price_field = self._get_price_field()
        if self.sensor_type in (SENSOR_CURRENT_PRICE, SENSOR_NEXT_HOUR_PRICE):
            price_key = (
                "current_price"
                if self.sensor_type == SENSOR_CURRENT_PRICE
                else "next_price"
            )
            price_data = self.coordinator.data.get(price_key, {})

            if price_data:
                attrs["timestamp"] = price_data.get("timestamp")
                attrs["spot_price_eur_mwh"] = price_data.get("spot_price")
                attrs["spot_price_eur_kwh"] = price_data.get("spot_price_eur_kwh")
                attrs["turpe_eur_kwh"] = price_data.get("turpe_eur_kwh")
                attrs["accise_eur_kwh"] = price_data.get("accise_eur_kwh")
                attrs["price_ht_eur_kwh"] = price_data.get("price_ht_eur_kwh")
                if price_field == "price_ttc_eur_kwh":
                    attrs["price_ttc_eur_kwh"] = price_data.get("price_ttc_eur_kwh")

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )
