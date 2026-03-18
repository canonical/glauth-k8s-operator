# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from contextlib import contextmanager
from typing import Callable, Iterator, Optional

import jubilant
import ldap
import yaml
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from integration.constants import GLAUTH_APP
from tenacity import retry, stop_after_attempt, wait_exponential

StatusPredicate = Callable[[jubilant.Status], bool]


def juju_model_factory(model_name: str) -> jubilant.Juju:
    juju = jubilant.Juju()
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO"})
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise

    juju.model = model_name

    return juju


def get_unit_data(model: jubilant.Juju, unit_name: str) -> dict:
    """Get the data for a given unit."""
    stdout = model.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    juju: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> dict | None:
    """Get the integration data for a given integration."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    model: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    """Get the application data for a given integration."""
    data = get_integration_data(model, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def get_unit_address(juju: jubilant.Juju, app_name: str, unit_num: int = 0) -> str:
    """Get the address of a given unit."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return data["address"]


@contextmanager
def remove_integration(
    juju: jubilant.Juju, /, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Temporarily remove an integration from the application.

    Integration is restored after the context is exited.
    """

    # The pre-existing integration instance can still be "dying" when the `finally` block
    # is called, so `tenacity.retry` is used here to capture the `jubilant.CLIError`
    # and re-run `juju integrate ...` until the previous integration instance has finished dying.
    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _reintegrate() -> None:
        juju.integrate(f"{GLAUTH_APP}:{integration_name}", remote_app_name)

    juju.remove_relation(f"{GLAUTH_APP}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        _reintegrate()


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_active(status, *apps)


def all_blocked(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_blocked(status, *apps)


def all_waiting(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_waiting(status, *apps)


def all_maintenance(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_maintenance(status, *apps)


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)


@contextmanager
def ldap_connection(
    uri: str, bind_dn: str, bind_password: str
) -> Iterator[ldap.ldapobject.LDAPObject]:
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
