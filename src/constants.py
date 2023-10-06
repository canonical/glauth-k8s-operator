# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import PurePath

DATABASE_INTEGRATION_NAME = "pg-database"
LOKI_API_PUSH_INTEGRATION_NAME = "logging"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"

GLAUTH_CONFIG_DIR = PurePath("/etc/config")
GLAUTH_CONFIG_FILE = GLAUTH_CONFIG_DIR / "glauth.cfg"
GLAUTH_COMMANDS = f"glauth -c {GLAUTH_CONFIG_FILE}"
GLAUTH_LDAP_PORT = 3893

LOG_DIR = PurePath("/var/log")
LOG_FILE = LOG_DIR / "glauth.log"

WORKLOAD_CONTAINER = "glauth"
WORKLOAD_SERVICE = "glauth"
