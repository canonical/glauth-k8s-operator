#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju Kubernetes charmed operator for GLAuth."""

import logging
from typing import Any

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, PromtailDigestError
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from jinja2 import Template
from lightkube import Client
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    InstallEvent,
    PebbleReadyEvent,
    RemoveEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import ChangeError, Layer

from constants import (
    DATABASE_INTEGRATION_NAME,
    GLAUTH_COMMANDS,
    GLAUTH_CONFIG_DIR,
    GLAUTH_LDAP_PORT,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    LOG_DIR,
    LOG_FILE,
    LOKI_API_PUSH_INTEGRATION_NAME,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from kubernetes_resource import ConfigMapResource, StatefulSetResource
from validators import (
    leader_unit,
    validate_container_connectivity,
    validate_database_resource,
    validate_integration_exists,
)

logger = logging.getLogger(__name__)


class GLAuthCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self._container = self.unit.get_container(WORKLOAD_CONTAINER)

        self._k8s_client = Client(field_manager=self.app.name, namespace=self.model.name)
        self._configmap = ConfigMapResource(client=self._k8s_client, name=self.app.name)
        self._statefulset = StatefulSetResource(client=self._k8s_client, name=self.app.name)

        self._db_name = f"{self.model.name}_{self.app.name}"
        self.database = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=self._db_name,
            extra_user_roles="SUPERUSER",
        )

        self.service_patcher = KubernetesServicePatch(self, [("ldap", GLAUTH_LDAP_PORT)])

        self.loki_consumer = LogProxyConsumer(
            self,
            log_files=[str(LOG_FILE)],
            relation_name=LOKI_API_PUSH_INTEGRATION_NAME,
            container_name=WORKLOAD_CONTAINER,
        )
        self.metrics_endpoint = MetricsEndpointProvider(
            self, relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME
        )
        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.glauth_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(
            self.loki_consumer.on.promtail_digest_error,
            self._on_promtail_error,
        )

    @property
    def _pebble_layer(self) -> Layer:
        pebble_layer = {
            "summary": "GLAuth layer",
            "description": "pebble layer for GLAuth service",
            "services": {
                WORKLOAD_SERVICE: {
                    "override": "replace",
                    "summary": "GLAuth Operator layer",
                    "startup": "disabled",
                    "command": '/bin/sh -c "{} 2>&1 | tee {}"'.format(
                        GLAUTH_COMMANDS,
                        LOG_FILE,
                    ),
                }
            },
        }
        return Layer(pebble_layer)

    def _restart_glauth_service(self) -> None:
        try:
            self._container.restart(WORKLOAD_CONTAINER)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the service, please check the logs"
            )

    @validate_container_connectivity
    @validate_integration_exists(DATABASE_INTEGRATION_NAME)
    @validate_database_resource
    def _handle_event_update(self, event: HookEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring GLAuth container")

        self._update_glauth_config()
        self._container.add_layer(WORKLOAD_CONTAINER, self._pebble_layer, combine=True)

        self._restart_glauth_service()
        self.unit.status = ActiveStatus()

    def _fetch_database_relation_data(self) -> dict:
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
            "database_name": self._db_name,
        }

    def _render_config_file(self) -> str:
        with open("templates/glauth.cfg.j2", mode="r") as file:
            template = Template(file.read())

        rendered = template.render(
            db_info=self._fetch_database_relation_data(),
            ldap_port=GLAUTH_LDAP_PORT,
            base_dn=self.config.get("base_dn"),
        )
        return rendered

    @leader_unit
    def _update_glauth_config(self) -> None:
        conf = self._render_config_file()
        self._configmap.patch({"glauth.cfg": conf})

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

    @leader_unit
    def _on_remove(self, event: RemoveEvent) -> None:
        self._configmap.delete()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self._update_glauth_config()
        self._mount_glauth_config()
        self._container.add_layer(WORKLOAD_CONTAINER, self._pebble_layer, combine=True)
        self._restart_glauth_service()
        self.unit.status = ActiveStatus()

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self._handle_event_update(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self._handle_event_update(event)

    @validate_container_connectivity
    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        if not self._container.isdir(LOG_DIR):
            self._container.make_dir(path=LOG_DIR, make_parents=True)
            logger.debug(f"Created logging directory {LOG_DIR}")

        self._handle_event_update(event)

    def _on_promtail_error(self, event: PromtailDigestError) -> None:
        logger.error(event.message)


if __name__ == "__main__":
    main(GLAuthCharm)
