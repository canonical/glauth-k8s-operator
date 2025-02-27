# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path, PurePath
from string import Template

LDAP_CLIENT_INTEGRATION_NAME = "ldap-client"
DATABASE_INTEGRATION_NAME = "pg-database"
INGRESS_PER_UNIT_INTEGRATION_NAME = "ingress"
LDAPS_INGRESS_PER_UNIT_INTEGRATION_NAME = "ldaps-ingress"
LOKI_API_PUSH_INTEGRATION_NAME = "logging"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"
CERTIFICATES_INTEGRATION_NAME = "certificates"
CERTIFICATES_TRANSFER_INTEGRATION_NAME = "send-ca-cert"

GLAUTH_CONFIG_DIR = PurePath("/etc/config")
GLAUTH_CONFIG_FILE = GLAUTH_CONFIG_DIR / "glauth.cfg"
GLAUTH_COMMANDS = f"glauth -c {GLAUTH_CONFIG_FILE}"
GLAUTH_LDAP_PORT = 3893
GLAUTH_LDAPS_PORT = 3894

WORKLOAD_CONTAINER = "glauth"
WORKLOAD_SERVICE = "glauth"

DEFAULT_UID = 5001
DEFAULT_GID = 5501
POSTGRESQL_DSN_TEMPLATE = Template("postgresql+psycopg://$username:$password@$endpoint/$database")

CERTIFICATE_FILE = Path("/etc/ssl/certs/ca-certificates.crt")
PRIVATE_KEY_DIR = Path("/etc/ssl/private")
LOCAL_CA_CERTS_DIR = Path("/usr/local/share/ca-certificates")

SERVER_CA_CERT = LOCAL_CA_CERTS_DIR / "glauth-ca.crt"
SERVER_KEY = PRIVATE_KEY_DIR / "glauth-server.key"
SERVER_CERT = LOCAL_CA_CERTS_DIR / "glauth-server.crt"
