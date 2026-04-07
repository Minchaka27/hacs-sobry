"""The Sobry Energy integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    CONF_DISPLAY,
    CONF_PROFIL,
    CONF_SEGMENT,
    CONF_TURPE,
    DEFAULT_DISPLAY,
    DEFAULT_PROFIL,
    DEFAULT_SEGMENT,
    DEFAULT_TURPE,
    DOMAIN,
    VALID_DISPLAYS,
    VALID_PROFILS,
    VALID_SEGMENTS,
    VALID_TURPE_C4,
    VALID_TURPE_C5,
)
from .coordinator import SobryDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_GET_PRICE_HISTORY = "get_price_history"
SERVICE_GET_ALL_PRICES = "get_all_prices"

SERVICE_SCHEMA_GET_PRICE_HISTORY = vol.Schema(
    {
        vol.Required("start_date"): cv.string,
        vol.Required("end_date"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional(CONF_SEGMENT): vol.In(VALID_SEGMENTS),
        vol.Optional(CONF_TURPE): cv.string,
        vol.Optional(CONF_PROFIL): vol.In(VALID_PROFILS),
        vol.Optional(CONF_DISPLAY): vol.In(VALID_DISPLAYS),
        vol.Optional("granularity", default="hourly"): vol.In(["hourly", "daily"]),
    }
)

SERVICE_SCHEMA_GET_ALL_PRICES = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional(CONF_SEGMENT): vol.In(VALID_SEGMENTS),
        vol.Optional(CONF_TURPE): cv.string,
        vol.Optional(CONF_PROFIL): vol.In(VALID_PROFILS),
        vol.Optional(CONF_DISPLAY): vol.In(VALID_DISPLAYS),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sobry Energy from a config entry."""
    _LOGGER.debug("Setting up Sobry Energy for entry %s", entry.entry_id)

    coordinator = SobryDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register services if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_GET_PRICE_HISTORY):

        async def async_get_price_history(call: ServiceCall) -> dict[str, Any]:
            """Handle get price history service call."""
            return await _async_handle_get_price_history(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_PRICE_HISTORY,
            async_get_price_history,
            schema=SERVICE_SCHEMA_GET_PRICE_HISTORY,
            supports_response=True,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_ALL_PRICES):

        async def async_get_all_prices(call: ServiceCall) -> dict[str, Any]:
            """Handle get all prices service call."""
            return await _async_handle_get_all_prices(hass, call)

        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_ALL_PRICES,
            async_get_all_prices,
            schema=SERVICE_SCHEMA_GET_ALL_PRICES,
            supports_response=True,
        )

    return True


async def _async_get_config_from_call(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[SobryDataUpdateCoordinator | None, str, str, str, str]:
    """Get coordinator and config from service call."""
    coordinator: SobryDataUpdateCoordinator | None = None

    # Try to get coordinator from config_entry_id
    config_entry_id = call.data.get("config_entry_id")
    if config_entry_id:
        coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)

    # Fallback to first available coordinator
    if not coordinator:
        domain_data = hass.data.get(DOMAIN, {})
        if domain_data:
            coordinator = next(iter(domain_data.values()))

    # Get parameters from service call or use defaults/coordinator values
    segment = call.data.get(CONF_SEGMENT)
    turpe = call.data.get(CONF_TURPE)
    profil = call.data.get(CONF_PROFIL)
    display = call.data.get(CONF_DISPLAY)

    if coordinator and not segment:
        segment = coordinator.segment
        turpe = coordinator.turpe
        profil = coordinator.profil
        display = coordinator.display

    # Apply defaults if still not set
    segment = segment or DEFAULT_SEGMENT
    turpe = turpe or DEFAULT_TURPE
    profil = profil or DEFAULT_PROFIL
    display = display or DEFAULT_DISPLAY

    # Enforce C4 rules
    if segment == "C4":
        profil = "pro"
        display = "HT"

    # Validate TURPE for segment
    valid_turpe = VALID_TURPE_C5 if segment == "C5" else VALID_TURPE_C4
    if turpe not in valid_turpe:
        turpe = valid_turpe[0] if valid_turpe else DEFAULT_TURPE

    return coordinator, segment, turpe, profil, display


async def _async_handle_get_all_prices(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Handle get all prices service call - returns current day prices."""
    coordinator, segment, turpe, profil, display = await _async_get_config_from_call(
        hass, call
    )

    _LOGGER.debug(
        "Fetching all prices for today (segment=%s, turpe=%s, profil=%s, display=%s)",
        segment,
        turpe,
        profil,
        display,
    )

    try:
        from datetime import date

        today = date.today().isoformat()
        tomorrow = (date.today()).isoformat()

        # Fetch today's prices via the raw endpoint
        prices_data = await SobryDataUpdateCoordinator.async_fetch_history(
            hass,
            start_date=today,
            end_date=tomorrow,
            segment=segment,
            turpe=turpe,
            profil=profil,
            display=display,
            granularity="hourly",
        )

        prices = prices_data.get("prices", [])

        # Build simplified price list with hour and all price components
        price_list = []
        for price_point in prices:
            price_entry = {
                "hour": price_point.get("hour"),
                "timestamp": price_point.get("timestamp"),
                "price_eur_kwh": price_point.get("price_ttc_eur_kwh")
                if display == "TTC"
                else price_point.get("price_ht_eur_kwh"),
                "price_ht_eur_kwh": price_point.get("price_ht_eur_kwh"),
                "price_ttc_eur_kwh": price_point.get("price_ttc_eur_kwh"),
                "spot_price_eur_kwh": price_point.get("spot_price_eur_kwh"),
                "turpe_eur_kwh": price_point.get("turpe_eur_kwh"),
                "accise_eur_kwh": price_point.get("accise_eur_kwh"),
            }
            price_list.append(price_entry)

        return {
            "success": True,
            "date": prices_data.get("date_range", {}).get("start"),
            "segment": segment,
            "turpe": turpe,
            "profil": profil,
            "display": display,
            "count": len(price_list),
            "prices": price_list,
            "statistics": prices_data.get("statistics", {}),
            "timezone": prices_data.get("timezone"),
        }
    except Exception as err:
        _LOGGER.error("Error fetching all prices: %s", err)
        return {
            "success": False,
            "error": str(err),
        }


async def _async_handle_get_price_history(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    """Handle get price history service call."""
    _, segment, turpe, profil, display = await _async_get_config_from_call(hass, call)

    start_date = call.data["start_date"]
    end_date = call.data["end_date"]
    granularity = call.data.get("granularity", "hourly")

    _LOGGER.debug(
        "Fetching price history from %s to %s (segment=%s, turpe=%s, profil=%s, display=%s)",
        start_date,
        end_date,
        segment,
        turpe,
        profil,
        display,
    )

    try:
        history_data = await SobryDataUpdateCoordinator.async_fetch_history(
            hass,
            start_date=start_date,
            end_date=end_date,
            segment=segment,
            turpe=turpe,
            profil=profil,
            display=display,
            granularity=granularity,
        )

        return {
            "success": True,
            "start_date": start_date,
            "end_date": end_date,
            "segment": segment,
            "turpe": turpe,
            "profil": profil,
            "display": display,
            "granularity": granularity,
            "count": history_data.get("count", 0),
            "prices": history_data.get("prices", []),
            "statistics": history_data.get("statistics", {}),
        }
    except Exception as err:
        _LOGGER.error("Error fetching price history: %s", err)
        return {
            "success": False,
            "error": str(err),
        }


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Sobry Energy entry %s", entry.entry_id)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
