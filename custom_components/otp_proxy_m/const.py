"""Constants for the OTP Proxy M integration."""

DOMAIN = "otp_proxy_m"

CONF_UPSTREAM = "upstream"
DEFAULT_UPSTREAM = "https://otp.mobilites-m.fr/otp/routers/default"

# Real upstream origin, used for the Host header when forwarding requests.
UPSTREAM_HOST = "otp.mobilites-m.fr"

GRAPHQL_PATH = "/index/graphql"
INDEX_PATH = "/index"

REQUEST_TIMEOUT = 30

STATE_OK = "ok"
STATE_ERROR = "error"
STATE_DOWN = "down"
