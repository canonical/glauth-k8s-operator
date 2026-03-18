# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from charms.tls_certificates_interface.v4.tls_certificates import (
    Certificate,
    CertificateSigningRequest,
)
from conftest import (
    DB_ENDPOINTS,
    DB_PASSWORD,
    DB_USERNAME,
    LDAP_PROVIDER_DATA,
    LDAPS_PROVIDER_DATA,
    create_state,
)
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Container, Context, Relation

from constants import CERTIFICATES_INTEGRATION_NAME, WORKLOAD_CONTAINER
from exceptions import CertificatesError
from kubernetes_resource import KubernetesResourceError


class TestInstallEvent:
    def test_on_install(self, context: Context, mocked_configmap: MagicMock) -> None:
        state = create_state()
        context.run(context.on.install(), state)

        mocked_configmap.create.assert_called_once()

    def test_configmap_creation_failed(
        self, context: Context, mocked_configmap: MagicMock
    ) -> None:
        mocked_configmap.create.side_effect = KubernetesResourceError("Some reason.")
        state = create_state()

        with pytest.raises(Exception, match="Some reason."):
            context.run(context.on.install(), state)


class TestRemoveEvent:
    def test_on_remove_non_leader_unit(
        self, context: Context, mocked_configmap: MagicMock
    ) -> None:
        state = create_state(leader=False)
        context.run(context.on.remove(), state)

        mocked_configmap.delete.assert_not_called()

    def test_on_remove(self, context: Context, mocked_configmap: MagicMock) -> None:
        state = create_state()
        context.run(context.on.remove(), state)

        mocked_configmap.delete.assert_called_once()


class TestPebbleReadyEvent:
    def test_when_container_not_connected(
        self,
        context: Context,
        db_relation: Relation,
        mocked_statefulset: MagicMock,
        certificates_relation: Relation,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        state = create_state(
            relations=[db_relation, certificates_relation],
            containers=[container],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == WaitingStatus("Container is not connected yet")
        mocked_statefulset.patch.assert_called_once()

    def test_when_missing_database_relation(
        self,
        context: Context,
        mocked_statefulset: MagicMock,
        certificates_relation: Relation,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(
            relations=[certificates_relation],
            containers=[container],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == BlockedStatus(
            "Backend integration (`pg-database` or `ldap-client`) missing"
        )
        mocked_statefulset.patch.assert_called_once()

    def test_when_missing_certificates_relation(
        self,
        context: Context,
        db_relation: Relation,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(relations=[db_relation], containers=[container])
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == BlockedStatus(
            f"Missing integration {CERTIFICATES_INTEGRATION_NAME}"
        )

    def test_when_tls_certificates_not_exist(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(
            relations=[certificates_relation, db_relation_ready],
            containers=[container],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == WaitingStatus("Missing TLS certificate and private key")

    def test_when_backend_not_created(
        self,
        context: Context,
        db_relation: Relation,
        ldap_relation: Relation,
        certificates_relation: Relation,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(
            relations=[db_relation, ldap_relation, certificates_relation],
            containers=[container],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == WaitingStatus("Waiting for database creation")

    def test_pebble_ready_event_with_database_backend(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(
            relations=[certificates_relation, db_relation_ready],
            containers=[container],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == ActiveStatus()

    def test_pebble_ready_event_with_ldap_backend(
        self,
        context: Context,
        certificates_relation: Relation,
        ldap_client_relation_ready: Relation,
        ldap_client_bind_password_secret: MagicMock,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=True)
        state = create_state(
            relations=[certificates_relation, ldap_client_relation_ready],
            containers=[container],
            secrets=[ldap_client_bind_password_secret],
        )
        out = context.run(context.on.pebble_ready(container), state)

        assert out.unit_status == ActiveStatus()


class TestDatabaseCreatedEvent:
    def test_database_created_event(
        self,
        context: Context,
        mocked_tls_certificates: MagicMock,
        certificates_relation: Relation,
        db_relation_ready: Relation,
    ) -> None:
        state = create_state(relations=[certificates_relation, db_relation_ready])
        out = context.run(context.on.relation_changed(db_relation_ready), state)

        assert out.unit_status == ActiveStatus()


class TestConfigChangedEvent:
    def test_when_container_not_connected(
        self,
        context: Context,
        db_relation: Relation,
        certificates_relation: Relation,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        state = create_state(
            relations=[db_relation, certificates_relation],
            containers=[container],
        )
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == WaitingStatus("Container is not connected yet")

    def test_when_missing_database_relation(
        self,
        context: Context,
        certificates_relation: Relation,
    ) -> None:
        state = create_state(relations=[certificates_relation])
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == BlockedStatus(
            "Backend integration (`pg-database` or `ldap-client`) missing"
        )

    def test_when_missing_certificates_relation(
        self,
        context: Context,
        db_relation: Relation,
    ) -> None:
        state = create_state(relations=[db_relation])
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == BlockedStatus(
            f"Missing integration {CERTIFICATES_INTEGRATION_NAME}"
        )

    def test_when_tls_certificates_not_exist(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
    ) -> None:
        state = create_state(relations=[certificates_relation, db_relation_ready])
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == WaitingStatus("Missing TLS certificate and private key")

    def test_when_database_not_created(
        self,
        context: Context,
        db_relation: Relation,
        certificates_relation: Relation,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        state = create_state(relations=[db_relation, certificates_relation])
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == WaitingStatus("Waiting for database creation")

    def test_on_config_changed_event(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        state = create_state(relations=[certificates_relation, db_relation_ready])
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == ActiveStatus()

    def test_enable_ldaps_changed_event(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        mocked_tls_certificates: MagicMock,
    ) -> None:
        state = create_state(
            relations=[certificates_relation, db_relation_ready],
            config={"ldaps_enabled": True},
        )
        out = context.run(context.on.config_changed(), state)

        assert out.unit_status == ActiveStatus()


class TestLdapRequestedEvent:
    def test_when_database_not_created(
        self,
        context: Context,
        db_relation: Relation,
        certificates_relation: Relation,
        ldap_relation_with_data: Relation,
    ) -> None:
        state = create_state(
            relations=[db_relation, certificates_relation, ldap_relation_with_data]
        )
        out = context.run(context.on.relation_changed(ldap_relation_with_data), state)

        assert out.unit_status == WaitingStatus("Waiting for database creation")

    def test_when_requirer_data_not_ready(
        self,
        context: Context,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        ldap_relation: Relation,
    ) -> None:
        state = create_state(relations=[certificates_relation, db_relation_ready, ldap_relation])
        out = context.run(context.on.relation_changed(ldap_relation), state)

        assert not out.get_relation(ldap_relation.id).local_app_data

    def test_when_ldap_requested(
        self,
        context: Context,
        mocked_tls_certificates: MagicMock,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        mocked_ldap_integration: MagicMock,
        ldap_relation_with_data: Relation,
    ) -> None:
        state = create_state(
            relations=[certificates_relation, db_relation_ready, ldap_relation_with_data],
        )
        out = context.run(context.on.relation_changed(ldap_relation_with_data), state)

        actual = out.get_relation(ldap_relation_with_data.id).local_app_data
        assert LDAP_PROVIDER_DATA.model_dump() == actual

    def test_when_ldaps_requested(
        self,
        context: Context,
        mocked_tls_certificates: MagicMock,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        mocked_ldaps_integration: MagicMock,
        ldap_relation_with_data: Relation,
    ) -> None:
        state = create_state(
            relations=[certificates_relation, db_relation_ready, ldap_relation_with_data],
            config={"ldaps_enabled": True},
        )
        out = context.run(context.on.relation_changed(ldap_relation_with_data), state)

        actual = out.get_relation(ldap_relation_with_data.id).local_app_data
        assert LDAPS_PROVIDER_DATA.model_dump() == actual


class TestLdapReadyEvent:
    def test_when_requirer_data_not_ready(
        self,
        context: Context,
        certificates_relation: Relation,
        ldap_client_relation: Relation,
    ) -> None:
        state = create_state(relations=[certificates_relation, ldap_client_relation])
        out = context.run(context.on.relation_changed(ldap_client_relation), state)

        assert not out.get_relation(ldap_client_relation.id).local_app_data

    def test_when_ldap_ready(
        self,
        context: Context,
        certificates_relation: Relation,
        mocked_tls_certificates: MagicMock,
        mocked_ldap_integration: MagicMock,
        ldap_client_relation_ready: Relation,
        ldap_client_bind_password_secret: MagicMock,
    ) -> None:
        state = create_state(
            relations=[certificates_relation, ldap_client_relation_ready],
            secrets=[ldap_client_bind_password_secret],
        )
        out = context.run(context.on.relation_changed(ldap_client_relation_ready), state)

        assert out.unit_status == ActiveStatus()


class TestLdapAuxiliaryRequestedEvent:
    def test_when_database_not_created(
        self,
        context: Context,
        db_relation: Relation,
        ldap_auxiliary_relation: Relation,
    ) -> None:
        state = create_state(relations=[db_relation, ldap_auxiliary_relation])
        # AuxiliaryProvider fires auxiliary_requested on relation_created,
        # which is gated by @wait_when(database_not_ready).
        out = context.run(context.on.relation_created(ldap_auxiliary_relation), state)

        assert out.unit_status == WaitingStatus("Waiting for database creation")

    def test_on_ldap_auxiliary_requested(
        self,
        context: Context,
        mocked_tls_certificates: MagicMock,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        ldap_auxiliary_relation: Relation,
    ) -> None:
        state = create_state(
            relations=[certificates_relation, db_relation_ready, ldap_auxiliary_relation]
        )
        out = context.run(context.on.relation_created(ldap_auxiliary_relation), state)

        # _on_auxiliary_requested writes DB credentials to the local app databag.
        # `database` is generated as "{model_name}_{app_name}" by the charm and is not
        # predictable from the fixture, so we only verify its presence.
        local_data = out.get_relation(ldap_auxiliary_relation.id).local_app_data
        assert "database" in local_data
        assert local_data["endpoint"] == DB_ENDPOINTS
        assert local_data["username"] == DB_USERNAME
        assert local_data["password"] == DB_PASSWORD


class TestCertChangedEvent:
    def test_when_container_not_connected(
        self,
        context: Context,
        csr: CertificateSigningRequest,
        certificate: Certificate,
    ) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        # Also provide the certificates relation so config_changed doesn't block before reaching
        # the container-not-connected guard inside _on_cert_changed.
        certificates_relation = Relation(CERTIFICATES_INTEGRATION_NAME)
        db_relation_bare = Relation("pg-database")
        state = create_state(
            containers=[container],
            relations=[db_relation_bare, certificates_relation],
        )
        with context(context.on.config_changed(), state) as mgr:
            mgr.charm._certs_integration.cert_requirer.on.certificate_available.emit(
                certificate,
                csr,
                certificate,
                [certificate],
            )

        assert mgr.charm.unit.status == WaitingStatus("Container is not connected yet")

    def test_when_update_certificates_failed(
        self,
        context: Context,
        mocker: MagicMock,
        mocked_tls_certificates: MagicMock,
        csr: CertificateSigningRequest,
        certificate: Certificate,
    ) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            # Patch instance methods after charm init; no mgr.run() needed because
            # we manually emit certificate_available to drive _on_cert_changed.
            mock_update = mocker.patch.object(
                mgr.charm._certs_integration,
                "update_certificates",
                side_effect=CertificatesError,
            )
            mock_transfer = mocker.patch.object(
                mgr.charm._certs_transfer_integration,
                "transfer_certificates",
            )
            mgr.charm._certs_integration.cert_requirer.on.certificate_available.emit(
                certificate,
                csr,
                certificate,
                [certificate],
            )

        mock_update.assert_called_once()
        mock_transfer.assert_not_called()

    def test_on_cert_changed(
        self,
        context: Context,
        mocker: MagicMock,
        mocked_tls_certificates: MagicMock,
        certificates_relation: Relation,
        db_relation_ready: Relation,
        csr: CertificateSigningRequest,
        certificate: Certificate,
    ) -> None:
        # Provide the relations needed so _handle_event_update doesn't defer.
        state = create_state(relations=[certificates_relation, db_relation_ready])
        with context(context.on.config_changed(), state) as mgr:
            mock_update = mocker.patch.object(
                mgr.charm._certs_integration,
                "update_certificates",
            )
            mock_transfer = mocker.patch.object(
                mgr.charm._certs_transfer_integration,
                "transfer_certificates",
            )
            mgr.charm._certs_integration.cert_requirer.on.certificate_available.emit(
                certificate,
                csr,
                certificate,
                [certificate],
            )

        mock_update.assert_called_once()
        mock_transfer.assert_called_once()


class TestCertificatesTransferEvent:
    def test_when_certificate_data_not_ready(
        self,
        context: Context,
        mocker: MagicMock,
        certificates_transfer_relation: Relation,
    ) -> None:
        mocked_certs_transfer = mocker.patch(
            "charm.CertificatesTransferIntegration", autospec=True
        )
        state = create_state(relations=[certificates_transfer_relation])
        context.run(context.on.relation_joined(certificates_transfer_relation), state)

        mocked_certs_transfer.return_value.transfer_certificates.assert_not_called()

    def test_certificates_transfer_relation_joined(
        self,
        context: Context,
        mocker: MagicMock,
        certificates_transfer_relation: Relation,
    ) -> None:
        state = create_state(relations=[certificates_transfer_relation])
        with context(context.on.relation_joined(certificates_transfer_relation), state) as mgr:
            # Patch instance methods after charm init, before event dispatch.
            mocker.patch.object(mgr.charm._certs_integration, "certs_ready", return_value=True)
            mock_transfer = mocker.patch.object(
                mgr.charm._certs_transfer_integration, "transfer_certificates"
            )
            mgr.run()

        mock_transfer.assert_called_once()
