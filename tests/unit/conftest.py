# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import datetime
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from charms.glauth_k8s.v0.ldap import LdapProviderData
from charms.tls_certificates_interface.v4.tls_certificates import (
    Certificate,
    CertificateSigningRequest,
)
from cryptography import x509
from cryptography.hazmat._oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from ops.pebble import Layer, ServiceStatus
from ops.testing import Container, Context, Relation, Secret, State
from pytest_mock import MockerFixture

from charm import GLAuthCharm
from constants import (
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    LDAP_CLIENT_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)

# Minimal pebble layer that registers the workload service so that
# Container.services / get_service() can find it during tests.
_WORKLOAD_LAYER = Layer({
    "services": {
        WORKLOAD_SERVICE: {
            "override": "replace",
            "startup": "disabled",
            "command": "/usr/bin/glauth",
        }
    }
})

DB_APP = "postgresql-k8s"
DB_DATABASE = "glauth"
DB_USERNAME = "relation_id"
DB_PASSWORD = "password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"

LDAP_PROVIDER_APP = "ldap-server"
LDAP_CLIENT_APP = "ldap-client"
LDAP_PROVIDER_DATA = LdapProviderData(
    urls=["ldap://ldap.glauth.com"],
    ldaps_urls=[],
    base_dn="dc=glauth,dc=com",
    bind_dn="cn=user,ou=group,dc=glauth,dc=com",
    bind_password="password",
    bind_password_secret="secret-id",
    auth_method="simple",
    starttls=True,
)
LDAPS_PROVIDER_DATA = LdapProviderData(
    urls=["ldap://ldap.glauth.com"],
    ldaps_urls=["ldaps://ldaps.glauth.com"],
    base_dn="dc=glauth,dc=com",
    bind_dn="cn=user,ou=group,dc=glauth,dc=com",
    bind_password="password",
    bind_password_secret="secret-id",
    auth_method="simple",
    starttls=True,
)

LDAP_AUXILIARY_APP = "glauth-utils"
LDAP_AUXILIARY_RELATION_DATA = {
    "database": DB_DATABASE,
    "endpoint": DB_ENDPOINTS,
    "username": DB_USERNAME,
    "password": DB_PASSWORD,
}

CERTIFICATE_PROVIDER_APP = "self-signed-certificates"
CERTIFICATES_TRANSFER_CLIENT_APP = "sssd"

LDAP_CLIENT_BIND_PASSWORD_SECRET_ID = "secret:ldap-bind-0000"


@pytest.fixture(autouse=True)
def k8s_client(mocker: MockerFixture) -> MagicMock:
    """Mock the lightkube Client used for K8s API calls."""
    mocked_k8s_client = mocker.patch("charm.Client", autospec=True)
    return mocked_k8s_client


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    """Mock the KubernetesComputeResourcesPatch to avoid K8s API calls."""
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="kratos-model",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture(autouse=True)
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    """Mock KubernetesServicePatch to avoid K8s API calls."""
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture(autouse=True)
def mocked_configmap(mocker: MockerFixture) -> MagicMock:
    """Mock ConfigMapResource; returns the instance mock for assertion convenience."""
    mocked = mocker.patch("charm.ConfigMapResource", autospec=True)
    return mocked.return_value


@pytest.fixture(autouse=True)
def mocked_statefulset(mocker: MockerFixture) -> MagicMock:
    """Mock StatefulSetResource; returns the instance mock for assertion convenience."""
    mocked = mocker.patch("charm.StatefulSetResource", autospec=True)
    return mocked.return_value


@pytest.fixture(autouse=True)
def mocked_restart_glauth_service(mocker: MockerFixture) -> MagicMock:
    """Mock _restart_glauth_service to bypass the after_config_updated retry loop."""
    return mocker.patch("charm.GLAuthCharm._restart_glauth_service")


@pytest.fixture
def context() -> Context:
    """ops.testing Context for GLAuthCharm."""
    return Context(GLAuthCharm, juju_version="3.2.1")


def create_state(
    leader: bool = True,
    secrets: list | None = None,
    relations: list | None = None,
    containers: list | None = None,
    config: dict | None = None,
) -> State:
    """Create a State with sensible defaults.

    Defaults to a connected workload container with the service active.
    """
    if secrets is None:
        secrets = []
    if relations is None:
        relations = []
    if containers is None:
        containers = [
            Container(
                name=WORKLOAD_CONTAINER,
                can_connect=True,
                layers={"workload": _WORKLOAD_LAYER},
                service_statuses={WORKLOAD_SERVICE: ServiceStatus.ACTIVE},
            )
        ]
    if config is None:
        config = {}
    return State(
        leader=leader,
        secrets=secrets,
        containers=containers,
        relations=relations,
        config=config,
    )


# ---------------------------------------------------------------------------
# Relation fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_relation() -> Relation:
    """Bare database relation without remote data."""
    return Relation(DATABASE_INTEGRATION_NAME)


@pytest.fixture
def db_relation_ready(db_relation: Relation) -> Relation:
    """Database relation populated with remote application data."""
    return replace(
        db_relation,
        remote_app_data={
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "endpoints": DB_ENDPOINTS,
            "password": DB_PASSWORD,
            "username": DB_USERNAME,
        },
    )


@pytest.fixture
def certificates_relation() -> Relation:
    """Bare certificates relation."""
    return Relation(CERTIFICATES_INTEGRATION_NAME)


@pytest.fixture
def ldap_relation() -> Relation:
    """Bare outbound LDAP relation (GLAuth acts as LDAP provider)."""
    return Relation("ldap")


@pytest.fixture
def ldap_relation_with_data(ldap_relation: Relation) -> Relation:
    """LDAP relation with requirer application data (user + group)."""
    return replace(ldap_relation, remote_app_data={"user": "user", "group": "group"})


@pytest.fixture
def ldap_client_relation() -> Relation:
    """Bare ldap-client relation (GLAuth acts as LDAP requirer to an upstream server)."""
    return Relation(LDAP_CLIENT_INTEGRATION_NAME)


@pytest.fixture
def ldap_client_relation_ready(ldap_client_relation: Relation) -> Relation:
    """ldap-client relation populated with upstream LDAP provider data."""
    return replace(
        ldap_client_relation,
        remote_app_data={
            "urls": '["ldap://ldap.glauth.com"]',
            "ldaps_urls": "[]",
            "base_dn": "dc=glauth,dc=com",
            "bind_dn": "cn=user,ou=group,dc=glauth,dc=com",
            "bind_password": "password",
            "bind_password_secret": LDAP_CLIENT_BIND_PASSWORD_SECRET_ID,
            "auth_method": "simple",
            "starttls": "True",
            "ldaps": "False",
        },
    )


@pytest.fixture
def ldap_client_bind_password_secret() -> Secret:
    """Secret carrying the LDAP bind password referenced by ldap_client_relation_ready."""
    return Secret(
        id=LDAP_CLIENT_BIND_PASSWORD_SECRET_ID,
        tracked_content={"password": "password"},
    )


@pytest.fixture
def ldap_auxiliary_relation() -> Relation:
    """Bare glauth-auxiliary relation."""
    return Relation("glauth-auxiliary")


@pytest.fixture
def certificates_transfer_relation() -> Relation:
    """Bare send-ca-cert relation."""
    return Relation(CERTIFICATES_TRANSFER_INTEGRATION_NAME)


# ---------------------------------------------------------------------------
# Behaviour mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mocked_tls_certificates(mocker: MockerFixture) -> MagicMock:
    """Patch Container.exists to simulate TLS certificates being present."""
    return mocker.patch("ops.model.Container.exists", return_value=True)


@pytest.fixture
def mocked_ldap_integration(mocker: MockerFixture) -> MagicMock:
    """Mock LdapIntegration to expose LDAP provider data."""
    mocked = mocker.patch("charm.LdapIntegration", autospec=True)
    mocked.return_value.provider_data = LDAP_PROVIDER_DATA
    return mocked.return_value


@pytest.fixture
def mocked_ldaps_integration(mocker: MockerFixture) -> MagicMock:
    """Mock LdapIntegration to expose LDAPS provider data."""
    mocked = mocker.patch("charm.LdapIntegration", autospec=True)
    mocked.return_value.provider_data = LDAPS_PROVIDER_DATA
    return mocked.return_value


@pytest.fixture
def mocked_hook_event(mocker: MockerFixture) -> MagicMock:
    """Minimal mock used by decorator unit tests."""
    return mocker.patch("ops.charm.HookEvent", autospec=True)


# ---------------------------------------------------------------------------
# TLS certificate fixtures (module-scoped; expensive to generate)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def private_key() -> RSAPrivateKey:
    """Generate a test RSA private key."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture(scope="module")
def csr(private_key: RSAPrivateKey) -> CertificateSigningRequest:
    """Generate a test CSR."""
    raw_csr = (
        x509
        .CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "mysite.com"),
            ])
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("mysite.com"),
            ]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    raw = raw_csr.public_bytes(encoding=serialization.Encoding.PEM).decode("utf-8")
    return CertificateSigningRequest(raw, common_name="mysite.com")


@pytest.fixture(scope="module")
def certificate(private_key: RSAPrivateKey) -> Certificate:
    """Generate a test self-signed certificate."""
    start_time = datetime.datetime.now(datetime.timezone.utc)
    expiry_time = start_time + datetime.timedelta(days=10)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "mysite.com"),
    ])
    raw_cert = (
        x509
        .CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start_time)
        .not_valid_after(expiry_time)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("mysite.com")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    raw = raw_cert.public_bytes(encoding=serialization.Encoding.PEM).decode("utf-8")
    return Certificate(raw, "mysite.com", expiry_time, start_time)
