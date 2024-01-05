# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Callable
from unittest.mock import MagicMock

import pytest
from charm import GLAuthCharm
from constants import DATABASE_INTEGRATION_NAME, WORKLOAD_CONTAINER
from ops.charm import CharmBase
from ops.testing import Harness
from pytest_mock import MockerFixture

DB_APP = "postgresql-k8s"
DB_USERNAME = "relation_id"
DB_PASSWORD = "password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


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
def database_relation(harness: Harness) -> int:
    relation_id = harness.add_relation(DATABASE_INTEGRATION_NAME, DB_APP)
    harness.add_relation_unit(relation_id, "postgresql-k8s/0")
    return relation_id


@pytest.fixture
def mocked_restart_glauth_service(mocker: MockerFixture, harness: Harness) -> Callable:
    def mock_restart_glauth_service(charm: CharmBase) -> None:
        charm._container.restart(WORKLOAD_CONTAINER)

    return mocker.patch("charm.GLAuthCharm._restart_glauth_service", mock_restart_glauth_service)


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
