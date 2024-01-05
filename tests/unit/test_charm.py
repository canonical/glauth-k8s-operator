# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from constants import WORKLOAD_CONTAINER, WORKLOAD_SERVICE
from kubernetes_resource import KubernetesResourceError
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness
from pytest_mock import MockerFixture


class TestInstallEvent:
    def test_on_install_non_leader_unit(
        self, harness: Harness, mocked_configmap: MagicMock, mocked_statefulset: MagicMock
    ) -> None:
        harness.set_leader(False)
        harness.charm.on.install.emit()

        mocked_configmap.create.assert_not_called()
        mocked_statefulset.patch.assert_not_called()

    def test_on_install(
        self, harness: Harness, mocked_configmap: MagicMock, mocked_statefulset: MagicMock
    ) -> None:
        harness.charm.on.install.emit()

        mocked_configmap.create.assert_called_once()
        mocked_statefulset.patch.assert_called_once()

    def test_configmap_creation_failed(self, harness: Harness, mocker: MockerFixture) -> None:
        mocked = mocker.patch("charm.ConfigMapResource.create")
        mocked.side_effect = KubernetesResourceError("Some reason.")

        with pytest.raises(KubernetesResourceError):
            harness.charm.on.install.emit()

        assert isinstance(harness.model.unit.status, MaintenanceStatus)


class TestRemoveEvent:
    def test_on_remove_non_leader_unit(
        self, harness: Harness, mocked_configmap: MagicMock
    ) -> None:
        harness.set_leader(False)
        harness.charm.on.remove.emit()

        mocked_configmap.delete.assert_not_called()

    def test_on_remove(self, harness: Harness, mocked_configmap: MagicMock) -> None:
        harness.charm.on.remove.emit()

        mocked_configmap.delete.assert_called_once()


class TestPebbleReadyEvent:
    def test_when_container_not_connected(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_missing_database_relation(self, harness: Harness) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_when_database_not_created(self, harness: Harness, database_relation: int) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_pebble_ready_event(
        self, harness: Harness, database_relation: int, database_resource: MagicMock
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.glauth_pebble_ready.emit(container)

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)


class TestDatabaseCreatedEvent:
    def test_database_created_event(
        self, harness: Harness, database_relation: int, database_resource: MagicMock
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)


class TestConfigChangedEvent:
    def test_when_container_not_connected(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_missing_database_relation(self, harness: Harness) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_when_database_not_created(self, harness: Harness, database_relation: int) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_on_config_changed_event(
        self, harness: Harness, database_relation: int, database_resource: MagicMock
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.config_changed.emit()

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)
