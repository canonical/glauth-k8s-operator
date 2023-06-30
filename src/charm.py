#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for GLAuth."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.glauth_k8s.v0.ldap_public import LDAPProvides, LDAPRequestedEvent
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, PromtailDigestError
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops.charm import CharmBase, ConfigChangedEvent, HookEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, Layer

if TYPE_CHECKING:
    from ops.pebble import LayerDict

from users import UserManager

logger = logging.getLogger(__name__)
PEER_RELATION_NAME = "glauth-peers"


class GlauthK8SCharm(CharmBase):
    """Charmed GLAuth."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._container_name = "glauth"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = Path("/etc/config")
        self._config_file_path = self._config_dir_path / "glauth.cfg"

        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "database"
        self._db_plugin = "postgres.so"

        self._prometheus_scrape_relation_name = "metrics-endpoint"
        self._loki_push_api_relation_name = "logging"

        self._glauth_service_command = f"glauth -c {self._config_file_path}"
        self._log_dir = Path("/var/log")
        self._log_path = self._log_dir / "glauth.log"

        self._ingress_relation_name = "ingress"

        self.service_patcher = KubernetesServicePatch(self, [(self.app.name, self._ldap_port)])
        self.ingress = IngressPerAppRequirer(
            self,
            relation_name=self._ingress_relation_name,
            port=self._http_port,
            strip_prefix=True,
        )

        self.database = DatabaseRequires(
            self,
            relation_name=self._db_relation_name,
            database_name=self._db_name,
            extra_user_roles="SUPERUSER",
        )

        self.ldap_provider = LDAPProvides(self)
        self._ldap_users = UserManager(self, PEER_RELATION_NAME)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=self._prometheus_scrape_relation_name,
            jobs=[
                {
                    "metrics_path": "/metrics",
                    "static_configs": [
                        {
                            "targets": [f"*:{self._http_port}"],
                        }
                    ],
                }
            ],
        )

        self.loki_consumer = LogProxyConsumer(
            self,
            log_files=[str(self._log_path)],
            relation_name=self._loki_push_api_relation_name,
            container_name=self._container_name,
        )

        self.framework.observe(self.on.glauth_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)

        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        self.framework.observe(self.ldap_provider.on.ldap_requested, self._provide_ldap_auth)

        self.framework.observe(
            self.loki_consumer.on.promtail_digest_error,
            self._promtail_error,
        )

        # self.framework.observe(self.on.search_dn_action, self._on_search_dn_action)
        # self.framework.observe(self.on.list_all_dns_action, self._on_list_all_dns_action)

    @property
    def _glauth_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            return False
        return service.is_running()

    @property
    def _pebble_layer(self) -> Layer:
        pebble_layer: LayerDict = {
            "summary": "GLAuth Application layer",
            "description": "pebble layer for GLAuth service",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "GLAuth Operator layer",
                    "startup": "disabled",
                    "command": '/bin/sh -c "{} 2>&1 | tee {}"'.format(
                        self._glauth_service_command,
                        str(self._log_path),
                    ),
                }
            },
        }
        return Layer(pebble_layer)

    @property
    def _ldap_port(self) -> str:
        return self.config["ldap_port"]

    @property
    def _http_port(self) -> str:
        return self.config["http_port"]

    @property
    def _basedn(self) -> str:
        # baseDN example: "dc=glauth,dc=com"
        dn_input = self.config["base_dn"]
        list_dns = dn_input.split(",")
        list_dc = [f"dc={dn}" for dn in list_dns]
        return ",".join(list_dc)

    # finish later
    def _render_conf_file(self) -> str:
        """Render GLAuth configuration file."""
        with open("templates/glauth.cfg.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            db_info=self._get_database_relation_info(),
            ldap_port=self._ldap_port,
            http_port=self._http_port,
            postgres_plugin=self._db_plugin,
            ignore_capabilities=str(self.config["ignore_capabilities"]).lower(),
            limited_failed_binds=str(self.config["limit_failed_binds"]).lower(),
            number_of_failed_binds=self.config["number_of_failed_binds"],
            period_of_failed_binds=self.config["period_of_failed_binds"],
            block_failed_binds_for=self.config["block_failed_binds_for"],
            prune_source_tables_every=self.config["prune_source_table_every"],
            prune_sources_older_than=self.config["prune_sources_older_than"],
            baseDN=self._basedn,
            user_list=self._ldap_users.users,
        )
        return rendered

    def _get_database_relation_info(self) -> dict:
        """Get database info from relation data bag."""
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
            "database_name": self._db_name,
        }

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to glauth container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to glauth container")
            return

        self.unit.status = MaintenanceStatus("Configuring resources")
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)

        if not self.model.relations[self._db_relation_name]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            event.defer()
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            event.defer()
            return

        self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)
        try:
            self._container.restart(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to restart, please consult the logs")
            return

        self.unit.status = ActiveStatus()

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        # Necessary directory for log forwarding
        if not self._container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("Waiting to connect to glauth container")
            return
        if not self._container.isdir(str(self._log_dir)):
            self._container.make_dir(path=str(self._log_dir), make_parents=True)
            logger.info(f"Created directory {self._log_dir}")

        self._handle_status_update_config(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._handle_status_update_config(event)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to GLAuth container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to glauth container")
            return

        self.unit.status = MaintenanceStatus(
            "Configuring container and resources for database connection"
        )

        try:
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for glauth service")
            logger.info("GLAuth service is absent. Deferring database created event.")
            return

        logger.info("Updating GLAuth config and restarting service")
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
        self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)

        self._container.start(self._container_name)
        self.unit.status = ActiveStatus()

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event Handler for database changed event."""
        self._handle_status_update_config(event)

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("The GLAuth ingress URL: %s", event.url)
        self._handle_status_update_config(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("GLAuth no longer has ingress")
        self._handle_status_update_config(event)

    def _provide_ldap_auth(self, event: LDAPRequestedEvent) -> None:
        logger.info("Sending ldap accessibility info")

        relationid = event.relation.id
        endpoint = f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{self._ldap_port}"
        distinguished_name = event.distinguished_name
        (username, password) = self._ldap_users.generate_user(
            "ldap", relationid, distinguished_name
        )
        if (not username) or (not password):
            """User Generation Has Failed"""
            logger.info("Cannot generate GLAuth User.")
            self.unit.status = BlockedStatus("Failed to generate GLAuth User")
            return

        """Pushing new user into configuration file. GLAuth uses hot reloading for users"""
        self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)

        self.ldap_provider.set_ldap_access(
            relationid, distinguished_name, endpoint, username, password
        )

    def _promtail_error(self, event: PromtailDigestError) -> None:
        logger.error(event.message)


if __name__ == "__main__":
    main(GlauthK8SCharm)
