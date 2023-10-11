# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import GLAuthCharm
from constants import DATABASE_INTEGRATION_NAME

DB_APP = "postgresql-k8s"
DB_USERNAME = "relation_id"
DB_PASSWORD = "password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


@pytest.fixture(autouse=True)
def k8s_client(mocker: MockerFixture) -> MagicMock:
    mocked_k8s_client = mocker.patch("charm.Client", autospec=True)
    return mocked_k8s_client


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Harness:
    harness = Harness(GLAuthCharm)
    harness.set_model_name("unit-test")
    harness.set_can_connect("glauth", True)
    harness.set_leader(True)

    harness.begin()
    yield harness
    harness.cleanup()


@pytest.fixture()
def mocked_hook_event(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("ops.charm.HookEvent", autospec=True)


@pytest.fixture()
def mocked_configmap_patch(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.ConfigMapResource.patch")


@pytest.fixture()
def mocked_statefulset(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.StatefulSetResource", autospec=True)


@pytest.fixture()
def database_relation(harness: Harness) -> int:
    relation_id = harness.add_relation(DATABASE_INTEGRATION_NAME, DB_APP)
    harness.add_relation_unit(relation_id, "postgresql-k8s/0")
    return relation_id


@pytest.fixture()
def database_resource(
    mocker: MockerFixture,
    harness: Harness,
    mocked_configmap_patch: MagicMock,
    mocked_statefulset: MagicMock,
    database_relation: int,
) -> None:
    mocker.patch("charm.GLAuthCharm._render_config_file")

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
