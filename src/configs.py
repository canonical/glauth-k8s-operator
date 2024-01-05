from dataclasses import asdict, dataclass
from typing import Any, Optional

from constants import GLAUTH_COMMANDS, LOG_FILE, POSTGRESQL_DSN_TEMPLATE, WORKLOAD_SERVICE
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
class ConfigFile:
    base_dn: Optional[str] = None
    database_config: Optional[DatabaseConfig] = None

    @property
    def content(self) -> str:
        return self.render()

    def render(self) -> str:
        with open("templates/glauth.cfg.j2", mode="r") as file:
            template = Template(file.read())

        database_config = self.database_config or DatabaseConfig()
        rendered = template.render(
            base_dn=self.base_dn,
            database=asdict(database_config),
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
