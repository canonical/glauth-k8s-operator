#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path
from typing import Callable, Optional

import jubilant
import ldap
import pytest
from integration.constants import (
    CERTIFICATE_PROVIDER_APP,
    DB_APP,
    GLAUTH_APP,
    GLAUTH_CLIENT_APP,
    GLAUTH_IMAGE,
    GLAUTH_PROXY,
    INGRESS_APP,
    LDAPS_INGRESS_APP,
    TRAEFIK_CHARM,
)
from integration.tester import ANY_CHARM
from integration.utils import (
    all_active,
    and_,
    any_error,
    extract_certificate_common_name,
    extract_certificate_sans,
    ldap_connection,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    # Deploy dependencies
    juju.deploy(
        DB_APP,
        channel="14/stable",
        trust=True,
    )
    juju.deploy(
        CERTIFICATE_PROVIDER_APP,
        channel="latest/stable",
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=INGRESS_APP,
        channel="latest/stable",
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=LDAPS_INGRESS_APP,
        channel="latest/stable",
        trust=True,
    )

    # Deploy GLAuth
    juju.deploy(
        str(local_charm),
        resources={"oci-image": GLAUTH_IMAGE},
        app=GLAUTH_APP,
        config={"starttls_enabled": "true", "ldaps_enabled": "true"},
        trust=True,
        base="ubuntu@22.04",
    )
    # Deploy GLAuth Proxy
    juju.deploy(
        str(local_charm),
        resources={"oci-image": GLAUTH_IMAGE},
        app=GLAUTH_PROXY,
        config={"starttls_enabled": "true", "ldaps_enabled": "true"},
        trust=True,
        base="ubuntu@22.04",
    )

    # Integrations
    juju.integrate(GLAUTH_APP, CERTIFICATE_PROVIDER_APP)
    juju.integrate(GLAUTH_PROXY, CERTIFICATE_PROVIDER_APP)
    juju.integrate(f"{GLAUTH_APP}:pg-database", DB_APP)
    juju.integrate(f"{GLAUTH_PROXY}:ldap-client", f"{GLAUTH_APP}:ldap")
    juju.integrate(f"{GLAUTH_APP}:ingress", f"{INGRESS_APP}:ingress-per-unit")
    juju.integrate(f"{GLAUTH_APP}:ldaps-ingress", f"{LDAPS_INGRESS_APP}:ingress-per-unit")

    juju.wait(
        ready=all_active(
            CERTIFICATE_PROVIDER_APP,
            DB_APP,
            GLAUTH_APP,
            GLAUTH_PROXY,
            INGRESS_APP,
            LDAPS_INGRESS_APP,
        ),
        error=any_error(
            CERTIFICATE_PROVIDER_APP,
            DB_APP,
            GLAUTH_APP,
            GLAUTH_PROXY,
            INGRESS_APP,
            LDAPS_INGRESS_APP,
        ),
        timeout=20 * 60,
    )


def test_database_integration(
    juju: jubilant.Juju,
    database_integration_data: dict,
) -> None:
    assert database_integration_data
    assert f"{juju.model}_{GLAUTH_APP}" == database_integration_data["database"]
    assert database_integration_data.get("username")
    assert database_integration_data.get("password")


def test_ingress_per_unit_integration(ingress_url: Optional[str]) -> None:
    assert ingress_url, "Ingress url not found in the ingress-per-unit integration"


def test_ldaps_ingress_per_unit_integration(ldaps_ingress_url: Optional[str]) -> None:
    assert ldaps_ingress_url, "LDAPS Ingress url not found in the ingress-per-unit integration"


def test_certification_integration(
    juju: jubilant.Juju,
    certificate_integration_data: Optional[dict],
    ingress_ip: Optional[str],
    ldaps_ingress_ip: Optional[str],
) -> None:
    assert certificate_integration_data
    certificates = json.loads(certificate_integration_data["certificates"])
    certificate = certificates[0]["certificate"]

    model_name = juju.model

    assert f"CN={GLAUTH_APP}.{model_name}.svc.cluster.local" == extract_certificate_common_name(
        certificate
    )
    assert ingress_ip in extract_certificate_sans(certificate)
    assert ldaps_ingress_ip in extract_certificate_sans(certificate)


def test_ldap_client_integration(
    juju: jubilant.Juju,
    app_integration_data: Callable,
) -> None:
    ldap_client_integration_data = app_integration_data(
        GLAUTH_PROXY,
        "ldap-client",
    )
    model_name = juju.model
    assert ldap_client_integration_data
    assert ldap_client_integration_data["bind_dn"].startswith(f"cn={GLAUTH_PROXY},ou={model_name}")
    assert ldap_client_integration_data["bind_password_secret"].startswith("secret:")


class GlauthClientTestSuite:
    def test_ldap_integration(
        self,
        juju: jubilant.Juju,
        pydantic_version: str,
        app_integration_data: Callable,
        ldap_client_app_name: str,
    ) -> None:
        charm_lib_path = Path("lib/charms")
        any_charm_src_overwrite = {
            "any_charm.py": ANY_CHARM,
            "ldap_interface_lib.py": (charm_lib_path / "glauth_k8s/v0/ldap.py").read_text(),
            "certificate_transfer.py": (
                charm_lib_path / "certificate_transfer_interface/v0/certificate_transfer.py"
            ).read_text(),
        }

        juju.deploy(
            GLAUTH_CLIENT_APP,
            app=ldap_client_app_name,
            channel="beta",
            revision=92,
            config={
                "src-overwrite": json.dumps(any_charm_src_overwrite),
                "python-packages": f"pydantic ~= {pydantic_version}\njsonschema\nldap3",
            },
        )

        juju.wait(
            ready=all_active(ldap_client_app_name),
            error=any_error(ldap_client_app_name),
            timeout=10 * 60,
        )

        juju.integrate(
            f"{ldap_client_app_name}:ldap",
            f"{GLAUTH_APP}:ldap",
        )

        juju.wait(
            ready=lambda status: (
                all_active(GLAUTH_APP, ldap_client_app_name)(status)
                and "bind_dn" in (app_integration_data(ldap_client_app_name, "ldap") or {})
            ),
            error=any_error(GLAUTH_APP, ldap_client_app_name),
            timeout=5 * 60,
        )

        integration_data = app_integration_data(
            ldap_client_app_name,
            "ldap",
        )
        model_name = juju.model
        assert integration_data
        assert integration_data["bind_dn"].startswith(f"cn={ldap_client_app_name},ou={model_name}")
        assert integration_data["bind_password_secret"].startswith("secret:")

    def test_certificate_transfer_integration(
        self,
        juju: jubilant.Juju,
        unit_integration_data_func: Callable,
        ingress_ip: Optional[str],
        ldaps_ingress_ip: Optional[str],
        ldap_client_app_name: str,
    ) -> None:
        juju.integrate(
            f"{ldap_client_app_name}:send-ca-cert",
            f"{GLAUTH_APP}:send-ca-cert",
        )

        juju.wait(
            ready=lambda status: (
                all_active(GLAUTH_APP, ldap_client_app_name)(status)
                and "ca"
                in (
                    unit_integration_data_func(ldap_client_app_name, GLAUTH_APP, "send-ca-cert")
                    or {}
                )
            ),
            error=any_error(GLAUTH_APP, ldap_client_app_name),
            timeout=5 * 60,
        )

        certificate_transfer_integration_data = unit_integration_data_func(
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
        model_name = juju.model
        assert (
            f"CN={GLAUTH_APP}.{model_name}.svc.cluster.local"
            == extract_certificate_common_name(certificate)
        )
        assert ingress_ip in extract_certificate_sans(certificate)
        assert ldaps_ingress_ip in extract_certificate_sans(certificate)

    @pytest.mark.skip(
        reason="glauth cannot scale up due to the traefik-k8s issue: https://github.com/canonical/traefik-k8s-operator/issues/406",
    )
    def test_glauth_scale_up(self, juju: jubilant.Juju) -> None:
        target_unit_num = 2
        juju.cli("scale-application", GLAUTH_APP, str(target_unit_num))

        juju.wait(
            ready=and_(
                all_active(GLAUTH_APP),
                lambda status: len(status.apps[GLAUTH_APP].units) == target_unit_num,
            ),
            error=any_error(GLAUTH_APP),
            timeout=5 * 60,
        )

    @pytest.mark.skip(
        reason="cert_handler is bugged, remove this once it is fixed or when we throw it away..."
    )
    def test_glauth_scale_down(self, juju: jubilant.Juju) -> None:
        target_unit_num = 1
        juju.cli("scale-application", GLAUTH_APP, str(target_unit_num))

        juju.wait(
            ready=and_(
                all_active(GLAUTH_APP),
                lambda status: len(status.apps[GLAUTH_APP].units) == target_unit_num,
            ),
            error=any_error(GLAUTH_APP),
            timeout=5 * 60,
        )

    def test_ldap_search_operation(
        self,
        initialize_database: None,
        ldap_configurations: Optional[tuple[str, str, str]],
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

    def test_ldap_starttls_operation(
        self,
        juju: jubilant.Juju,
        ldap_configurations: Optional[tuple[str, str, str]],
        ldap_client_app_name: str,
    ) -> None:
        assert ldap_configurations, "LDAP configuration should be ready"
        base_dn, *_ = ldap_configurations

        action = juju.run(
            f"{ldap_client_app_name}/0",
            "rpc",
            params={"method": "starttls_operation", "cn": "hackers"},
        )
        res = action.results

        ret = json.loads(res["return"])
        assert ret, "Can't find user 'hackers'"
        assert ret["dn"] == f"cn=hackers,ou=superheros,ou=users,{base_dn}"

    def test_ldaps_operation(
        self,
        juju: jubilant.Juju,
        ldap_configurations: Optional[tuple[str, str, str]],
        ldap_client_app_name: str,
    ) -> None:
        assert ldap_configurations, "LDAP configuration should be ready"
        base_dn, *_ = ldap_configurations

        action = juju.run(
            f"{ldap_client_app_name}/0",
            "rpc",
            params={"method": "ldaps_operation", "cn": "hackers"},
        )
        res = action.results

        ret = json.loads(res["return"])
        assert ret, "Can't find user 'hackers'"
        assert ret["dn"] == f"cn=hackers,ou=superheros,ou=users,{base_dn}"

    def test_ldaps_disabled_removes_ldaps_urls(
        self, juju: jubilant.Juju, ldap_client_app_name: str, app_integration_data: Callable
    ) -> None:
        juju.config(GLAUTH_APP, {"ldaps_enabled": "false"})
        juju.wait(
            ready=lambda status: (
                all_active(GLAUTH_APP, ldap_client_app_name)(status)
                and (app_integration_data(ldap_client_app_name, "ldap") or {}).get("ldaps_urls")
                == "[]"
            ),
            error=any_error(GLAUTH_APP, ldap_client_app_name),
            timeout=5 * 60,
        )

        ldaps_data = app_integration_data(ldap_client_app_name, "ldap")
        assert ldaps_data["ldaps_urls"] == "[]"

    def test_ldaps_re_enabled_adds_ldaps_urls(
        self, juju: jubilant.Juju, ldap_client_app_name: str, app_integration_data: Callable
    ) -> None:
        juju.config(GLAUTH_APP, {"ldaps_enabled": "true"})
        juju.wait(
            ready=lambda status: (
                all_active(GLAUTH_APP, ldap_client_app_name)(status)
                and (app_integration_data(ldap_client_app_name, "ldap") or {}).get("ldaps_urls")
                not in (None, "[]")
            ),
            error=any_error(GLAUTH_APP, ldap_client_app_name),
            timeout=5 * 60,
        )

        ldaps_data = app_integration_data(ldap_client_app_name, "ldap")
        assert ldaps_data["ldaps_urls"] != "[]"

    @pytest.mark.teardown
    def test_remove_client_app(self, juju: jubilant.Juju, ldap_client_app_name: str) -> None:
        juju.remove_application(ldap_client_app_name, force=True)
        juju.wait(
            ready=all_active(GLAUTH_APP),
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
