# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap

ANY_CHARM = textwrap.dedent(
    """
import json
import logging
import ssl
import subprocess
from pathlib import Path
from typing import Any, Optional

from any_charm_base import AnyCharmBase
from certificate_transfer import CertificateAvailableEvent, CertificateTransferRequires
from ldap3 import AUTO_BIND_NO_TLS, SUBTREE, Connection, Server, Tls
from ldap_interface_lib import LdapReadyEvent, LdapRequirer

logger = logging.getLogger(__name__)


class AnyCharm(AnyCharmBase):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.ldap_requirer = LdapRequirer(
            self,
            relation_name="ldap",
        )
        self.framework.observe(
            self.ldap_requirer.on.ldap_ready,
            self._on_ldap_ready,
        )
        self.certificate_transfer = CertificateTransferRequires(
            self,
            relationship_name="send-ca-cert",
        )
        self.framework.observe(
            self.certificate_transfer.on.certificate_available,
            self._on_certificate_available,
        )

    def _on_ldap_ready(self, event: LdapReadyEvent) -> None:
        ldap_data = self.ldap_requirer.consume_ldap_relation_data(
            relation=event.relation,
        )

        if not (peer := self.model.get_relation("peer-any")):
            logger.error("The peer relation is not ready yet")
            return

        peer.data[self.app].update({**ldap_data.model_dump(), **{"bind_password": ldap_data.bind_password}})

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        tls_cert_dir = Path("/usr/local/share/ca-certificates/")
        logger.info("Writing TLS certificate chain to directory `%s`", tls_cert_dir)

        tls_cert_dir.mkdir(mode=0o644, exist_ok=True)
        for idx, cert in enumerate(event.chain):
            (tls_cert_dir / f"cert-{idx}.crt").write_text(cert)

        logger.info("Updating TLS certificates with `update-ca-certificates`")
        try:
            subprocess.check_output(
                ["update-ca-certificates"],
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error("TLS certificate update failed: %s", e.stderr)

    def starttls_operation(self, cn: str = "hackers") -> Optional[dict[str, str]]:
        if not (peer := self.model.get_relation("peer-any")):
            logger.error("The peer integration is not ready yet")
            return None

        ldap_data = peer.data[self.app]
        ldap_uri = json.loads(ldap_data["urls"])[0]
        base_dn = ldap_data["base_dn"]
        bind_dn = ldap_data["bind_dn"]
        bind_password = ldap_data["bind_password"]

        ldap_host, ldap_port = ldap_uri.rsplit(sep=":", maxsplit=1)
        tls = Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(host=ldap_host, port=int(ldap_port), use_ssl=False, tls=tls)
        conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=AUTO_BIND_NO_TLS)
        conn.start_tls()

        conn.search(base_dn, f"(cn={cn})", search_scope=SUBTREE)
        entries = conn.response

        if not (entries := conn.response):
            logger.error("Can't find user '%s", cn)
            return None

        return {"dn": entries[0]["dn"]}

    def ldaps_operation(self, cn: str = "hackers") -> Optional[dict[str, str]]:
        if not (peer := self.model.get_relation("peer-any")):
            logger.error("The peer integration is not ready yet")
            return None

        ldap_data = peer.data[self.app]
        ldap_uri = json.loads(ldap_data["ldaps_urls"])[0]
        base_dn = ldap_data["base_dn"]
        bind_dn = ldap_data["bind_dn"]
        bind_password = ldap_data["bind_password"]

        ldap_host, ldap_port = ldap_uri.rsplit(sep=":", maxsplit=1)
        tls = Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLSv1_2)
        server = Server(host=ldap_host, port=int(ldap_port), use_ssl=True, tls=tls)
        conn = Connection(server, user=bind_dn, password=bind_password)

        conn.bind()
        conn.search(base_dn, f"(cn={cn})", search_scope=SUBTREE)
        entries = conn.response

        if not (entries := conn.response):
            logger.error("Can't find user '%s", cn)
            return None

        return {"dn": entries[0]["dn"]}
"""
)
