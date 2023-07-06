# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Generator
from unittest.mock import MagicMock

import pytest
from ops.model import Container
from ops.pebble import ExecError
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import GlauthK8SCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Harness:
    harness = Harness(GlauthK8SCharm)
    harness.set_model_name("glauth-model")
    harness.set_can_connect("glauth", True)
    harness.set_leader(True)
    harness.begin()
    return harness


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture()
def mocked_glauth_service(harness: Harness, mocked_container: MagicMock) -> Generator:
    service = MagicMock()
    service.is_running = lambda: True
    mocked_container.get_service = MagicMock(return_value=service)
    mocked_container.can_connect = MagicMock(return_value=True)
    return service


@pytest.fixture()
def mocked_container(harness: Harness, mocker: MockerFixture) -> Container:
    container = harness.model.unit.get_container("glauth")
    setattr(container, "restart", mocker.MagicMock())
    return container


@pytest.fixture()
def mocked_pebble_exec(mocker: MockerFixture) -> MagicMock:
    mocked_pebble_exec = mocker.patch("ops.model.Container.exec")
    return mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_success(mocker: MockerFixture, mocked_pebble_exec: MagicMock) -> MagicMock:
    mocked_process = mocker.patch("ops.pebble.ExecProcess")
    mocked_process.wait_output.return_value = ("Success", None)
    mocked_pebble_exec.return_value = mocked_process
    return mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_failed(mocked_pebble_exec: MagicMock) -> MagicMock:
    mocked_pebble_exec.side_effect = ExecError(
        exit_code=400, stderr="Failed to execute", stdout="Failed", command=["test", "command"]
    )
    return mocked_pebble_exec


@pytest.fixture(autouse=True)
def mocked_log_proxy_consumer_setup_promtail(mocker: MockerFixture) -> MagicMock:
    mocked_setup_promtail = mocker.patch(
        "charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._setup_promtail", return_value=None
    )
    return mocked_setup_promtail


@pytest.fixture()
def mocked_fqdn(mocker: MockerFixture) -> MagicMock:
    mocked_fqdn = mocker.patch("socket.getfqdn")
    mocked_fqdn.return_value = "glauth-k8s"
    return mocked_fqdn
