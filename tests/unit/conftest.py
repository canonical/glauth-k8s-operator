# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from typing import Callable
from unittest.mock import MagicMock

import pytest
from charm import GLAuthCharm
from charms.glauth_k8s.v0.ldap import LdapProviderData
from constants import (
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from ops.charm import CharmBase
from ops.testing import Harness
from pytest_mock import MockerFixture

DB_APP = "postgresql-k8s"
DB_DATABASE = "glauth"
DB_USERNAME = "relation_id"
DB_PASSWORD = "password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"

LDAP_CLIENT_APP = "ldap-client"
LDAP_PROVIDER_DATA = LdapProviderData(
    url="ldap://ldap.glauth.com",
    base_dn="dc=glauth,dc=com",
    bind_dn="cn=user,ou=group,dc=glauth,dc=com",
    bind_password_secret="password",
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


@pytest.fixture(autouse=True)
def k8s_client(mocker: MockerFixture) -> MagicMock:
    mocked_k8s_client = mocker.patch("charm.Client", autospec=True)
    return mocked_k8s_client


@pytest.fixture
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Harness:
    harness = Harness(GLAuthCharm)
    harness.set_model_name("unit-test")
    harness.set_can_connect("glauth", True)
    harness.set_leader(True)

    harness.begin()
    yield harness
    harness.cleanup()


@pytest.fixture
def mocked_hook_event(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("ops.charm.HookEvent", autospec=True)


@pytest.fixture
def mocked_configmap(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.ConfigMapResource", autospec=True)
    harness.charm._configmap = mocked
    return mocked


@pytest.fixture
def mocked_statefulset(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.StatefulSetResource", autospec=True)
    harness.charm._statefulset = mocked
    return mocked


@pytest.fixture
def mocked_restart_glauth_service(mocker: MockerFixture, harness: Harness) -> Callable:
    def mock_restart_glauth_service(charm: CharmBase) -> None:
        charm._container.restart(WORKLOAD_CONTAINER)

    return mocker.patch("charm.GLAuthCharm._restart_glauth_service", mock_restart_glauth_service)


@pytest.fixture
def mocked_ldap_integration(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.LdapIntegration", autospec=True)
    mocked.provider_data = LDAP_PROVIDER_DATA
    harness.charm._ldap_integration = mocked
    return mocked


@pytest.fixture
def mocked_certificates_integration(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.CertificatesIntegration", autospec=True)
    mocked.cert_handler = harness.charm._certs_integration.cert_handler
    harness.charm._certs_integration = mocked
    return mocked


@pytest.fixture
def mocked_certificates_transfer_integration(mocker: MockerFixture, harness: Harness) -> MagicMock:
    mocked = mocker.patch("charm.CertificatesTransferIntegration", autospec=True)
    harness.charm._certs_transfer_integration = mocked
    return mocked


@pytest.fixture
def mocked_tls_certificates(mocker: MockerFixture, harness: Harness) -> MagicMock:
    return mocker.patch("ops.model.Container.exists", return_value=True)


@pytest.fixture
def database_relation(harness: Harness) -> int:
    relation_id = harness.add_relation(DATABASE_INTEGRATION_NAME, DB_APP)
    harness.add_relation_unit(relation_id, f"{DB_APP}/0")
    return relation_id


@pytest.fixture
def database_resource(
    harness: Harness,
    mocked_configmap: MagicMock,
    mocked_statefulset: MagicMock,
    database_relation: int,
    mocked_restart_glauth_service: Callable,
) -> None:
    harness.update_relation_data(
        database_relation,
        DB_APP,
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "endpoints": DB_ENDPOINTS,
            "password": DB_PASSWORD,
            "username": DB_USERNAME,
        },
    )


@pytest.fixture
def ldap_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("ldap", LDAP_CLIENT_APP)
    harness.add_relation_unit(relation_id, f"{LDAP_CLIENT_APP}/0")
    return relation_id


@pytest.fixture
def ldap_relation_data(harness: Harness, ldap_relation: int) -> None:
    harness.update_relation_data(
        ldap_relation,
        LDAP_CLIENT_APP,
        {
            "user": "user",
            "group": "group",
        },
    )


@pytest.fixture
def ldap_auxiliary_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("glauth-auxiliary", LDAP_AUXILIARY_APP)
    harness.add_relation_unit(relation_id, f"{LDAP_AUXILIARY_APP}/0")
    return relation_id


@pytest.fixture
def ldap_auxiliary_relation_data(harness: Harness, ldap_auxiliary_relation: int) -> dict[str, str]:
    harness.update_relation_data(
        ldap_auxiliary_relation,
        LDAP_AUXILIARY_APP,
        LDAP_AUXILIARY_RELATION_DATA,
    )
    return LDAP_AUXILIARY_RELATION_DATA


@pytest.fixture
def certificates_relation(harness: Harness) -> int:
    relation_id = harness.add_relation(
        CERTIFICATES_INTEGRATION_NAME,
        CERTIFICATE_PROVIDER_APP,
    )
    return relation_id


@pytest.fixture
def certificates_transfer_relation(harness: Harness) -> int:
    relation_id = harness.add_relation(
        CERTIFICATES_TRANSFER_INTEGRATION_NAME, CERTIFICATES_TRANSFER_CLIENT_APP
    )
    harness.add_relation_unit(relation_id, f"{CERTIFICATES_TRANSFER_CLIENT_APP}/0")
    return relation_id


@pytest.fixture(autouse=True)
def mocked_juju_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch.dict(os.environ, {"JUJU_VERSION": "3.2.1"})
