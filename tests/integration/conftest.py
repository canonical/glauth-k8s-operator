# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import secrets
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator, Optional, Tuple

import jubilant
import psycopg
import pytest
import yaml
from integration.constants import (
    DB_APP,
    GLAUTH_APP,
    GLAUTH_CLIENT_APP,
    GLAUTH_PROXY,
)
from integration.utils import (
    get_app_integration_data,
    get_unit_address,
    get_unit_data,
    juju_model_factory,
)

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control."""
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection based on deployment and model management."""
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options."""
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-glauth-{secrets.token_hex(4)}"

    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            log = juju_.debug_log(limit=1000)
            print(log, end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0
        if not keep_model:
            with suppress(jubilant.CLIError):
                args = [
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "600s",
                ]
                juju_.cli(*args, include_model=False)


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the path to the charm-under-test."""
    # in GitHub CI, charms are built with charmcraftcache and uploaded to
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        subprocess.run(["charmcraft", "pack"], check=True)
        if not (charms := list(Path(".").glob("*.charm"))):
            raise RuntimeError("Charm not found and build failed")
        charm = charms[0].absolute()
    return Path(charm)


@pytest.fixture
def database_integration_data(juju: jubilant.Juju, app_integration_data: Callable) -> dict | None:
    data = app_integration_data(GLAUTH_APP, "pg-database")

    secret_uri = data["secret-user"]
    secret_content = juju.show_secret(secret_uri, reveal=True).content
    decoded_db_credentials = {field: (secret_content[field]) for field in ("username", "password")}
    return {**data, **decoded_db_credentials}


@pytest.fixture
def certificate_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(GLAUTH_APP, "certificates")


@pytest.fixture
def ingress_ip(ingress_url: str) -> str:
    return ingress_url.split(":")[0]


@pytest.fixture
def ldaps_ingress_ip(ldaps_ingress_url: str) -> str:
    return ldaps_ingress_url.split(":")[0]


@pytest.fixture
def ingress_url(app_integration_data: Callable) -> str | None:
    # Example:
    # data = {'ingress': 'glauth-k8s/0:\n  url: 10.64.140.43:3893\n'}
    data = app_integration_data(GLAUTH_APP, "ingress")
    ingress = data.get("ingress")
    ingress_data = yaml.safe_load(ingress)
    ingress_data = list(ingress_data.values())[0]
    return ingress_data.get("url")


@pytest.fixture
def ldaps_ingress_url(app_integration_data: Callable) -> str | None:
    # Example:
    # data = {'ingress': 'glauth-k8s/0:\n  url: 10.64.140.43:3893\n'}
    data = app_integration_data(GLAUTH_APP, "ldaps-ingress")
    ingress = data.get("ingress")
    ingress_data = yaml.safe_load(ingress)
    ingress_data = list(ingress_data.values())[0]
    return ingress_data.get("url")


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    def _get_data(app_name: str, integration_name: str, unit_num: int = 0) -> dict | None:
        return get_app_integration_data(juju, app_name, integration_name, unit_num)

    return _get_data


@pytest.fixture
def unit_integration_data_func(juju: jubilant.Juju) -> Callable:
    def _get_data(
        app_name: str, remote_app_name: str, integration_name: str, unit_num: int = 0
    ) -> dict | None:
        unit_data = get_unit_data(juju, f"{app_name}/{unit_num}")
        for rel in unit_data.get("relation-info", []):
            if rel["endpoint"] == integration_name:
                for related_unit, data in rel.get("related-units", {}).items():
                    if related_unit.startswith(remote_app_name):
                        return data.get("data")
        return None

    return _get_data


@pytest.fixture
def initialize_database(juju: jubilant.Juju, database_integration_data: dict) -> None:
    if not database_integration_data:
        pytest.skip("database integration data not available")

    # Get DB address. Assuming pod IP is reachable.
    try:
        database_address = get_unit_address(juju, DB_APP, 0)
    except Exception:
        # Fallback if address cannot be retrieved
        database_address = None

    if not database_address:
        pytest.skip("Cannot retrieve DB address for initialization")

    db_connection_params = {
        "dbname": database_integration_data["database"],
        "user": database_integration_data["username"],
        "password": database_integration_data["password"],
        "host": database_address,
        "port": 5432,
    }

    with psycopg.connect(**db_connection_params) as conn:
        with conn.cursor() as cursor:
            sql_file = Path("tests/integration/db.sql")
            if sql_file.exists():
                statements = sql_file.read_text()
                cursor.execute(statements)
                conn.commit()


@pytest.fixture
def ldap_configurations(
    juju: jubilant.Juju, app_integration_data: Callable
) -> Optional[Tuple[str, str, str]]:
    data = app_integration_data(GLAUTH_PROXY, "ldap-client")
    if not data:
        return None
    secret_uri = data["bind_password_secret"]
    secret_content = juju.show_secret(secret_uri, reveal=True).content
    bind_password = secret_content["password"]
    return (data["base_dn"], data["bind_dn"], bind_password)


@pytest.fixture
def ldap_client_app_name(pydantic_version: str) -> str:
    return "".join([GLAUTH_CLIENT_APP, pydantic_version.replace(".", "")])
