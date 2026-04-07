"""Constants for the Sobry Energy integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "sobry"
DEFAULT_NAME: Final = "Sobry Energy"

# API Configuration
API_BASE_URL: Final = "https://api.sobry.co"
API_ENDPOINT_TOMORROW: Final = "/api/prices/tomorrow"
API_ENDPOINT_RAW: Final = "/api/prices/raw"
API_TIMEOUT: Final = 30

# Update interval (API day-ahead is published around 13:00 CET)
DEFAULT_SCAN_INTERVAL: Final = timedelta(hours=1)
MIN_SCAN_INTERVAL: Final = timedelta(minutes=1)

# Rate limiting (100 requests per minute)
RATE_LIMIT_PER_MINUTE: Final = 100

# Configuration keys
CONF_SEGMENT: Final = "segment"
CONF_TURPE: Final = "turpe"
CONF_PROFIL: Final = "profil"
CONF_DISPLAY: Final = "display"

# Default configuration values
DEFAULT_SEGMENT: Final = "C5"
DEFAULT_TURPE: Final = "CU4"
DEFAULT_PROFIL: Final = "particulier"
DEFAULT_DISPLAY: Final = "TTC"

# Valid configuration options
VALID_SEGMENTS: Final = ["C5", "C4"]
VALID_TURPE_C5: Final = ["CU", "CU4", "MU4", "MUDT", "LU"]
VALID_TURPE_C4: Final = ["CU", "LU"]
VALID_PROFILS: Final = ["particulier", "pro"]
VALID_DISPLAYS: Final = ["HT", "TTC"]

# Sensor types
SENSOR_CURRENT_PRICE: Final = "current_price"
SENSOR_MIN_PRICE: Final = "min_price"
SENSOR_MAX_PRICE: Final = "max_price"
SENSOR_AVG_PRICE: Final = "avg_price"
SENSOR_MEDIAN_PRICE: Final = "median_price"
SENSOR_NEXT_HOUR_PRICE: Final = "next_hour_price"
SENSOR_ALL_PRICES: Final = "all_prices"

SENSOR_TYPES: Final = [
    SENSOR_CURRENT_PRICE,
    SENSOR_MIN_PRICE,
    SENSOR_MAX_PRICE,
    SENSOR_AVG_PRICE,
    SENSOR_MEDIAN_PRICE,
    SENSOR_NEXT_HOUR_PRICE,
    SENSOR_ALL_PRICES,
]
