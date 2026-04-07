"""DataUpdateCoordinator for Sobry Energy."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

import aiohttp

from .const import (
    API_BASE_URL,
    API_ENDPOINT_RAW,
    API_ENDPOINT_TOMORROW,
    API_TIMEOUT,
    CONF_DISPLAY,
    CONF_PROFIL,
    CONF_SEGMENT,
    CONF_TURPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class SobryDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Sobry API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.segment = entry.data.get(CONF_SEGMENT, "C5")
        self.turpe = entry.data.get(CONF_TURPE, "CU4")
        self.profil = entry.data.get(CONF_PROFIL, "particulier")
        self.display = entry.data.get(CONF_DISPLAY, "TTC")

        # For C4, enforce profil=pro and display=HT
        if self.segment == "C4":
            self.profil = "pro"
            self.display = "HT"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from Sobry API."""
        try:
            url = f"{API_BASE_URL}{API_ENDPOINT_TOMORROW}"
            params = {}

            # Add pricing parameters
            if self.segment:
                params["segment"] = self.segment
            if self.turpe:
                params["turpe"] = self.turpe
            if self.profil:
                params["profil"] = self.profil
            if self.display:
                params["display"] = self.display

            _LOGGER.debug("Fetching data from %s with params: %s", url, params)

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        raise UpdateFailed("Rate limit exceeded (100 req/min)")
                    elif response.status == 404:
                        raise UpdateFailed("No data available for the requested period")
                    elif response.status >= 400:
                        text = await response.text()
                        # Check if it's a "data not available yet" error (before ~13h)
                        if (
                            "pas disponible" in text.lower()
                            or "not available" in text.lower()
                        ):
                            _LOGGER.debug(
                                "Tomorrow data not available yet (before ~13h), trying today's data"
                            )
                            return await self._fetch_today_data()
                        raise UpdateFailed(f"API error {response.status}: {text}")

                    data = await response.json()

            if not data.get("success"):
                raise UpdateFailed("API returned unsuccessful response")

            # Process and enrich data
            processed_data = self._process_data(data)

            _LOGGER.debug(
                "Successfully fetched data with %d price points",
                len(processed_data.get("prices", [])),
            )

            return processed_data

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error ({type(err).__name__}): {err}"
            ) from err

    async def _fetch_today_data(self) -> dict:
        """Fetch today's data as fallback when tomorrow data is not available."""
        from datetime import date, timedelta

        today = date.today()
        tomorrow = today + timedelta(days=1)
        url = f"{API_BASE_URL}{API_ENDPOINT_RAW}"
        params: dict[str, str] = {
            "start": today.isoformat(),
            "end": tomorrow.isoformat(),
            "segment": self.segment,
            "turpe": self.turpe,
            "profil": self.profil,
            "display": self.display,
            "granularity": "hourly",
        }

        _LOGGER.debug("Fetching today's data from %s with params: %s", url, params)

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as session:
                async with session.get(url, params=params) as response:
                    if response.status >= 400:
                        text = await response.text()
                        raise UpdateFailed(f"API error {response.status}: {text}")

                    data = await response.json()

            if not data.get("success"):
                raise UpdateFailed("API returned unsuccessful response")

            # Adapt raw endpoint response to tomorrow endpoint format
            processed_data = {
                "date": today,
                "timezone": data.get("timezone", "Europe/Paris (CET)"),
                "count": data.get("count", 0),
                "statistics": data.get("statistics", {}),
                "pricing_metadata": data.get("pricing_metadata", {}),
                "prices": data.get("data", []),
                "current_price": None,
                "next_hour_price": None,
                "last_updated": dt_util.now().isoformat(),
                "note": "Données du jour (demain non disponible avant ~13h)",
            }

            # Find current and next hour prices
            now = dt_util.now()
            for price_point in processed_data["prices"]:
                timestamp_str = price_point.get("timestamp", "")
                try:
                    timestamp = dt_util.parse_datetime(timestamp_str)
                    if timestamp:
                        if (
                            timestamp.hour == now.hour
                            and timestamp.date() == now.date()
                        ):
                            processed_data["current_price"] = price_point
                        if timestamp.hour == (now.hour + 1) % 24:
                            if timestamp.hour == 0:
                                if timestamp.date() == now.date() + timedelta(days=1):
                                    processed_data["next_hour_price"] = price_point
                            else:
                                processed_data["next_hour_price"] = price_point
                except (ValueError, TypeError):
                    continue

            _LOGGER.debug(
                "Successfully fetched today's data with %d price points",
                len(processed_data.get("prices", [])),
            )

            return processed_data

        except Exception as err:
            _LOGGER.warning("Failed to fetch today's data: %s", err)
            # Return empty data structure to allow configuration to proceed
            return self._get_empty_data()

    def _get_empty_data(self) -> dict:
        """Return empty data structure when no data is available."""
        now = dt_util.now()
        return {
            "date": now.date().isoformat(),
            "timezone": "Europe/Paris (CET)",
            "count": 0,
            "statistics": {},
            "pricing_metadata": {},
            "prices": [],
            "current_price": None,
            "next_hour_price": None,
            "last_updated": now.isoformat(),
            "note": "Données temporairement indisponibles (disponibles à partir de ~13h)",
        }

    def _process_data(self, data: dict) -> dict:
        """Process API response data."""
        now = dt_util.now()

        # Find current price
        prices = data.get("prices", [])
        current_price = None
        next_hour_price = None

        for i, price_point in enumerate(prices):
            timestamp_str = price_point.get("timestamp", "")
            try:
                # Parse ISO timestamp
                timestamp = dt_util.parse_datetime(timestamp_str)
                if timestamp:
                    # Current hour
                    if timestamp.hour == now.hour and timestamp.date() == now.date():
                        current_price = price_point
                    # Next hour
                    if timestamp.hour == (now.hour + 1) % 24:
                        # Handle day wrap
                        if timestamp.hour == 0:
                            if timestamp.date() == now.date() + timedelta(days=1):
                                next_hour_price = price_point
                        else:
                            next_hour_price = price_point
            except (ValueError, TypeError):
                continue

        # If no current price found, use first available
        if not current_price and prices:
            current_price = prices[0]

        if not next_hour_price and len(prices) > 1:
            next_hour_price = prices[1]

        return {
            "date": data.get("date"),
            "timezone": data.get("timezone"),
            "count": data.get("count"),
            "statistics": data.get("statistics", {}),
            "pricing_metadata": data.get("pricing_metadata", {}),
            "prices": prices,
            "current_price": current_price,
            "next_hour_price": next_hour_price,
            "last_updated": now.isoformat(),
        }

    def get_price_for_hour(self, hour: int) -> dict | None:
        """Get price data for a specific hour."""
        if not self.data:
            return None

        prices = self.data.get("prices", [])
        for price_point in prices:
            timestamp_str = price_point.get("timestamp", "")
            try:
                timestamp = dt_util.parse_datetime(timestamp_str)
                if timestamp and timestamp.hour == hour:
                    return price_point
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    async def async_fetch_history(
        hass: HomeAssistant,
        start_date: str,
        end_date: str,
        segment: str = "C5",
        turpe: str = "CU4",
        profil: str = "particulier",
        display: str = "TTC",
        granularity: str = "hourly",
    ) -> dict:
        """Fetch historical price data from Sobry API.

        This is a static method that can be called without an instance.
        """
        url = f"{API_BASE_URL}{API_ENDPOINT_RAW}"
        params: dict[str, str] = {
            "start": start_date,
            "end": end_date,
            "segment": segment,
            "turpe": turpe,
            "profil": profil,
            "display": display,
            "granularity": granularity,
        }

        _LOGGER.debug("Fetching history from %s with params: %s", url, params)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as response:
                if response.status == 429:
                    raise UpdateFailed("Rate limit exceeded (100 req/min)")
                elif response.status == 404:
                    raise UpdateFailed("No data available for the requested period")
                elif response.status >= 400:
                    text = await response.text()
                    raise UpdateFailed(f"API error {response.status}: {text}")

                data = await response.json()

        if not data.get("success"):
            raise UpdateFailed("API returned unsuccessful response")

        return {
            "count": data.get("count", 0),
            "prices": data.get("prices", []),
            "statistics": data.get("statistics", {}),
            "date_range": data.get("date_range", {}),
            "timezone": data.get("timezone"),
        }
