# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any

import pytest
import yaml
from charms.glauth_k8s.v0.ldap import LdapReadyEvent, LdapRequirer, LdapUnavailableEvent
from ops import CharmBase, EventBase
from ops.testing import Context, Model, Relation, Secret, State
from unit.conftest import create_state

METADATA = """
name: requirer-tester
requires:
  ldap:
    interface: ldap
"""


class LdapRequirerCharm(CharmBase):
    """Test charm that wraps LdapRequirer and records emitted events."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.events: list[EventBase] = []
        self.ldap_requirer = LdapRequirer(self)
        self.framework.observe(
            self.ldap_requirer.on.ldap_ready,
            self._record_event,
        )
        self.framework.observe(
            self.ldap_requirer.on.ldap_unavailable,
            self._record_event,
        )

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture
def context() -> Context:
    """ops.testing Context for the test LdapRequirerCharm."""
    return Context(LdapRequirerCharm, meta=yaml.safe_load(METADATA), juju_version="3.2.1")


@pytest.fixture
def provider_data() -> dict[str, str]:
    """Minimal LDAP provider relation data."""
    return {
        "urls": '["ldap://path.to.glauth:3893"]',
        "ldaps_urls": '["ldaps://path.to.glauth:3894"]',
        "base_dn": "dc=glauth,dc=com",
        "starttls": "true",
        "bind_dn": "cn=serviceuser,ou=svcaccts,dc=glauth,dc=com",
        "bind_password_secret": "",
        "auth_method": "simple",
    }


@pytest.fixture
def requirer_data() -> dict[str, str]:
    """Expected LDAP requirer relation data."""
    return {
        "user": "requirer-tester",
        "group": "test",
    }


def dict_to_relation_data(dic: dict[str, Any]) -> dict[str, str]:
    """Serialise list/dict values to JSON strings."""
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


def test_data_in_relation_bag(context: Context, requirer_data: dict[str, str]) -> None:
    relation = Relation("ldap")
    # Use a fixed model name so the LdapRequirer's group == requirer_data["group"].
    state = State(model=Model(name="test"), leader=True, relations=[relation])

    state_out = context.run(context.on.relation_created(relation), state)

    relation_data = state_out.get_relation(relation.id).local_app_data
    assert relation_data == dict_to_relation_data(requirer_data)


def test_event_emitted_when_ldap_is_ready(
    context: Context,
    provider_data: dict[str, str],
) -> None:
    password = "p4ssw0rd"
    secret = Secret(id="secret:bind-0001", tracked_content={"password": password})
    data = {**provider_data, "bind_password_secret": secret.id}
    relation = Relation("ldap", remote_app_data=data)
    state = create_state(leader=True, relations=[relation], secrets=[secret], containers=[])

    context.run(context.on.relation_changed(relation), state)

    # The requirer identity (user/group) is written on relation_created, not relation_changed.
    # This test's purpose is verifying the ldap_ready event is emitted.
    assert any(isinstance(e, LdapReadyEvent) for e in context.emitted_events)


def test_event_emitted_when_relation_removed(context: Context) -> None:
    relation = Relation("ldap")
    state = create_state(leader=True, relations=[relation], containers=[])

    context.run(context.on.relation_broken(relation), state)

    assert any(isinstance(e, LdapUnavailableEvent) for e in context.emitted_events)


def test_consume_ldap_relation_data(context: Context, provider_data: dict[str, str]) -> None:
    password = "p4ssw0rd"
    secret = Secret(id="secret:bind-0002", tracked_content={"password": password})
    data = {**provider_data, "bind_password_secret": secret.id}
    relation = Relation("ldap", remote_app_data=data)
    state = create_state(leader=True, relations=[relation], secrets=[secret], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        result = mgr.charm.ldap_requirer.consume_ldap_relation_data()

    assert result is not None
    assert result.auth_method == provider_data["auth_method"]
    assert result.base_dn == provider_data["base_dn"]
    assert result.bind_dn == provider_data["bind_dn"]
    assert result.bind_password == password
    assert result.bind_password_secret == secret.id


def test_consume_ldap_relation_data_inaccessible_secret(
    context: Context, provider_data: dict[str, str]
) -> None:
    data = {**provider_data, "bind_password_secret": "secret:no-grant"}
    relation = Relation("ldap", remote_app_data=data)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        result = mgr.charm.ldap_requirer.consume_ldap_relation_data()

    assert result is None


def test_not_ready(context: Context, provider_data: dict[str, str]) -> None:
    data = {k: v for k, v in provider_data.items() if k != "urls"}
    relation = Relation("ldap", remote_app_data=data)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        assert not mgr.charm.ldap_requirer.ready()


def test_ready(context: Context, provider_data: dict[str, str]) -> None:
    relation = Relation("ldap", remote_app_data=provider_data)
    state = create_state(leader=True, relations=[relation], containers=[])

    with context(context.on.relation_changed(relation), state) as mgr:
        mgr.run()
        assert mgr.charm.ldap_requirer.ready()
