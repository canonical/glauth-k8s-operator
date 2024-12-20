# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from charms.glauth_k8s.v0.ldap import LdapProviderData, LdapRequirer
from jinja2 import Template
from ops.pebble import Layer

from constants import (
    GLAUTH_COMMANDS,
    POSTGRESQL_DSN_TEMPLATE,
    SERVER_CERT,
    SERVER_KEY,
    WORKLOAD_SERVICE,
)


@dataclass
class DatabaseConfig:
    endpoint: Optional[str] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    @classmethod
    def load(cls, requirer: Any) -> Optional["DatabaseConfig"]:
        if not (database_integrations := requirer.relations):
            return None

        integration_id = database_integrations[0].id
        integration_data = requirer.fetch_relation_data()[integration_id]

        return DatabaseConfig(
            endpoint=integration_data.get("endpoints"),
            database=requirer.database,
            username=integration_data.get("username"),
            password=integration_data.get("password"),
        )


@dataclass
class LdapServerConfig:
    ldap_server: Optional[LdapProviderData] = None

    @classmethod
    def load(cls, requirer: LdapRequirer) -> Optional["LdapServerConfig"]:
        if not (ldap_servers := requirer.consume_ldap_relation_data()):
            return None

        return LdapServerConfig(ldap_servers)


@dataclass
class StartTLSConfig:
    enabled: bool = True
    tls_key: Path = SERVER_KEY
    tls_cert: Path = SERVER_CERT

    @classmethod
    def load(cls, config: Mapping[str, Any]) -> "StartTLSConfig":
        return StartTLSConfig(
            enabled=config.get("starttls_enabled", True),
        )


@dataclass
class ConfigFile:
    base_dn: Optional[str] = None
    anonymousdse_enabled: bool = False
    database_config: Optional[DatabaseConfig] = None
    starttls_config: Optional[StartTLSConfig] = None
    ldap_servers_config: Optional[LdapServerConfig] = None

    @property
    def content(self) -> str:
        return self.render()

    def render(self) -> str:
        with open("templates/glauth.cfg.j2", mode="r") as file:
            template = Template(file.read())

        database_config = asdict(self.database_config) if self.database_config else None
        ldap_servers_config = self.ldap_servers_config
        starttls_config = asdict(self.starttls_config) if self.starttls_config else None
        rendered = template.render(
            base_dn=self.base_dn,
            anonymousdse_enabled=self.anonymousdse_enabled,
            database=database_config,
            ldap_servers=ldap_servers_config,
            starttls=starttls_config,
        )
        return rendered


pebble_layer = Layer({
    "summary": "GLAuth layer",
    "description": "pebble layer for GLAuth service",
    "services": {
        WORKLOAD_SERVICE: {
            "override": "replace",
            "summary": "GLAuth Operator layer",
            "startup": "disabled",
            "command": GLAUTH_COMMANDS,
        }
    },
})
