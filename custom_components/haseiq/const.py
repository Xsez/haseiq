"""Constants for the Hase iQ integration."""

DOMAIN = "haseiq"
MANUFACTURER = "Hase"

# Config entry data
CONF_GENERATION = "generation"
CONF_OVEN_ID = "oven_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_KEEPALIVE_HELD = "keepalive_held"
CONF_SHARE_LINK = "share_link"

GEN1 = 1
GEN2 = 2

# Phase code → translation key. The two generations use different phase sets.
PHASES_GEN1: dict[int, str] = {
    0: "off",
    1: "heating_up",
    2: "burning",
    3: "add_wood",
    4: "dont_add_wood",
}
PHASES_GEN2: dict[int, str] = {
    0: "off",
    1: "kindling",
    2: "burning",
    3: "add_wood",
    4: "heating_up",
    5: "residual_heat",
    6: "dont_add_wood",
    7: "error",
}
GEN2_PHASE_ERROR = 7
