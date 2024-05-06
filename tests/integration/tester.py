# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import textwrap

ANY_CHARM = textwrap.dedent(
    """
from typing import Any

from any_charm_base import AnyCharmBase
from certificate_transfer import CertificateAvailableEvent, CertificateTransferRequires
from ldap import (
    LdapReadyEvent,
    LdapRequirer,
)


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
            event.relation.id,
        )

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        pass
"""
)
