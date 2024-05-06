# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import subprocess
from pathlib import Path
from typing import Callable, Optional

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CERTIFICATE_PROVIDER_APP = "self-signed-certificates"
DB_APP = "postgresql-k8s"
GLAUTH_APP = METADATA["name"]
GLAUTH_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
GLAUTH_CLIENT_APP = "any-charm"


def extract_certificate_common_name(certificate: str) -> Optional[str]:
    cert_data = certificate.encode()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    if not (rdns := cert.subject.rdns):
        return None

    return rdns[0].rfc4514_string()


def get_unit_data(unit_name: str, model_name: str) -> dict:
    res = subprocess.run(
        ["juju", "show-unit", unit_name, "-m", model_name],
        check=True,
        text=True,
        capture_output=True,
    )
    cmd_output = yaml.safe_load(res.stdout)
    return cmd_output[unit_name]


def get_integration_data(model_name: str, app_name: str, integration_name: str) -> Optional[dict]:
    unit_data = get_unit_data(f"{app_name}/0", model_name)
    return next(
        (
            integration
            for integration in unit_data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    model_name: str, app_name: str, integration_name: str
) -> Optional[dict]:
    data = get_integration_data(model_name, app_name, integration_name)
    return data["application-data"] if data else None


def get_unit_integration_data(
    model_name: str, app_name: str, remote_app_name: str, integration_name: str
) -> Optional[dict]:
    data = get_integration_data(model_name, app_name, integration_name)
    return data["related-units"][f"{remote_app_name}/0"]["data"] if data else None


@pytest.fixture
def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test.model_name)


@pytest.fixture
def unit_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_unit_integration_data, ops_test.model_name)


@pytest.fixture
def database_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return app_integration_data(GLAUTH_APP, "pg-database")


@pytest.fixture
def certificate_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return app_integration_data(GLAUTH_APP, "certificates")
