#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
GLAUTH_APP = METADATA["name"]
GLAUTH_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
DB_APP = "postgresql-k8s"


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        "postgresql-k8s",
        channel="14/stable",
        trust=True,
    )
    charm_path = await ops_test.build_charm(".")
    await ops_test.model.deploy(
        str(charm_path),
        resources={"oci-image": GLAUTH_IMAGE},
        application_name=GLAUTH_APP,
        trust=True,
        series="jammy",
    )
    await ops_test.model.integrate(GLAUTH_APP, DB_APP)

    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP, DB_APP],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


async def test_glauth_scale_up(ops_test: OpsTest) -> None:
    app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 3

    await app.scale(target_unit_num)

    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP],
        status="active",
        raise_on_blocked=True,
        timeout=600,
        wait_for_exact_units=target_unit_num,
    )


async def test_glauth_scale_down(ops_test: OpsTest) -> None:
    app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 1

    await app.scale(target_unit_num)
    await ops_test.model.wait_for_idle(
        apps=[GLAUTH_APP],
        status="active",
        timeout=300,
    )
