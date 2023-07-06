#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
POSTGRES = "postgresql-k8s"
TRAEFIK = "traefik-k8s"
TRAEFIK_APP = "traefik"


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def get_app_address(ops_test: OpsTest, app_name: str) -> str:
    """Get address of an app."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["public-address"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm-under-test and deploy it.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(
        POSTGRES,
        channel="14/stable",
        trust=True,
    )
    charm = await ops_test.build_charm(".")
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
    await ops_test.model.deploy(
        charm, resources=resources, application_name=APP_NAME, trust=True, series="jammy"
    )
    await ops_test.model.add_relation(APP_NAME, POSTGRES)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, POSTGRES],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )


async def test_ingress_relation(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        TRAEFIK,
        application_name=TRAEFIK_APP,
        channel="latest/edge",
        config={"external_hostname": "some_hostname"},
    )
    await ops_test.model.add_relation(f"{APP_NAME}:ingress", TRAEFIK_APP)

    await ops_test.model.wait_for_idle(
        apps=[TRAEFIK_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )


async def test_has_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach glauth
    public_address = await get_unit_address(ops_test, TRAEFIK_APP, 0)

    resp = requests.get(
        f"http://{public_address}/{ops_test.model.name}-{APP_NAME}/.well-known/ory/webauthn.js"
    )

    assert resp.status_code == 200


async def test_glauth_scale_up(ops_test: OpsTest) -> None:
    """Check that glauth-k8s works after it is scaled up."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(3)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_exact_units=3,
    )