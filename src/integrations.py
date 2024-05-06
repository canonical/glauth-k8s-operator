# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import logging
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from secrets import token_bytes
from typing import Optional

from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateTransferProvides,
)
from charms.glauth_k8s.v0.ldap import LdapProviderBaseData, LdapProviderData
from charms.glauth_utils.v0.glauth_auxiliary import AuxiliaryData
from charms.observability_libs.v1.cert_handler import CertHandler
from configs import DatabaseConfig
from constants import (
    CERTIFICATE_FILE,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DEFAULT_GID,
    DEFAULT_UID,
    GLAUTH_LDAP_PORT,
    SERVER_CA_CERT,
    SERVER_CERT,
    SERVER_KEY,
)
from database import Capability, Group, Operation, User
from exceptions import CertificatesError
from ops.charm import CharmBase
from ops.pebble import PathError
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BindAccount:
    cn: str
    ou: str
    password: str


def _create_bind_account(dsn: str, user_name: str, group_name: str) -> BindAccount:
    with Operation(dsn) as op:
        if not op.select(Group, Group.name == group_name):
            group = Group(name=group_name, gid_number=DEFAULT_GID)
            op.add(group)

        if not (user := op.select(User, User.name == user_name)):
            new_password = hashlib.sha256(token_bytes()).hexdigest()
            user = User(
                name=user_name,
                uid_number=DEFAULT_UID,
                gid_number=DEFAULT_GID,
                password_sha256=new_password,
            )
            op.add(user)
        password = user.password_bcrypt or user.password_sha256

        if not op.select(Capability, Capability.user_id == DEFAULT_UID):
            capability = Capability(user_id=DEFAULT_UID)
            op.add(capability)

    return BindAccount(user_name, group_name, password)


class LdapIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._bind_account: Optional[BindAccount] = None

    def load_bind_account(self, user: str, group: str) -> None:
        database_config = DatabaseConfig.load(self._charm.database_requirer)
        self._bind_account = _create_bind_account(database_config.dsn, user, group)

    @property
    def ldap_url(self) -> str:
        return f"ldap://{self._charm.config.get('hostname')}:{GLAUTH_LDAP_PORT}"

    @property
    def base_dn(self) -> str:
        return self._charm.config.get("base_dn")

    @property
    def starttls_enabled(self) -> bool:
        return self._charm.config.get("starttls_enabled", True)

    @property
    def provider_base_data(self) -> LdapProviderBaseData:
        return LdapProviderBaseData(
            url=self.ldap_url,
            base_dn=self.base_dn,
            starttls=self.starttls_enabled,
        )

    @property
    def provider_data(self) -> Optional[LdapProviderData]:
        if not self._bind_account:
            return None

        return LdapProviderData(
            url=self.ldap_url,
            base_dn=self.base_dn,
            bind_dn=f"cn={self._bind_account.cn},ou={self._bind_account.ou},{self.base_dn}",
            bind_password_secret=self._bind_account.password,
            auth_method="simple",
            starttls=self.starttls_enabled,
        )


class AuxiliaryIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm

    @property
    def auxiliary_data(self) -> AuxiliaryData:
        database_config = DatabaseConfig.load(self._charm.database_requirer)

        return AuxiliaryData(
            database=database_config.database,
            endpoint=database_config.endpoint,
            username=database_config.username,
            password=database_config.password,
        )


@dataclass
class CertificateData:
    ca_cert: Optional[str] = None
    ca_chain: Optional[str] = None
    cert: Optional[str] = None


class CertificatesIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = charm._container

        hostname = charm.config.get("hostname")
        self.cert_handler = CertHandler(
            charm,
            key="glauth-server-cert",
            cert_subject=hostname,
            sans=[
                hostname,
                f"{charm.app.name}.{charm.model.name}.svc.cluster.local",
            ],
        )

    @property
    def _ca_cert(self) -> Optional[str]:
        return self.cert_handler.ca_cert

    @property
    def _server_key(self) -> Optional[str]:
        return self.cert_handler.private_key

    @property
    def _server_cert(self) -> Optional[str]:
        return self.cert_handler.server_cert

    @property
    def _ca_chain(self) -> Optional[str]:
        return self.cert_handler.chain

    @property
    def cert_data(self) -> CertificateData:
        return CertificateData(
            ca_cert=self._ca_cert,
            ca_chain=self._ca_chain,
            cert=self._server_cert,
        )

    def update_certificates(self) -> None:
        if not self.cert_handler.enabled:
            logger.debug("The certificates integration is not ready.")
            self._remove_certificates()
            return

        if not self.certs_ready():
            logger.debug("The certificates data is not ready.")
            self._remove_certificates()
            return

        self._prepare_certificates()
        self._push_certificates()

    def certs_ready(self) -> bool:
        return all((self._ca_cert, self._ca_chain, self._server_key, self._server_cert))

    def _prepare_certificates(self) -> None:
        SERVER_CA_CERT.write_text(self._ca_cert)  # type: ignore[arg-type]
        SERVER_KEY.write_text(self._server_key)  # type: ignore[arg-type]
        SERVER_CERT.write_text(self._server_cert)  # type: ignore[arg-type]

        try:
            for attempt in Retrying(
                wait=wait_fixed(3),
                stop=stop_after_attempt(3),
                retry=retry_if_exception_type(subprocess.CalledProcessError),
                reraise=True,
            ):
                with attempt:
                    subprocess.run(
                        ["update-ca-certificates", "--fresh"],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
        except subprocess.CalledProcessError as e:
            logger.error(f"{e.stderr}")
            raise CertificatesError("Update the TLS certificates failed.")

    def _push_certificates(self) -> None:
        self._container.push(CERTIFICATE_FILE, CERTIFICATE_FILE.read_text(), make_dirs=True)
        self._container.push(SERVER_CA_CERT, self._ca_cert, make_dirs=True)
        self._container.push(SERVER_KEY, self._server_key, make_dirs=True)
        self._container.push(SERVER_CERT, self._server_cert, make_dirs=True)

    def _remove_certificates(self) -> None:
        for file in (CERTIFICATE_FILE, SERVER_CA_CERT, SERVER_KEY, SERVER_CERT):
            with suppress(PathError):
                self._container.remove_path(file)


class CertificatesTransferIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._certs_transfer_provider = CertificateTransferProvides(
            charm, relationship_name=CERTIFICATES_TRANSFER_INTEGRATION_NAME
        )

    def transfer_certificates(
        self, /, data: CertificateData, relation_id: Optional[int] = None
    ) -> None:
        if not (
            relations := self._charm.model.relations.get(CERTIFICATES_TRANSFER_INTEGRATION_NAME)
        ):
            return

        if relation_id is not None:
            relations = [relation for relation in relations if relation.id == relation_id]

        ca_cert, ca_chain, certificate = data.ca_cert, data.ca_chain, data.cert
        if not all((ca_cert, ca_chain, certificate)):
            for relation in relations:
                self._certs_transfer_provider.remove_certificate(relation_id=relation.id)
            return

        for relation in relations:
            self._certs_transfer_provider.set_certificate(
                ca=data.ca_cert,  # type: ignore[arg-type]
                chain=data.ca_chain,  # type: ignore[arg-type]
                certificate=data.cert,  # type: ignore[arg-type]
                relation_id=relation.id,
            )
