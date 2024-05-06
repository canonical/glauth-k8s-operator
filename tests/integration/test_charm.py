#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import pytest
from conftest import (
    CERTIFICATE_PROVIDER_APP,
    DB_APP,
    GLAUTH_APP,
    GLAUTH_CLIENT_APP,
    GLAUTH_IMAGE,
    extract_certificate_common_name,
)
from pytest_operator.plugin import OpsTest
from tester import ANY_CHARM

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    charm_lib_path = Path("lib/charms")
    any_charm_src_overwrite = {
        "any_charm.py": ANY_CHARM,
        "ldap.py": (charm_lib_path / "glauth_k8s/v0/ldap.py").read_text(),
        "certificate_transfer.py": (
            charm_lib_path / "certificate_transfer_interface/v0/certificate_transfer.py"
        ).read_text(),
    }

    await asyncio.gather(
        ops_test.model.deploy(
            DB_APP,
            channel="14/stable",
            trust=True,
        ),
        ops_test.model.deploy(
            CERTIFICATE_PROVIDER_APP,
            channel="stable",
            trust=True,
        ),
        ops_test.model.deploy(
            GLAUTH_CLIENT_APP,
            channel="beta",
            config={
                "src-overwrite": json.dumps(any_charm_src_overwrite),
                "python-packages": "pydantic ~= 2.0\njsonschema",
            },
        ),
    )

    charm_path = await ops_test.build_charm(".")
    await ops_test.model.deploy(
        str(charm_path),
        resources={"oci-image": GLAUTH_IMAGE},
        application_name=GLAUTH_APP,
        config={"starttls_enabled": True},
        trust=True,
        series="jammy",
    )

    await ops_test.model.integrate(GLAUTH_APP, CERTIFICATE_PROVIDER_APP)
    await ops_test.model.integrate(GLAUTH_APP, DB_APP)

    await ops_test.model.wait_for_idle(
        apps=[CERTIFICATE_PROVIDER_APP, DB_APP, GLAUTH_CLIENT_APP, GLAUTH_APP],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


def test_database_integration(
    ops_test: OpsTest,
    database_integration_data: Optional[dict],
) -> None:
    assert database_integration_data
    assert f"{ops_test.model_name}_{GLAUTH_APP}" == database_integration_data["database"]
    assert database_integration_data["password"]


def test_certification_integration(
    certificate_integration_data: Optional[dict],
) -> None:
    assert certificate_integration_data
    certificates = json.loads(certificate_integration_data["certificates"])
    certificate = certificates[0]["certificate"]
    assert "CN=ldap.glauth.com" == extract_certificate_common_name(certificate)


async def test_ldap_integration(
    ops_test: OpsTest,
    app_integration_data: Callable,
) -> None:
    await ops_test.model.integrate(
        f"{GLAUTH_CLIENT_APP}:ldap",
        f"{GLAUTH_APP}:ldap",
    )

    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP, GLAUTH_CLIENT_APP],
        status="active",
        timeout=1000,
    )

    ldap_integration_data = app_integration_data(
        GLAUTH_CLIENT_APP,
        "ldap",
    )
    assert ldap_integration_data
    assert ldap_integration_data["bind_dn"].startswith(
        f"cn={GLAUTH_CLIENT_APP},ou={ops_test.model_name}"
    )
    assert ldap_integration_data["bind_password_secret"].startswith("secret:")


async def test_certificate_transfer_integration(
    ops_test: OpsTest,
    unit_integration_data: Callable,
) -> None:
    await ops_test.model.integrate(
        f"{GLAUTH_CLIENT_APP}:send-ca-cert",
        f"{GLAUTH_APP}:send-ca-cert",
    )

    certificate_transfer_integration_data = unit_integration_data(
        GLAUTH_CLIENT_APP,
        GLAUTH_APP,
        "send-ca-cert",
    )
    assert certificate_transfer_integration_data


async def test_glauth_scale_up(ops_test: OpsTest) -> None:
    app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 3

    await app.scale(target_unit_num)

    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP],
        status="active",
        timeout=1000,
        wait_for_exact_units=target_unit_num,
    )


async def test_glauth_scale_down(ops_test: OpsTest) -> None:
    app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 1

    await app.scale(target_unit_num)
    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP],
        status="active",
        timeout=1000,
    )
