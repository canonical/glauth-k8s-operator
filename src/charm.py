#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju Kubernetes charmed operator for GLAuth."""

import logging
from typing import Any, Optional

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.glauth_k8s.v0.ldap import (
    LdapProvider,
    LdapReadyEvent,
    LdapRequestedEvent,
    LdapRequirer,
)
from charms.glauth_utils.v0.glauth_auxiliary import AuxiliaryProvider, AuxiliaryRequestedEvent
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tls_certificates_interface.v4.tls_certificates import CertificateAvailableEvent
from charms.traefik_k8s.v1.ingress_per_unit import (
    IngressPerUnitReadyForUnitEvent,
    IngressPerUnitRequirer,
    IngressPerUnitRevokedForUnitEvent,
)
from lightkube import Client
from ops import StoredState, main
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationJoinedEvent,
    RemoveEvent,
    UpdateStatusEvent,
)
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import ChangeError

from configs import (
    ConfigFile,
    ConfigFileData,
    DatabaseConfig,
    LdapsConfig,
    LdapServerConfig,
    StartTLSConfig,
    pebble_layer,
)
from constants import (
    CERTIFICATES_INTEGRATION_NAME,
    CERTIFICATES_TRANSFER_INTEGRATION_NAME,
    DATABASE_INTEGRATION_NAME,
    GLAUTH_CONFIG_DIR,
    GLAUTH_LDAP_PORT,
    GLAUTH_LDAPS_PORT,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    INGRESS_PER_UNIT_INTEGRATION_NAME,
    LDAP_CLIENT_INTEGRATION_NAME,
    LDAPS_INGRESS_PER_UNIT_INTEGRATION_NAME,
    LOKI_API_PUSH_INTEGRATION_NAME,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from exceptions import CertificatesError
from integrations import (
    AuxiliaryIntegration,
    CertificatesIntegration,
    CertificatesTransferIntegration,
    LdapIntegration,
)
from kubernetes_resource import ConfigMapResource, StatefulSetResource
from utils import (
    after_config_updated,
    backend_integration_not_exists,
    backend_not_ready,
    block_when,
    container_not_connected,
    database_not_ready,
    integration_not_exists,
    leader_unit,
    service_not_ready,
    tls_certificates_not_ready,
    wait_when,
)

logger = logging.getLogger(__name__)


class GLAuthCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    config_changed = False

    def __init__(self, *args: Any):
        super().__init__(*args)
        self._stored.set_default(
            config_hash=None,
        )
        self._container = self.unit.get_container(WORKLOAD_CONTAINER)

        self._k8s_client = Client(field_manager=self.app.name, namespace=self.model.name)
        self._configmap = ConfigMapResource(client=self._k8s_client, name=self.app.name)
        self._statefulset = StatefulSetResource(client=self._k8s_client, name=self.app.name)

        self._db_name = f"{self.model.name}_{self.app.name}"
        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=self._db_name,
            extra_user_roles="SUPERUSER",
        )

        # FIXME: https://github.com/canonical/traefik-k8s-operator/issues/406 -
        #   `glauth-k8s` can only scale to one unit when integrated with
        #   `traefik-k8s`. `traefik-k8s` will become inactive if more than
        #   one `glauth-k8s` units are deployed because `traefik-k8s` attempts
        #   to assign them all the same LoadBalancer IP address.
        self.ingress_per_unit = IngressPerUnitRequirer(
            self,
            INGRESS_PER_UNIT_INTEGRATION_NAME,
            port=GLAUTH_LDAP_PORT,
            mode="tcp",
        )
        self.ldaps_ingress_per_unit = IngressPerUnitRequirer(
            self,
            LDAPS_INGRESS_PER_UNIT_INTEGRATION_NAME,
            port=GLAUTH_LDAPS_PORT,
            mode="tcp",
        )

        self.ldap_provider = LdapProvider(self)
        self.framework.observe(
            self.ldap_provider.on.ldap_requested,
            self._on_ldap_requested,
        )

        self.ldap_requirer = LdapRequirer(self, LDAP_CLIENT_INTEGRATION_NAME)
        self.framework.observe(
            self.ldap_requirer.on.ldap_ready,
            self._on_ldap_ready,
        )

        self.auxiliary_provider = AuxiliaryProvider(self)
        self.framework.observe(
            self.auxiliary_provider.on.auxiliary_requested,
            self._on_auxiliary_requested,
        )

        self._certs_integration = CertificatesIntegration(self)
        self.framework.observe(
            self._certs_integration.cert_requirer.on.certificate_available,
            self._on_cert_changed,
        )

        self._certs_transfer_integration = CertificatesTransferIntegration(self)
        self.framework.observe(
            self.on[CERTIFICATES_TRANSFER_INTEGRATION_NAME].relation_joined,
            self._on_certificates_transfer_relation_joined,
        )

        self.service_patcher = KubernetesServicePatch(
            self, [("ldap", GLAUTH_LDAP_PORT), ("ldaps", GLAUTH_LDAPS_PORT)]
        )

        self._log_forwarder = LogForwarder(self, relation_name=LOKI_API_PUSH_INTEGRATION_NAME)
        self.metrics_endpoint = MetricsEndpointProvider(
            self, relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME
        )
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.glauth_pebble_ready, self._on_pebble_ready)
        self.framework.observe(
            self.database_requirer.on.database_created, self._on_database_created
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed, self._on_database_changed
        )
        self.framework.observe(self.ingress_per_unit.on.ready_for_unit, self._on_ingress_changed)
        self.framework.observe(self.ingress_per_unit.on.revoked_for_unit, self._on_ingress_changed)

        self.framework.observe(
            self.ldaps_ingress_per_unit.on.ready_for_unit, self._on_ingress_changed
        )
        self.framework.observe(
            self.ldaps_ingress_per_unit.on.revoked_for_unit, self._on_ingress_changed
        )

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        self.config_file = ConfigFile(
            ConfigFileData(
                base_dn=self.config.get("base_dn"),
                anonymousdse_enabled=self.config.get("anonymousdse_enabled"),
                starttls_config=StartTLSConfig.load(self.config),
                ldaps_config=LdapsConfig.load(self.config),
                database_config=DatabaseConfig.load(self.database_requirer),
                ldap_servers_config=LdapServerConfig.load(self.ldap_requirer),
            ),
        )
        self._ldap_integration = LdapIntegration(self)
        self._auxiliary_integration = AuxiliaryIntegration(self)

    def _restart_service(self, restart: bool = False) -> None:
        if restart:
            self._container.restart(WORKLOAD_SERVICE)
        elif not self._container.get_service(WORKLOAD_SERVICE).is_running():
            self._container.start(WORKLOAD_SERVICE)
        else:
            self._container.replan()

    @after_config_updated
    def _restart_glauth_service(self, restart: bool = False) -> None:
        try:
            self._restart_service(restart)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the service, please check the logs"
            )

    @block_when(
        backend_integration_not_exists,
        integration_not_exists(CERTIFICATES_INTEGRATION_NAME),
    )
    @wait_when(
        container_not_connected,
        backend_not_ready,
        tls_certificates_not_ready,
    )
    def _handle_event_update(self, event: HookEvent) -> None:
        self._update_glauth_config()
        self._container.add_layer(WORKLOAD_CONTAINER, pebble_layer, combine=True)

        self._restart_glauth_service(restart=self.config_changed)
        self.unit.status = ActiveStatus()

    @property
    def current_config_hash(self) -> Optional[int]:
        return self._stored.config_hash

    @leader_unit
    def _update_cm(self) -> None:
        self._configmap.patch({"glauth.cfg": self.config_file.content})

    def _update_glauth_config(self) -> None:
        config_hash = hash(self.config_file)
        if config_hash == self.current_config_hash:
            return

        self._update_cm()

        self._stored.config_hash = config_hash
        self.config_changed = True

    @leader_unit
    def _mount_glauth_config(self) -> None:
        pod_spec_patch = {
            "containers": [
                {
                    "name": WORKLOAD_CONTAINER,
                    "volumeMounts": [
                        {
                            "mountPath": str(GLAUTH_CONFIG_DIR),
                            "name": "glauth-config",
                            "readOnly": True,
                        },
                    ],
                },
            ],
            "volumes": [
                {
                    "name": "glauth-config",
                    "configMap": {"name": self._configmap.name},
                },
            ],
        }
        patch_data = {"spec": {"template": {"spec": pod_spec_patch}}}
        self._statefulset.patch(patch_data)

    @leader_unit
    def _on_install(self, event: InstallEvent) -> None:
        self._configmap.create()
        self._update_glauth_config()

    @leader_unit
    def _on_remove(self, event: RemoveEvent) -> None:
        self._configmap.delete()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._handle_event_update(event)
        self.auxiliary_provider.update_relation_app_data(
            data=self._auxiliary_integration.auxiliary_data,
        )

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._handle_event_update(event)
        self.auxiliary_provider.update_relation_app_data(
            data=self._auxiliary_integration.auxiliary_data,
        )

    def _on_update_status(self, event: UpdateStatusEvent) -> None:
        self._handle_event_update(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._handle_event_update(event)
        self.ldap_provider.update_relations_app_data(self._ldap_integration.provider_base_data)

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._mount_glauth_config()
        self.__on_pebble_ready(event)

    @wait_when(container_not_connected)
    def __on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        try:
            self._certs_integration.update_certificates()
        except CertificatesError:
            self.unit.status = BlockedStatus(
                "Failed to update the TLS certificates, please check the logs"
            )
            return

        self._handle_event_update(event)

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Failed to patch resource constraints: {event.message}")
        self.unit.status = BlockedStatus(event.message)

    @leader_unit
    @wait_when(database_not_ready, service_not_ready)
    def _on_ldap_requested(self, event: LdapRequestedEvent) -> None:
        if not (requirer_data := event.data):
            logger.warning(f"The LDAP requirer {event.app.name} does not provide necessary data.")
            return

        self._ldap_integration.load_bind_account(
            requirer_data.user, requirer_data.group, event.relation.id
        )
        if not self._ldap_integration.provider_data:
            return

        self.ldap_provider.update_relations_app_data(
            self._ldap_integration.provider_data,
            relation_id=event.relation.id,
        )

    def _on_ldap_ready(self, event: LdapReadyEvent) -> None:
        self._handle_event_update(event)

    @wait_when(database_not_ready)
    def _on_auxiliary_requested(self, event: AuxiliaryRequestedEvent) -> None:
        self.auxiliary_provider.update_relation_app_data(
            relation_id=event.relation.id,
            data=self._auxiliary_integration.auxiliary_data,
        )

    @leader_unit
    @wait_when(container_not_connected)
    def _on_ingress_changed(
        self, event: IngressPerUnitReadyForUnitEvent | IngressPerUnitRevokedForUnitEvent
    ) -> None:
        self.ldap_provider.update_relations_app_data(self._ldap_integration.provider_base_data)

    @wait_when(container_not_connected)
    def _on_cert_changed(self, event: CertificateAvailableEvent) -> None:
        try:
            self._certs_integration.update_certificates()
        except CertificatesError:
            self.unit.status = BlockedStatus(
                "Failed to update the TLS certificates, please check the logs"
            )
            return

        self._handle_event_update(event)
        self._certs_transfer_integration.transfer_certificates(
            self._certs_integration.cert_data,
        )

    def _on_certificates_transfer_relation_joined(self, event: RelationJoinedEvent) -> None:
        if not self._certs_integration.certs_ready():
            event.defer()
            return

        self._certs_transfer_integration.transfer_certificates(
            self._certs_integration.cert_data, event.relation.id
        )

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)


if __name__ == "__main__":
    main(GLAuthCharm)
