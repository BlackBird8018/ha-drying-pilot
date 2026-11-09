# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Constants for DryingPilot."""

from datetime import timedelta

DOMAIN = "drying_pilot"

# Configuration (entities)
CONF_WEATHER = "weather_entity"
CONF_TEMPERATURE = "temperature_entity"
CONF_HUMIDITY = "humidity_entity"
CONF_PV_POWER = "pv_power_entity"
CONF_PV_PEAK = "pv_peak_w"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_NOTIFY_TYPES = "notify_types"

# Options (model parameters)
CONF_A = "a"
CONF_B = "b"
CONF_SUN_GAIN = "sun_gain"
CONF_MIN_RATE = "min_rate"
CONF_RAIN_MM = "rain_mm"
CONF_RAIN_PROBABILITY = "rain_probability"
CONF_REWET_RH = "rewet_rh"
CONF_REWET_RH_EXIT = "rewet_rh_exit"
CONF_DEW_MARGIN = "dew_margin"
CONF_CALIBRATION_SINCE = "calibration_since"
CONF_RESET_CALIBRATION = "reset_calibration"
CONF_SPIN_RPM = "spin_rpm"
CONF_PREDRY_MIN_HOURS = "predry_min_hours"
CONF_TARGET_LIGHT = "target_light"
CONF_TARGET_NORMAL = "target_normal"
CONF_TARGET_HEAVY = "target_heavy"

DEFAULT_PV_PEAK = 800.0

UPDATE_INTERVAL = timedelta(minutes=5)
FORECAST_INTERVAL = timedelta(minutes=15)

STORAGE_VERSION = 1

SERVICE_START = "start"
SERVICE_STOP = "stop"
SERVICE_FEEDBACK = "feedback"
ATTR_ANSWER = "answer"
ATTR_FEEDBACK = "feedback"
ATTR_LOCATION = "location"
ATTR_LAUNDRY_TYPE = "laundry_type"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

HUMID_MIN_DURATION = timedelta(minutes=30)
FEEDBACK_SNOOZE = timedelta(hours=1)
