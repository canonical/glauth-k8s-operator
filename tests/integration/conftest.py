# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import os
import re
from base64 import b64decode
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Optional

import aiofiles
import ldap.ldapobject
import psycopg
import pytest_asyncio
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
TRAEFIK_CHARM = "traefik-k8s"
CERTIFICATE_PROVIDER_APP = "self-signed-certificates"
DB_APP = "postgresql-k8s"
GLAUTH_PROXY = "ldap-proxy"
GLAUTH_APP = METADATA["name"]
GLAUTH_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
GLAUTH_CLIENT_APP = "any-charm"
INGRESS_APP = "ingress"
LDAPS_INGRESS_APP = "ldaps-ingress"
JUJU_SECRET_ID_REGEX = re.compile(r"secret:(?://[a-f0-9-]+/)?(?P<secret_id>[a-zA-Z0-9]+)")
INGRESS_URL_REGEX = re.compile(r"url:\s*(?P<ingress_url>\d{1,3}(?:\.\d{1,3}){3}:\d+)")


@contextmanager
def ldap_connection(uri: str, bind_dn: str, bind_password: str) -> ldap.ldapobject.LDAPObject:
    conn = ldap.initialize(uri)
    try:
        conn.simple_bind_s(bind_dn, bind_password)
        yield conn
    finally:
        conn.unbind_s()


def extract_certificate_common_name(certificate: str) -> Optional[str]:
    cert_data = certificate.encode()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    if not (rdns := cert.subject.rdns):
        return None

    return rdns[0].rfc4514_string()


def extract_certificate_sans(certificate: str) -> list[str]:
    cert_data = certificate.encode()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    sans = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    domains = sans.value.get_values_for_type(x509.DNSName)
    ips = [str(ip) for ip in sans.value.get_values_for_type(x509.IPAddress)]
    return domains + ips


async def get_secret(ops_test: OpsTest, secret_id: str) -> dict:
    show_secret_cmd = f"show-secret {secret_id} --reveal".split()
    _, stdout, _ = await ops_test.juju(*show_secret_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[secret_id]


async def get_unit_data(ops_test: OpsTest, unit_name: str) -> dict:
    show_unit_cmd = f"show-unit {unit_name}".split()
    _, stdout, _ = await ops_test.juju(*show_unit_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


async def get_integration_data(
    ops_test: OpsTest, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    data = await get_unit_data(ops_test, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


async def get_app_integration_data(
    ops_test: OpsTest,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


async def get_unit_integration_data(
    ops_test: OpsTest,
    app_name: str,
    remote_app_name: str,
    integration_name: str,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name)
    return data["related-units"][f"{remote_app_name}/0"]["data"] if data else None


@pytest_asyncio.fixture
async def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test)


@pytest_asyncio.fixture
async def unit_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_unit_integration_data, ops_test)


@pytest_asyncio.fixture
async def ldap_integration_data(
    app_integration_data: Callable, ldap_client_app_name: str
) -> Optional[dict]:
    return await app_integration_data(ldap_client_app_name, "ldap")


@pytest_asyncio.fixture
async def database_integration_data(ops_test: OpsTest, app_integration_data: Callable) -> dict:
    database_integration_data = await app_integration_data(GLAUTH_APP, "pg-database") or {}

    db_credentials = await ops_test.model.list_secrets(
        filter={"uri": database_integration_data["secret-user"]},
        show_secrets=True,
    )
    db_credential = next(iter(db_credentials), None)
    assert db_credential
    decoded_db_credentials = {
        field: b64decode(db_credential.value.data[field]).decode("utf-8")
        for field in ("username", "password")
    }

    return {**database_integration_data, **decoded_db_credentials}


@pytest_asyncio.fixture
async def certificate_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(GLAUTH_APP, "certificates")


@pytest_asyncio.fixture
async def ingress_per_unit_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(GLAUTH_APP, "ingress")


@pytest_asyncio.fixture
async def ldaps_ingress_per_unit_integration_data(
    app_integration_data: Callable,
) -> Optional[dict]:
    return await app_integration_data(GLAUTH_APP, "ldaps-ingress")


@pytest_asyncio.fixture
async def ingress_url(ingress_per_unit_integration_data: Optional[dict]) -> Optional[str]:
    if not ingress_per_unit_integration_data:
        return None

    ingress = ingress_per_unit_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress url not found in ingress per unit integration data"

    return matched.group("ingress_url")


@pytest_asyncio.fixture
async def ldaps_ingress_url(
    ldaps_ingress_per_unit_integration_data: Optional[dict],
) -> Optional[str]:
    if not ldaps_ingress_per_unit_integration_data:
        return None

    ingress = ldaps_ingress_per_unit_integration_data["ingress"]
    matched = INGRESS_URL_REGEX.search(ingress)
    assert matched is not None, "ingress url not found in ldaps ingress per unit integration data"

    return matched.group("ingress_url")


@pytest_asyncio.fixture
async def ingress_ip(ingress_url: Optional[str]) -> Optional[str]:
    if not ingress_url:
        return None

    ingress_ip, *_ = ingress_url.rsplit(sep=":", maxsplit=1)
    return ingress_ip


@pytest_asyncio.fixture
async def ldaps_ingress_ip(ldaps_ingress_url: Optional[str]) -> Optional[str]:
    if not ldaps_ingress_url:
        return None

    ingress_ip, *_ = ldaps_ingress_url.rsplit(sep=":", maxsplit=1)
    return ingress_ip


@pytest_asyncio.fixture
async def ldap_configurations(
    ops_test: OpsTest, ldap_integration_data: Optional[dict]
) -> Optional[tuple[str, ...]]:
    if not ldap_integration_data:
        return None

    base_dn = ldap_integration_data["base_dn"]
    bind_dn = ldap_integration_data["bind_dn"]
    bind_password_secret: str = ldap_integration_data["bind_password_secret"]

    matched = JUJU_SECRET_ID_REGEX.match(bind_password_secret)
    assert matched is not None, "bind password secret id should be valid"

    bind_password = await get_secret(ops_test, matched.group("secret_id"))

    return base_dn, bind_dn, bind_password["content"]["password"]


async def unit_address(ops_test: OpsTest, *, app_name: str, unit_num: int = 0) -> str:
    status = await ops_test.model.get_status()
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest_asyncio.fixture
async def database_address(ops_test: OpsTest) -> str:
    return await unit_address(ops_test, app_name=DB_APP)


@pytest_asyncio.fixture
async def initialize_database(database_integration_data: dict, database_address: str) -> None:
    assert database_integration_data, "database_integration_data should be ready"

    db_connection_params = {
        "dbname": database_integration_data["database"],
        "user": database_integration_data["username"],
        "password": database_integration_data["password"],
        "host": database_address,
        "port": 5432,
    }

    async with await psycopg.AsyncConnection.connect(**db_connection_params) as conn:
        async with conn.cursor() as cursor:
            async with aiofiles.open("tests/integration/db.sql", "rb") as f:
                statements = await f.read()

            await cursor.execute(statements)
            await conn.commit()


@pytest_asyncio.fixture(scope="module")
def run_action(ops_test: OpsTest) -> Callable:
    async def _run_action(
        application_name: str, action_name: str, **params: Any
    ) -> dict[str, str]:
        app = ops_test.model.applications[application_name]
        action = await app.units[0].run_action(action_name, **params)
        await action.wait()
        return action.results

    return _run_action


@pytest_asyncio.fixture(scope="module")
async def local_charm(ops_test: OpsTest) -> Path:
    # in GitHub CI, charms are built with charmcraftcache and uploaded to $CHARM_PATH
    charm = os.getenv("CHARM_PATH")
    if not charm:
        # fall back to build locally - required when run outside of GitHub CI
        charm = await ops_test.build_charm(".")
    return charm
