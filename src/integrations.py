# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import hashlib
import ipaddress
import logging
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from secrets import token_hex
from typing import List, Optional

from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateTransferProvides,
)
from charms.glauth_k8s.v0.ldap import LdapProviderBaseData, LdapProviderData
from charms.glauth_utils.v0.glauth_auxiliary import AuxiliaryData
from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    ProviderCertificate,
    TLSCertificatesRequiresV4,
)
from ops.charm import CharmBase
from ops.pebble import PathError
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from configs import DatabaseConfig, LdapServerConfig
from constants import (
    CERTIFICATE_FILE,
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DEFAULT_GID,
    DEFAULT_UID,
    GLAUTH_LDAP_PORT,
    GLAUTH_LDAPS_PORT,
    SERVER_CA_CERT,
    SERVER_CERT,
    SERVER_KEY,
)
from database import Capability, Group, Operation, User
from exceptions import CertificatesError

logger = logging.getLogger(__name__)


@dataclass
class BindAccount:
    cn: str
    ou: str
    password: Optional[str]


def _reset_account_password(dsn: str, user_name: str) -> str:
    password = token_hex()
    password_sha256 = hashlib.sha256(password.encode()).hexdigest()
    with Operation(dsn) as op:
        if not (user := op.select(User, User.name == user_name)):
            raise RuntimeError(f"No user '{user_name}' found")
        user.password_sha256 = password_sha256
        op.add(user)

    return password


def _create_bind_account(dsn: str, user_name: str, group_name: str) -> BindAccount:
    with Operation(dsn) as op:
        if not op.select(Group, Group.name == group_name):
            group = Group(name=group_name, gid_number=DEFAULT_GID)
            op.add(group)

        user = op.select(User, User.name == user_name)
        password = token_hex() if not user else ""
        if not user:
            user = User(
                name=user_name,
                uid_number=DEFAULT_UID,
                gid_number=DEFAULT_GID,
                password_sha256=hashlib.sha256(password.encode()).hexdigest(),
            )
            op.add(user)

        if not op.select(Capability, Capability.user_id == DEFAULT_UID):
            capability = Capability(user_id=DEFAULT_UID)
            op.add(capability)

    return BindAccount(user_name, group_name, password)


class LdapIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._bind_account: Optional[BindAccount] = None

    def load_bind_account(self, user: str, group: str, relation_id: int) -> None:
        if LdapServerConfig.load(self._charm.ldap_requirer):
            return self.load_bind_account_from_remote_ldap()
        if not (database_config := DatabaseConfig.load(self._charm.database_requirer)):
            return

        self._bind_account = _create_bind_account(database_config.dsn, user, group)
        if not self._bind_account.password:
            password = self._charm.ldap_provider.get_bind_password(relation_id)
            if not password:
                password = _reset_account_password(database_config.dsn, user)
            self._bind_account.password = password

    def load_bind_account_from_remote_ldap(self) -> None:
        ldap_config = LdapServerConfig.load(self._charm.ldap_requirer)

        if not ldap_config or not ldap_config.ldap_server:
            return

        bind_dn = {
            part.split("=")[0]: part.split("=")[1]
            for part in ldap_config.ldap_server.bind_dn.split(",")
        }
        self._bind_account = BindAccount(
            bind_dn.get("cn", ""), bind_dn.get("ou", ""), ldap_config.ldap_server.bind_password
        )

    @property
    def ldap_urls(self) -> List[str]:
        if ingress := self._charm.ingress_per_unit.urls:
            return [f"ldap://{url}" for url in ingress.values()]

        url = f"{self._charm.app.name}.{self._charm.model.name}.svc.cluster.local"
        return [f"ldap://{url}:{GLAUTH_LDAP_PORT}"]

    @property
    def ldaps_urls(self) -> List[str]:
        if ingress := self._charm.ldaps_ingress_per_unit.urls:
            return [f"ldaps://{url}" for url in ingress.values()]

        url = f"{self._charm.app.name}.{self._charm.model.name}.svc.cluster.local"
        return [f"ldaps://{url}:{GLAUTH_LDAPS_PORT}"]

    @property
    def base_dn(self) -> str:
        return self._charm.config.get("base_dn")

    @property
    def starttls_enabled(self) -> bool:
        return self._charm.config.get("starttls_enabled", True)

    @property
    def ldaps_enabled(self) -> bool:
        return self._charm.config.get("ldaps_enabled", False)

    @property
    def provider_base_data(self) -> LdapProviderBaseData:
        return LdapProviderBaseData(
            urls=self.ldap_urls,
            ldaps_urls=self.ldaps_urls,
            base_dn=self.base_dn,
            starttls=self.starttls_enabled,
        )

    @property
    def provider_data(self) -> Optional[LdapProviderData]:
        if not self._bind_account:
            return None

        return LdapProviderData(
            urls=self.ldap_urls,
            ldaps_urls=self.ldaps_urls,
            base_dn=self.base_dn,
            bind_dn=f"cn={self._bind_account.cn},ou={self._bind_account.ou},{self.base_dn}",
            bind_password=self._bind_account.password,
            auth_method="simple",
            starttls=self.starttls_enabled,
        )


class AuxiliaryIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm

    @property
    def auxiliary_data(self) -> AuxiliaryData:
        if not (database_config := DatabaseConfig.load(self._charm.database_requirer)):
            return AuxiliaryData()

        return AuxiliaryData(
            database=database_config.database,
            endpoint=database_config.endpoint,
            username=database_config.username,
            password=database_config.password,
        )


@dataclass
class CertificateData:
    ca_cert: Optional[str] = None
    ca_chain: Optional[list[str]] = None
    cert: Optional[str] = None


class CertificatesIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = charm._container

        k8s_svc_host = f"{charm.app.name}.{charm.model.name}.svc.cluster.local"
        sans_dns, sans_ip = [k8s_svc_host], []

        for ingress in (charm.ingress_per_unit, charm.ldaps_ingress_per_unit):
            if ingress_url := ingress.url:
                ingress_domain, *_ = ingress_url.rsplit(sep=":", maxsplit=1)

                try:
                    ipaddress.ip_address(ingress_domain)
                except ValueError:
                    sans_dns.append(ingress_domain)
                else:
                    sans_ip.append(ingress_domain)

        self.csr_attributes = CertificateRequestAttributes(
            common_name=k8s_svc_host,
            sans_dns=frozenset(sans_dns),
            sans_ip=frozenset(sans_ip),
        )
        self.cert_requirer = TLSCertificatesRequiresV4(
            charm,
            relationship_name=CERTIFICATES_INTEGRATION_NAME,
            certificate_requests=[self.csr_attributes],
            mode=Mode.UNIT,
            refresh_events=[
                charm.ingress_per_unit.on.ready_for_unit,
                charm.ingress_per_unit.on.revoked_for_unit,
                charm.ldaps_ingress_per_unit.on.ready_for_unit,
                charm.ldaps_ingress_per_unit.on.revoked_for_unit,
            ],
        )

    @property
    def _ca_cert(self) -> Optional[str]:
        return str(self._certs.ca) if self._certs else None

    @property
    def _server_key(self) -> Optional[str]:
        private_key = self.cert_requirer.private_key
        return str(private_key) if private_key else None

    @property
    def _server_cert(self) -> Optional[str]:
        return str(self._certs.certificate) if self._certs else None

    @property
    def _ca_chain(self) -> Optional[list[str]]:
        return [str(chain) for chain in self._certs.chain] if self._certs else None

    @property
    def _certs(self) -> Optional[ProviderCertificate]:
        cert, *_ = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return cert

    @property
    def cert_data(self) -> CertificateData:
        return CertificateData(
            ca_cert=self._ca_cert,
            ca_chain=self._ca_chain,
            cert=self._server_cert,
        )

    def update_certificates(self) -> None:
        if not self._charm.model.get_relation(CERTIFICATES_INTEGRATION_NAME):
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
        certs, private_key = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return all((certs, private_key))

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
