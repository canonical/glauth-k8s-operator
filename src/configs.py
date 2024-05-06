from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from constants import (
    GLAUTH_COMMANDS,
    LOG_FILE,
    POSTGRESQL_DSN_TEMPLATE,
    SERVER_CERT,
    SERVER_KEY,
    WORKLOAD_SERVICE,
)
from jinja2 import Template
from ops.pebble import Layer


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
    def load(cls, requirer: Any) -> "DatabaseConfig":
        if not (database_integrations := requirer.relations):
            return DatabaseConfig()

        integration_id = database_integrations[0].id
        integration_data = requirer.fetch_relation_data()[integration_id]

        return DatabaseConfig(
            endpoint=integration_data.get("endpoints"),
            database=requirer.database,
            username=integration_data.get("username"),
            password=integration_data.get("password"),
        )


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
    database_config: Optional[DatabaseConfig] = None
    starttls_config: Optional[StartTLSConfig] = None

    @property
    def content(self) -> str:
        return self.render()

    def render(self) -> str:
        with open("templates/glauth.cfg.j2", mode="r") as file:
            template = Template(file.read())

        database_config = self.database_config or DatabaseConfig()
        starttls_config = self.starttls_config or StartTLSConfig()
        rendered = template.render(
            base_dn=self.base_dn,
            database=asdict(database_config),
            starttls=asdict(starttls_config),
        )
        return rendered


pebble_layer = Layer(
    {
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
)
