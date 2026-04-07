"""DataUpdateCoordinator for Sobry Energy."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

import aiohttp

from .const import (
    API_BASE_URL,
    API_ENDPOINT_RAW,
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
            # Récupérer les données du jour en cours
            return await self._fetch_today_data()

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error ({type(err).__name__}): {err}"
            ) from err

    async def _fetch_today_data(self) -> dict:
        """Fetch today's data."""
        from datetime import date, timedelta
        from statistics import mean, median

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
            "granularity": "quarter_hourly",
        }

        _LOGGER.debug("Fetching today's data from %s with params: %s", url, params)

        try:
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

            prices_data = data.get("data", [])
            _LOGGER.debug("API returned %d price points", len(prices_data))
            if prices_data:
                _LOGGER.debug("First price point: %s", prices_data[0])

            # Calculer les statistiques si non fournies par l'API
            statistics = data.get("statistics", {})
            if not statistics and prices_data:
                price_field = self._get_price_field_for_data(data)
                all_prices = [
                    p.get(price_field)
                    for p in prices_data
                    if p.get(price_field) is not None
                ]
                if all_prices:
                    statistics = {
                        "min": min(all_prices),
                        "max": max(all_prices),
                        "average": round(mean(all_prices), 6),
                        "median": round(median(all_prices), 6),
                    }

            # Adapt raw endpoint response to tomorrow endpoint format
            processed_data = {
                "date": today.isoformat(),
                "timezone": data.get("timezone", "Europe/Paris (CET)"),
                "count": data.get("count", 0),
                "statistics": statistics,
                "pricing_metadata": data.get("pricing_metadata", {}),
                "prices": prices_data,
                "current_price": None,
                "next_price": None,
                "last_updated": dt_util.now().isoformat(),
                "note": None,
            }

            # Find current and next quarter-hour prices
            now = dt_util.now()
            current_slot = (now.hour * 4) + (now.minute // 15)
            next_slot = (current_slot + 1) % 96

            for price_point in processed_data["prices"]:
                timestamp_str = price_point.get("timestamp", "")
                try:
                    timestamp = dt_util.parse_datetime(timestamp_str)
                    if timestamp:
                        slot = (timestamp.hour * 4) + (timestamp.minute // 15)
                        if slot == current_slot and timestamp.date() == now.date():
                            processed_data["current_price"] = price_point
                        if slot == next_slot:
                            if next_slot < current_slot:  # Day wrap
                                if timestamp.date() == now.date() + timedelta(days=1):
                                    processed_data["next_price"] = price_point
                            else:
                                processed_data["next_price"] = price_point
                except (ValueError, TypeError):
                    continue

            _LOGGER.debug(
                "Successfully fetched today's data with %d price points, stats: %s",
                len(processed_data.get("prices", [])),
                statistics,
            )

            return processed_data

        except Exception as err:
            _LOGGER.warning("Failed to fetch today's data: %s", err)
            raise UpdateFailed(f"Failed to fetch data: {err}") from err

    def _process_data(self, data: dict) -> dict:
        """Process API response data."""
        now = dt_util.now()
        current_slot = (now.hour * 4) + (now.minute // 15)
        next_slot = (current_slot + 1) % 96

        # Find current and next quarter-hour price
        prices = data.get("prices", [])
        current_price = None
        next_price = None

        for i, price_point in enumerate(prices):
            timestamp_str = price_point.get("timestamp", "")
            try:
                # Parse ISO timestamp
                timestamp = dt_util.parse_datetime(timestamp_str)
                if timestamp:
                    slot = (timestamp.hour * 4) + (timestamp.minute // 15)
                    # Current slot
                    if slot == current_slot and timestamp.date() == now.date():
                        current_price = price_point
                    # Next slot
                    if slot == next_slot:
                        # Handle day wrap
                        if next_slot < current_slot:
                            if timestamp.date() == now.date() + timedelta(days=1):
                                next_price = price_point
                        else:
                            next_price = price_point
            except (ValueError, TypeError):
                continue

        # If no current price found, use first available
        if not current_price and prices:
            current_price = prices[0]

        if not next_price and len(prices) > 1:
            next_price = prices[1]

        return {
            "date": data.get("date"),
            "timezone": data.get("timezone"),
            "count": data.get("count"),
            "statistics": data.get("statistics", {}),
            "pricing_metadata": data.get("pricing_metadata", {}),
            "prices": prices,
            "current_price": current_price,
            "next_price": next_price,
            "last_updated": now.isoformat(),
        }

    def _get_price_field_for_data(self, data: dict) -> str:
        """Determine which price field to use for statistics based on metadata."""
        pricing_metadata = data.get("pricing_metadata", {})

        if pricing_metadata.get("enabled"):
            display = pricing_metadata.get("display", self.display)
            if display == "TTC":
                return "price_ttc_eur_kwh"
            else:
                return "price_ht_eur_kwh"

        # Fallback: try to detect from first price data
        prices = data.get("data", [])
        if prices:
            first = prices[0]
            if "price_ttc_eur_kwh" in first:
                return "price_ttc_eur_kwh"
            elif "price_ht_eur_kwh" in first:
                return "price_ht_eur_kwh"
            elif "spot_price_eur_kwh" in first:
                return "spot_price_eur_kwh"

        # Default fallback
        return "price_ttc_eur_kwh"

    def get_price_for_slot(self, slot: int) -> dict | None:
        """Get price data for a specific 15-min slot (0-95)."""
        if not self.data:
            return None

        prices = self.data.get("prices", [])
        for price_point in prices:
            timestamp_str = price_point.get("timestamp", "")
            try:
                timestamp = dt_util.parse_datetime(timestamp_str)
                if timestamp:
                    price_slot = (timestamp.hour * 4) + (timestamp.minute // 15)
                    if price_slot == slot:
                        return price_point
            except (ValueError, TypeError):
                continue
        return None

    def get_price_for_hour(self, hour: int) -> dict | None:
        """Get price data for a specific hour (returns first 15-min slot of hour)."""
        return self.get_price_for_slot(hour * 4)

    @staticmethod
    async def async_fetch_history(
        hass: HomeAssistant,
        start_date: str,
        end_date: str,
        segment: str = "C5",
        turpe: str = "CU4",
        profil: str = "particulier",
        display: str = "TTC",
        granularity: str = "quarter_hourly",
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
            "prices": data.get("data", []),
            "statistics": data.get("statistics", {}),
            "date_range": data.get("date_range", {}),
            "timezone": data.get("timezone"),
        }
