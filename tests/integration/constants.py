# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import re
from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
GLAUTH_APP = METADATA["name"]
GLAUTH_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
TRAEFIK_CHARM = "traefik-k8s"
CERTIFICATE_PROVIDER_APP = "self-signed-certificates"
DB_APP = "postgresql-k8s"
GLAUTH_PROXY = "ldap-proxy"
GLAUTH_CLIENT_APP = "any-charm"
INGRESS_APP = "ingress"
LDAPS_INGRESS_APP = "ldaps-ingress"

JUJU_SECRET_ID_REGEX = re.compile(r"secret:(?://[a-f0-9-]+/)?(?P<secret_id>[a-zA-Z0-9]+)")
INGRESS_URL_REGEX = re.compile(r"url:\s*(?P<ingress_url>\d{1,3}(?:\.\d{1,3}){3}:\d+)")
