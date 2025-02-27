# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from conftest import (
    LDAP_AUXILIARY_APP,
    LDAP_CLIENT_APP,
    LDAP_PROVIDER_APP,
    LDAP_PROVIDER_DATA,
    LDAPS_PROVIDER_DATA,
)
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness
from pytest_mock import MockerFixture

from constants import WORKLOAD_CONTAINER, WORKLOAD_SERVICE
from exceptions import CertificatesError
from kubernetes_resource import KubernetesResourceError


class TestInstallEvent:
    def test_on_install(self, harness: Harness, mocked_configmap: MagicMock) -> None:
        harness.charm.on.install.emit()

        mocked_configmap.create.assert_called_once()

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
    def test_when_container_not_connected(
        self,
        harness: Harness,
        database_relation: int,
        mocked_statefulset: MagicMock,
        certificates_relation: int,
    ) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)
        mocked_statefulset.patch.assert_called_once()

    def test_when_missing_database_relation(
        self,
        harness: Harness,
        mocked_statefulset: MagicMock,
        certificates_relation: int,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, BlockedStatus)
        mocked_statefulset.patch.assert_called_once()

    def test_when_missing_certificates_relation(
        self,
        harness: Harness,
        database_relation: int,
    ) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_when_tls_certificates_not_exist(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_backend_not_created(
        self,
        harness: Harness,
        database_relation: int,
        ldap_client_relation: int,
        certificates_relation: int,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.glauth_pebble_ready.emit(container)

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_pebble_ready_event_with_database_backend(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.glauth_pebble_ready.emit(container)

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)

    def test_pebble_ready_event_with_ldap_backend(
        self,
        harness: Harness,
        certificates_relation: int,
        ldap_client_resource: MagicMock,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.glauth_pebble_ready.emit(container)

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)


class TestDatabaseCreatedEvent:
    def test_database_created_event(
        self,
        harness: Harness,
        mocked_tls_certificates: MagicMock,
        certificates_relation: int,
        database_resource: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)


class TestConfigChangedEvent:
    def test_when_container_not_connected(
        self,
        harness: Harness,
        database_relation: int,
        certificates_relation: int,
    ) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_missing_database_relation(
        self,
        harness: Harness,
        certificates_relation: int,
    ) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_when_missing_certificates_relation(
        self,
        harness: Harness,
        database_relation: int,
    ) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_when_tls_certificates_not_exist(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
    ) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_database_not_created(
        self,
        harness: Harness,
        database_relation: int,
        certificates_relation: int,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        harness.charm.on.config_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_on_config_changed_event(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.charm.on.config_changed.emit()

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)

    def test_enable_ldaps_changed_event(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
        mocked_tls_certificates: MagicMock,
    ):
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        harness.update_config({"ldaps_enabled": True})

        service = container.get_service(WORKLOAD_SERVICE)
        assert service.is_running()
        assert isinstance(harness.model.unit.status, ActiveStatus)


class TestLdapRequestedEvent:
    def test_when_database_not_created(
        self,
        harness: Harness,
        database_relation: int,
        certificates_relation: int,
        ldap_relation_data: MagicMock,
    ) -> None:
        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_when_requirer_data_not_ready(
        self,
        harness: Harness,
        certificates_relation: int,
        database_resource: MagicMock,
        ldap_relation: int,
    ) -> None:
        assert not harness.get_relation_data(ldap_relation, LDAP_CLIENT_APP)

    def test_when_ldap_requested(
        self,
        harness: Harness,
        mocked_tls_certificates: MagicMock,
        certificates_relation: int,
        database_resource: MagicMock,
        mocked_ldap_integration: MagicMock,
        ldap_relation: int,
        ldap_relation_data: MagicMock,
    ) -> None:
        assert isinstance(harness.model.unit.status, ActiveStatus)

        actual = dict(harness.get_relation_data(ldap_relation, harness.model.app.name))
        assert LDAP_PROVIDER_DATA.model_dump() == actual

    def test_when_ldaps_requested(
        self,
        harness: Harness,
        mocked_tls_certificates: MagicMock,
        certificates_relation: int,
        database_resource: MagicMock,
        mocked_ldaps_integration: MagicMock,
        ldap_relation: int,
        ldap_relation_data: MagicMock,
    ) -> None:
        assert isinstance(harness.model.unit.status, ActiveStatus)

        harness.update_config({"ldaps_enabled": True})

        actual = dict(harness.get_relation_data(ldap_relation, harness.model.app.name))
        assert LDAPS_PROVIDER_DATA.model_dump() == actual


class TestLdapReadyEvent:
    def test_when_requirer_data_not_ready(
        self,
        harness: Harness,
        certificates_relation: int,
        ldap_client_relation: int,
    ) -> None:
        assert not harness.get_relation_data(ldap_client_relation, LDAP_PROVIDER_APP)

    def test_when_ldap_ready(
        self,
        harness: Harness,
        mocked_tls_certificates: MagicMock,
        certificates_relation: int,
        mocked_ldap_integration: MagicMock,
        ldap_client_relation: int,
        ldap_client_resource: MagicMock,
    ) -> None:
        assert isinstance(harness.model.unit.status, ActiveStatus)

        actual = dict(harness.get_relation_data(ldap_client_relation, harness.model.app.name))
        expected = {
            "group": harness.model.name,
            "user": harness.model.app.name,
        }
        assert expected == actual


class TestLdapAuxiliaryRequestedEvent:
    def test_when_database_not_created(
        self, harness: Harness, database_relation: int, ldap_auxiliary_relation: int
    ) -> None:
        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_on_ldap_auxiliary_requested(
        self,
        harness: Harness,
        mocked_tls_certificates: MagicMock,
        certificates_relation: int,
        database_resource: MagicMock,
        ldap_auxiliary_relation: int,
        ldap_auxiliary_relation_data: MagicMock,
    ) -> None:
        assert isinstance(harness.model.unit.status, ActiveStatus)
        assert ldap_auxiliary_relation_data == harness.get_relation_data(
            ldap_auxiliary_relation, LDAP_AUXILIARY_APP
        )


class TestCertChangedEvent:
    def test_when_container_not_connected(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        harness.charm._certs_integration.cert_handler.on.cert_changed.emit()

        assert isinstance(harness.model.unit.status, WaitingStatus)

    @patch(
        "charm.CertificatesIntegration.update_certificates",
        side_effect=CertificatesError,
    )
    def test_when_update_certificates_failed(
        self,
        mocked_update_certificates: MagicMock,
        harness: Harness,
        mocked_certificates_integration: MagicMock,
        mocked_certificates_transfer_integration: MagicMock,
    ) -> None:
        harness.charm._certs_integration.cert_handler.on.cert_changed.emit()

        mocked_certificates_integration.update_certificates.assert_called_once()
        mocked_certificates_transfer_integration.transfer_certificates.assert_not_called()

    def test_on_cert_changed(
        self,
        harness: Harness,
        mocked_certificates_integration: MagicMock,
        mocked_certificates_transfer_integration: MagicMock,
    ) -> None:
        harness.charm._certs_integration.cert_handler.on.cert_changed.emit()

        mocked_certificates_integration.update_certificates.assert_called_once()
        mocked_certificates_transfer_integration.transfer_certificates.assert_called_once()


class TestCertificatesTransferEvent:
    def test_when_certificate_data_not_ready(
        self,
        mocked_certificates_transfer_integration: MagicMock,
        certificates_transfer_relation: int,
    ) -> None:
        mocked_certificates_transfer_integration.transfer_certificates.assert_not_called()

    def test_certificates_transfer_relation_joined(
        self,
        mocked_certificates_integration: MagicMock,
        mocked_certificates_transfer_integration: MagicMock,
        certificates_transfer_relation: int,
    ) -> None:
        mocked_certificates_transfer_integration.transfer_certificates.assert_called_once()
