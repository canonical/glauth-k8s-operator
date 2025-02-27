# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any, Dict, Generator, List

import pytest
from charms.glauth_k8s.v0.ldap import LdapReadyEvent, LdapRequirer, LdapUnavailableEvent
from ops import CharmBase, EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  ldap:
    interface: ldap
"""


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(LdapRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.set_model_name("test")
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


@pytest.fixture()
def provider_data() -> Dict[str, str]:
    return {
        "urls": '["ldap://path.to.glauth:3893"]',
        "ldaps_urls": '["ldaps://path.to.glauth:3894"]',
        "base_dn": "dc=glauth,dc=com",
        "starttls": "true",
        "bind_dn": "cn=serviceuser,ou=svcaccts,dc=glauth,dc=com",
        "bind_password_secret": "",
        "auth_method": "simple",
    }


@pytest.fixture()
def requirer_data() -> Dict[str, str]:
    return {
        "user": "requirer-tester",
        "group": "test",
    }


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class LdapRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.events: List[EventBase] = []
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


def test_data_in_relation_bag(harness: Harness, requirer_data: Dict) -> None:
    relation_id = harness.add_relation("ldap", "provider")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert relation_data == dict_to_relation_data(requirer_data)


def test_event_emitted_when_ldap_is_ready(
    harness: Harness,
    provider_data: Dict,
    requirer_data: Dict,
) -> None:
    relation_id = harness.add_relation("ldap", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data,
    )
    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)
    events = harness.charm.events

    assert relation_data == dict_to_relation_data(requirer_data)
    assert len(events) == 1
    assert isinstance(events[0], LdapReadyEvent)


def test_event_emitted_when_relation_removed(
    harness: Harness,
    provider_data: Dict,
    requirer_data: Dict,
) -> None:
    relation_id = harness.add_relation("ldap", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.remove_relation(relation_id)

    events = harness.charm.events

    assert len(events) == 1
    assert isinstance(events[0], LdapUnavailableEvent)


def test_consume_ldap_relation_data(harness: Harness, provider_data: Dict) -> None:
    password = "p4ssw0rd"
    relation_id = harness.add_relation("ldap", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    secret_id = harness.add_model_secret("provider", {"password": password})
    harness.grant_secret(secret_id, "requirer-tester")
    provider_data["bind_password_secret"] = secret_id
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data,
    )

    charm: LdapRequirerCharm = harness.charm
    data = charm.ldap_requirer.consume_ldap_relation_data()

    assert data
    assert data.auth_method == provider_data["auth_method"]
    assert data.base_dn == provider_data["base_dn"]
    assert data.bind_dn == provider_data["bind_dn"]
    assert data.bind_password == password
    assert data.bind_password_secret == provider_data["bind_password_secret"]


def test_not_ready(harness: Harness, provider_data: Dict) -> None:
    relation_id = harness.add_relation("ldap", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    provider_data.pop("urls")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data,
    )

    charm: LdapRequirerCharm = harness.charm

    assert not charm.ldap_requirer.ready()


def test_ready(harness: Harness, provider_data: Dict) -> None:
    relation_id = harness.add_relation("ldap", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data,
    )

    charm: LdapRequirerCharm = harness.charm

    assert charm.ldap_requirer.ready()
