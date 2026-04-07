"""Config flow for Sobry Energy integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

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

_LOGGER = logging.getLogger(__name__)


def _get_turpe_options(segment: str) -> list[str]:
    """Get valid TURPE options for a segment."""
    return VALID_TURPE_C5 if segment == "C5" else VALID_TURPE_C4


class SobryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sobry Energy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            segment = user_input.get(CONF_SEGMENT, DEFAULT_SEGMENT)

            # Store segment and proceed to TURPE selection
            self._data = {CONF_SEGMENT: segment}
            return await self.async_step_turpe()

        # Build schema based on current segment selection
        schema = vol.Schema(
            {
                vol.Required(CONF_SEGMENT, default=DEFAULT_SEGMENT): vol.In(
                    VALID_SEGMENTS
                ),
            }
        )

        # Show initial form
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_turpe(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle TURPE selection step."""
        errors: dict[str, str] = {}

        # Get stored data from previous step
        segment = self._get_data().get(CONF_SEGMENT, DEFAULT_SEGMENT)

        if user_input is not None:
            turpe = user_input.get(CONF_TURPE, DEFAULT_TURPE)

            # Store and proceed to next step
            self._data = {**self._get_data(), CONF_TURPE: turpe}

            # For C4, skip profil/display selection (forced values)
            if segment == "C4":
                return await self._create_entry()

            return await self.async_step_profil()

        valid_turpe = _get_turpe_options(segment)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TURPE, default=valid_turpe[0] if valid_turpe else DEFAULT_TURPE
                ): vol.In(valid_turpe),
            }
        )

        return self.async_show_form(
            step_id="turpe",
            data_schema=schema,
            errors=errors,
            description_placeholders={"segment": segment},
        )

    async def async_step_profil(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle profil selection step (C5 only)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data = {**self._get_data(), **user_input}
            return await self.async_step_display()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROFIL, default=DEFAULT_PROFIL): vol.In(
                    VALID_PROFILS
                ),
            }
        )

        return self.async_show_form(
            step_id="profil",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_display(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle display selection step (C5 only)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data = {**self._get_data(), **user_input}
            return await self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_DISPLAY, default=DEFAULT_DISPLAY): vol.In(
                    VALID_DISPLAYS
                ),
            }
        )

        return self.async_show_form(
            step_id="display",
            data_schema=schema,
            errors=errors,
        )

    def _get_data(self) -> dict[str, Any]:
        """Get data stored during config flow."""
        if not hasattr(self, "_data"):
            self._data = {}
        return self._data

    async def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        data = self._get_data()
        segment = data.get(CONF_SEGMENT, DEFAULT_SEGMENT)
        turpe = data.get(CONF_TURPE, DEFAULT_TURPE)
        profil = data.get(CONF_PROFIL, DEFAULT_PROFIL if segment == "C5" else "pro")
        display = data.get(CONF_DISPLAY, DEFAULT_DISPLAY if segment == "C5" else "HT")

        # For C4, enforce profil=pro and display=HT
        if segment == "C4":
            profil = "pro"
            display = "HT"
            data[CONF_PROFIL] = profil
            data[CONF_DISPLAY] = display

        await self.async_set_unique_id(f"sobry_{segment}_{turpe}_{profil}_{display}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Sobry {segment} ({turpe})",
            data=data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SobryOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SobryOptionsFlowHandler(config_entry)


class SobryOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Sobry Energy."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        segment = self.config_entry.data.get(CONF_SEGMENT, DEFAULT_SEGMENT)

        if user_input is not None:
            # Validate TURPE for segment
            turpe = user_input.get(CONF_TURPE, DEFAULT_TURPE)
            valid_turpe = _get_turpe_options(segment)

            if turpe not in valid_turpe:
                errors[CONF_TURPE] = "invalid_turpe_for_segment"
            elif not errors:
                # For C4, enforce profil=pro and display=HT
                if segment == "C4":
                    user_input[CONF_PROFIL] = "pro"
                    user_input[CONF_DISPLAY] = "HT"

                return self.async_create_entry(title="", data=user_input)

        # Build options schema
        valid_turpe = _get_turpe_options(segment)
        current_turpe = self.config_entry.data.get(CONF_TURPE, DEFAULT_TURPE)
        current_profil = self.config_entry.data.get(CONF_PROFIL, DEFAULT_PROFIL)
        current_display = self.config_entry.data.get(CONF_DISPLAY, DEFAULT_DISPLAY)

        schema_parts = {
            vol.Required(CONF_TURPE, default=current_turpe): vol.In(valid_turpe),
        }

        # Only show profil/display for C5
        if segment == "C5":
            schema_parts[vol.Required(CONF_PROFIL, default=current_profil)] = vol.In(
                VALID_PROFILS
            )
            schema_parts[vol.Required(CONF_DISPLAY, default=current_display)] = vol.In(
                VALID_DISPLAYS
            )

        schema = vol.Schema(schema_parts)

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"segment": segment},
        )
