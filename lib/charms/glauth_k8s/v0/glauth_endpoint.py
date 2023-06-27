#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""This library provides a Python API for both requesting and providing the endpoint for LDAP interface.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.glauth_k8s.v0.glauth_endpoint
```
To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  ldap:
    interface: ldap_public
    limit: 1
```
Then, to initialise the library:
```python
from charms.glauth.v0.glauth_endpoint import (
    LDAPEndpointRelationError,
    LDAPEndpointRequirer,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.ldap_relation = LDAPEndpointRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            ldap_endpoint = self.ldap_relation.get_ldap_endpoint()
        except LDAPEndpointRelationError as error:
            ...
```
"""

import logging
from typing import Dict

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents

# The unique Charmhub library identifier, never change it
LIBID = "temporary"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 0

RELATION_NAME = "ldap"
INTERFACE_NAME = "ldap_public"
logger = logging.getLogger(__name__)


class LDAPEndpointRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class LDAPEndpointProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `LDAPEndpointProvider`."""

    ready = EventSource(LDAPEndpointRelationReadyEvent)


class LDAPEndpointProvider(Object):
    """Provider side of the `ldap` relation."""

    on = LDAPEndpointProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_provider_endpoint_relation_created
        )

    def _on_provider_endpoint_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def send_ldap_endpoint(self, ldap_endpoint: str) -> None:
        """Updates relation with endpoints info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[self._relation_name]
        for relation in relations:
            relation.data[self._charm.app].update(
                {
                    "endpoint": ldap_endpoint,
                }
            )


class LDAPEndpointRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class LDAPEndpointRelationMissingError(LDAPEndpointRelationError):
    """Raised when the relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing glauth ldap relation with kratos"
        super().__init__(self.message)


class LDAPEndpointRelationDataMissingError(LDAPEndpointRelationError):
    """Raised when information is missing from the relation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class LDAPEndpointRequirer(Object):
    """Requirer side of the ldap relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    def get_ldap_endpoint(self) -> Dict:
        """Get the glauth ldap endpoint."""
        endpoints = self.model.relations[self.relation_name]
        if len(endpoints) == 0:
            raise LDAPEndpointRelationMissingError()

        if not (app := endpoints[0].app):
            raise LDAPEndpointRelationMissingError()

        data = endpoints[0].data[app]

        if "endpoint" not in data:
            raise LDAPEndpointRelationDataMissingError(
                "Missing ldap endpoint in glauth ldap relation data"
            )

        return {
            "endpoint": data["endpoint"],
        }
