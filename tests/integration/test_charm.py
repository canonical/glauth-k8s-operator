#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import ldap
import pytest
from conftest import (
    CERTIFICATE_PROVIDER_APP,
    DB_APP,
    GLAUTH_APP,
    GLAUTH_CLIENT_APP,
    GLAUTH_IMAGE,
    GLAUTH_PROXY,
    INGRESS_APP,
    LDAPS_INGRESS_APP,
    TRAEFIK_CHARM,
    extract_certificate_common_name,
    extract_certificate_sans,
    ldap_connection,
)
from pytest_operator.plugin import OpsTest
from tester import ANY_CHARM

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
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
            TRAEFIK_CHARM,
            application_name=INGRESS_APP,
            channel="latest/stable",
            trust=True,
        ),
        ops_test.model.deploy(
            TRAEFIK_CHARM,
            application_name=LDAPS_INGRESS_APP,
            channel="latest/stable",
            trust=True,
        ),
    )

    charm_path = await ops_test.build_charm(".")
    await ops_test.model.deploy(
        str(charm_path),
        resources={"oci-image": GLAUTH_IMAGE},
        application_name=GLAUTH_APP,
        config={"starttls_enabled": True, "ldaps_enabled": True},
        trust=True,
        series="jammy",
    )
    await ops_test.model.deploy(
        str(charm_path),
        resources={"oci-image": GLAUTH_IMAGE},
        application_name=GLAUTH_PROXY,
        config={"starttls_enabled": True, "ldaps_enabled": True},
        trust=True,
        series="jammy",
    )

    await ops_test.model.integrate(GLAUTH_APP, CERTIFICATE_PROVIDER_APP)
    await ops_test.model.integrate(GLAUTH_PROXY, CERTIFICATE_PROVIDER_APP)
    await ops_test.model.integrate(GLAUTH_APP, DB_APP)
    await ops_test.model.integrate(f"{GLAUTH_PROXY}:ldap-client", f"{GLAUTH_APP}:ldap")
    await ops_test.model.integrate(f"{GLAUTH_APP}:ingress", f"{INGRESS_APP}:ingress-per-unit")
    await ops_test.model.integrate(
        f"{GLAUTH_APP}:ldaps-ingress", f"{LDAPS_INGRESS_APP}:ingress-per-unit"
    )

    await ops_test.model.wait_for_idle(
        apps=[
            CERTIFICATE_PROVIDER_APP,
            DB_APP,
            GLAUTH_APP,
            GLAUTH_PROXY,
            INGRESS_APP,
            LDAPS_INGRESS_APP,
        ],
        status="active",
        raise_on_blocked=False,
        timeout=10 * 60,
    )


async def test_database_integration(
    ops_test: OpsTest,
    database_integration_data: dict,
) -> None:
    assert database_integration_data
    assert f"{ops_test.model_name}_{GLAUTH_APP}" == database_integration_data["database"]
    assert database_integration_data["username"]
    assert database_integration_data["password"]


async def test_ingress_per_unit_integration(ingress_url: Optional[str]) -> None:
    assert ingress_url, "Ingress url not found in the ingress-per-unit integration"


async def test_ldaps_ingress_per_unit_integration(ldaps_ingress_url: Optional[str]) -> None:
    assert ldaps_ingress_url, "LDAPS Ingress url not found in the ingress-per-unit integration"


async def test_certification_integration(
    ops_test: OpsTest,
    certificate_integration_data: Optional[dict],
    ingress_ip: Optional[str],
    ldaps_ingress_ip: Optional[str],
) -> None:
    assert certificate_integration_data
    certificates = json.loads(certificate_integration_data["certificates"])
    certificate = certificates[0]["certificate"]
    assert (
        f"CN={GLAUTH_APP}.{ops_test.model_name}.svc.cluster.local"
        == extract_certificate_common_name(certificate)
    )
    assert ingress_ip in extract_certificate_sans(certificate)
    assert ldaps_ingress_ip in extract_certificate_sans(certificate)


async def test_ldap_client_integration(
    ops_test: OpsTest,
    app_integration_data: Callable,
) -> None:
    ldap_client_integration_data = await app_integration_data(
        GLAUTH_PROXY,
        "ldap-client",
    )
    assert ldap_client_integration_data
    assert ldap_client_integration_data["bind_dn"].startswith(
        f"cn={GLAUTH_PROXY},ou={ops_test.model_name}"
    )
    assert ldap_client_integration_data["bind_password_secret"].startswith("secret:")


class GlauthClientTestSuite:
    @pytest.fixture()
    def ldap_client_app_name(self, pydantic_version: str) -> str:
        return "".join([GLAUTH_CLIENT_APP, pydantic_version.replace(".", "")])

    async def test_deploy_client_app(
        self, ops_test: OpsTest, pydantic_version: str, ldap_client_app_name: str
    ) -> None:
        charm_lib_path = Path("lib/charms")
        any_charm_src_overwrite = {
            "any_charm.py": ANY_CHARM,
            "ldap_interface_lib.py": (charm_lib_path / "glauth_k8s/v0/ldap.py").read_text(),
            "certificate_transfer.py": (
                charm_lib_path / "certificate_transfer_interface/v0/certificate_transfer.py"
            ).read_text(),
        }
        await ops_test.model.deploy(
            GLAUTH_CLIENT_APP,
            application_name=ldap_client_app_name,
            channel="beta",
            config={
                "src-overwrite": json.dumps(any_charm_src_overwrite),
                "python-packages": f"pydantic ~= {pydantic_version}\njsonschema\nldap3",
            },
        )

        await ops_test.model.wait_for_idle(
            apps=[ldap_client_app_name],
            status="active",
            raise_on_blocked=False,
            timeout=5 * 60,
        )

    async def test_ldap_integration(
        self,
        ops_test: OpsTest,
        app_integration_data: Callable,
        ldap_client_app_name: str,
    ) -> None:
        await ops_test.model.integrate(
            f"{ldap_client_app_name}:ldap",
            f"{GLAUTH_APP}:ldap",
        )

        await ops_test.model.wait_for_idle(
            apps=[GLAUTH_APP, ldap_client_app_name],
            status="active",
            timeout=5 * 60,
        )

        integration_data = await app_integration_data(
            ldap_client_app_name,
            "ldap",
        )
        assert integration_data
        assert integration_data["bind_dn"].startswith(
            f"cn={ldap_client_app_name},ou={ops_test.model_name}"
        )
        assert integration_data["bind_password_secret"].startswith("secret:")

    async def test_certificate_transfer_integration(
        self,
        ops_test: OpsTest,
        unit_integration_data: Callable,
        ingress_ip: Optional[str],
        ldaps_ingress_ip: Optional[str],
        ldap_client_app_name: str,
    ) -> None:
        await ops_test.model.integrate(
            f"{ldap_client_app_name}:send-ca-cert",
            f"{GLAUTH_APP}:send-ca-cert",
        )

        await ops_test.model.wait_for_idle(
            apps=[GLAUTH_APP, ldap_client_app_name],
            status="active",
            timeout=5 * 60,
        )

        certificate_transfer_integration_data = await unit_integration_data(
            ldap_client_app_name,
            GLAUTH_APP,
            "send-ca-cert",
        )
        assert certificate_transfer_integration_data, (
            "Certificate transfer integration data is empty."
        )

        for key in ("ca", "certificate", "chain"):
            assert key in certificate_transfer_integration_data, (
                f"Missing '{key}' in certificate transfer integration data."
            )

        chain = certificate_transfer_integration_data["chain"]
        assert isinstance(json.loads(chain), list), "Invalid certificate chain."

        certificate = certificate_transfer_integration_data["certificate"]
        assert (
            f"CN={GLAUTH_APP}.{ops_test.model_name}.svc.cluster.local"
            == extract_certificate_common_name(certificate)
        )
        assert ingress_ip in extract_certificate_sans(certificate)
        assert ldaps_ingress_ip in extract_certificate_sans(certificate)

    @pytest.mark.skip(
        reason="glauth cannot scale up due to the traefik-k8s issue: https://github.com/canonical/traefik-k8s-operator/issues/406",
    )
    async def test_glauth_scale_up(self, ops_test: OpsTest) -> None:
        app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 2

        await app.scale(target_unit_num)

        await ops_test.model.wait_for_idle(
            apps=[GLAUTH_APP],
            status="active",
            timeout=5 * 60,
            wait_for_exact_units=target_unit_num,
        )

    @pytest.mark.skip(
        reason="cert_handler is bugged, remove this once it is fixed or when we throw it away..."
    )
    async def test_glauth_scale_down(self, ops_test: OpsTest) -> None:
        app, target_unit_num = ops_test.model.applications[GLAUTH_APP], 1

        await app.scale(target_unit_num)
        await ops_test.model.wait_for_idle(
            apps=[GLAUTH_APP],
            status="active",
            timeout=5 * 60,
        )

    async def test_ldap_search_operation(
        self,
        initialize_database: None,
        ldap_configurations: Optional[tuple[str, ...]],
        ingress_url: Optional[str],
    ) -> None:
        assert ldap_configurations, "LDAP configuration should be ready"
        base_dn, bind_dn, bind_password = ldap_configurations

        ldap_uri = f"ldap://{ingress_url}"
        with ldap_connection(uri=ldap_uri, bind_dn=bind_dn, bind_password=bind_password) as conn:
            res = conn.search_s(
                base=base_dn,
                scope=ldap.SCOPE_SUBTREE,
                filterstr="(cn=hackers)",
            )

        assert res[0], "Can't find user 'hackers'"
        dn, _ = res[0]
        assert dn == f"cn=hackers,ou=superheros,ou=users,{base_dn}"

        with ldap_connection(
            uri=ldap_uri, bind_dn=f"cn=serviceuser,ou=svcaccts,{base_dn}", bind_password="mysecret"
        ) as conn:
            res = conn.search_s(
                base=base_dn,
                scope=ldap.SCOPE_SUBTREE,
                filterstr="(cn=johndoe)",
            )

        assert res[0], "User 'johndoe' can't be found by using 'serviceuser' as bind DN"
        dn, _ = res[0]
        assert dn == f"cn=johndoe,ou=svcaccts,ou=users,{base_dn}"

        with ldap_connection(
            uri=ldap_uri, bind_dn=f"cn=hackers,ou=superheros,{base_dn}", bind_password="dogood"
        ) as conn:
            user4 = conn.search_s(
                base=f"ou=superheros,{base_dn}", scope=ldap.SCOPE_SUBTREE, filterstr="(cn=user4)"
            )

        assert user4[0], "User 'user4' can't be found by using 'hackers' as bind DN"
        dn, _ = user4[0]
        assert dn == f"cn=user4,ou=superheros,{base_dn}"

        with (
            ldap_connection(
                uri=ldap_uri, bind_dn=f"cn=hackers,ou=superheros,{base_dn}", bind_password="dogood"
            ) as conn,
            pytest.raises(ldap.INSUFFICIENT_ACCESS),
        ):
            conn.search_s(base=base_dn, scope=ldap.SCOPE_SUBTREE, filterstr="(cn=user4)")

    async def test_ldap_starttls_operation(
        self,
        ldap_configurations: Optional[tuple[str, ...]],
        run_action: Callable,
        ldap_client_app_name: str,
    ) -> None:
        assert ldap_configurations, "LDAP configuration should be ready"
        base_dn, *_ = ldap_configurations

        res = await run_action(
            ldap_client_app_name, "rpc", method="starttls_operation", cn="hackers"
        )
        ret = json.loads(res["return"])
        assert ret, "Can't find user 'hackers'"
        assert ret["dn"] == f"cn=hackers,ou=superheros,ou=users,{base_dn}"

    async def test_ldaps_operation(
        self,
        ldap_configurations: Optional[tuple[str, ...]],
        run_action: Callable,
        ldap_client_app_name: str,
    ) -> None:
        assert ldap_configurations, "LDAP configuration should be ready"
        base_dn, *_ = ldap_configurations

        res = await run_action(ldap_client_app_name, "rpc", method="ldaps_operation", cn="hackers")
        ret = json.loads(res["return"])
        assert ret, "Can't find user 'hackers'"
        assert ret["dn"] == f"cn=hackers,ou=superheros,ou=users,{base_dn}"

    async def test_remove_client_app(self, ops_test: OpsTest, ldap_client_app_name: str) -> None:
        await ops_test.model.remove_application(ldap_client_app_name, force=True)
        await ops_test.model.wait_for_idle(
            apps=[GLAUTH_APP],
            status="active",
            raise_on_blocked=False,
            timeout=5 * 60,
        )


class TestGlauthClientPydanticV2(GlauthClientTestSuite):
    @pytest.fixture()
    def pydantic_version(self) -> str:
        return "2.0"


class TestGlauthClientPydanticV1(GlauthClientTestSuite):
    @pytest.fixture()
    def pydantic_version(self) -> str:
        return "1.0"
