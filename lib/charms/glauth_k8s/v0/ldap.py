# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Juju Charm Library for the `ldap` Juju Interface

This juju charm library contains the Provider and Consumer classes for handling
the `ldap` interface.

## Consumer Charm

The consumer charm is expected to:

- Provide information for the provider charm to pass LDAP related
information in the juju integration, in order to communicate with the LDAP
server and authenticate LDAP operations
- Listen to the custom juju event `LdapReadyEvent` to obtain the LDAP
related information from the integration
- Listen to the custom juju event `LdapUnavailableEvent` to handle the
situation when the LDAP integration is broken

```python

from charms.glauth_k8s.v0.ldap import (
    LdapConsumer,
    LdapReadyEvent,
    LdapUnavailableEvent,
)

class ConsumerCharm(CharmBase):
    # LDAP consumer charm that integrates with an LDAP provider charm.

    def __init__(self, *args):
        super().__init__(*args)

        self.ldap_consumer = LdapConsumer(self)
        self.framework.observe(
            self.ldap_consumer.on.ldap_ready,
            self._on_ldap_ready,
        )
        self.framework.observe(
            self.ldap_consumer.on.ldap_unavailable,
            self._on_ldap_unavailable,
        )

    def _on_ldap_ready(self, event: LdapReadyEvent) -> None:
        # Consume the LDAP related information
        ldap_data = LdapConsumer.consume_ldap_relation_data(event.relation)

        # Configure the LDAP consumer charm
        ...

    def _on_ldap_unavailable(self, event: LdapUnavailableEvent) -> None:
        # Handle the situation where the LDAP integration is broken
        ...
```

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

- ldap_ready: event emitted when the LDAP related information is ready for
consumer charm to use.
- ldap_unavailable: event emitted when the LDAP integration is broken.

Additionally, the consumer charmed operator needs to declare the `ldap`
interface in the `metadata.yaml`:

```yaml
requires:
  ldap:
    interface: ldap
```

## Provider Charm

The provider charm is expected to:

- Use the information provided by the consumer charm to provide LDAP related
information for the consumer charm to connect and authenticate to the LDAP
server
- Listen to the custom juju event `LdapRequestedEvent` to offer LDAP related
information in the integration

```python

from charms.glauth_k8s.v0.ldap import (
    LdapProvider,
    LdapRequestedEvent,
)

class ProviderCharm(CharmBase):
    # LDAP provider charm.

    def __init__(self, *args):
        super().__init__(*args)

        self.ldap_provider = LdapProvider(self)
        self.framework.observe(
            self.ldap_provider.on.ldap_requested,
            self._on_ldap_requested,
    )

    def _on_ldap_requested(self, event: LdapRequestedEvent) -> None:
        # Consume the information provided by the consumer charm
        consumer_data = event.data

        # Prepare the LDAP related information
        ldap_data = ...

        # Update the integration data
        self.ldap_provider.update_relation_app_data(
            relation.id,
            ldap_data,
        )
```

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

-  ldap_requested: event emitted when the consumer charm is requesting the
LDAP related information in order to connect and authenticate to the LDAP server
"""

from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Callable, Optional, Union

from dacite import from_dict
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    RelationEvent,
)
from ops.framework import EventSource, Object, ObjectEvents
from ops.model import Relation

# The unique CharmHub library identifier, never change it
LIBID = "5a535b3c4d0b40da98e29867128e57b9"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["dacite~=1.8.0"]

DEFAULT_RELATION_NAME = "ldap"


def leader_unit(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(
        obj: Union["LdapProvider", "LdapConsumer"], *args: Any, **kwargs: Any
    ) -> Optional[Any]:
        if not obj.unit.is_leader():
            return None

        return func(obj, *args, **kwargs)

    return wrapper


@leader_unit
def _update_relation_app_databag(
    ldap: Union["LdapProvider", "LdapConsumer"], relation: Relation, data: dict
) -> None:
    if relation is None:
        return

    relation.data[ldap.app].update(data)


@dataclass(frozen=True)
class LdapProviderData:
    ldap_uri: str
    base_dn: str
    bind_dn: str
    bind_password: str


@dataclass(frozen=True)
class LdapConsumerData:
    app: str
    model: str


class LdapRequestedEvent(RelationEvent):
    """An event emitted when the LDAP integration is built."""

    @property
    def data(self) -> Optional[LdapConsumerData]:
        if not self.relation.data:
            return None

        relation_data = self.relation.data[self.relation.app]
        return from_dict(data_class=LdapConsumerData, data=relation_data)


class LdapProviderEvents(ObjectEvents):
    ldap_requested = EventSource(LdapRequestedEvent)


class LdapReadyEvent(RelationEvent):
    """An event when the LDAP related information is ready."""


class LdapUnavailableEvent(RelationEvent):
    """An event when the LDAP integration is unavailable."""


class LdapConsumerEvents(ObjectEvents):
    ldap_ready = EventSource(LdapReadyEvent)
    ldap_unavailable = EventSource(LdapUnavailableEvent)


class LdapProvider(Object):
    on = LdapProviderEvents()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        super().__init__(charm, relation_name)

        self.charm = charm
        self.app = charm.app
        self.unit = charm.unit
        self._relation_name = relation_name

        self.framework.observe(
            self.charm.on[self._relation_name].relation_changed,
            self._on_relation_changed,
        )

    @leader_unit
    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the event emitted when the consumer charm provides the
        necessary data."""

        self.on.ldap_requested.emit(event.relation)

    def update_relation_app_data(
        self, relation_id: int, data: LdapProviderData
    ) -> None:
        """An API for the provider charm to provide the LDAP related
        information."""

        relation = self.charm.model.get_relation(
            self._relation_name, relation_id
        )
        _update_relation_app_databag(self.charm, relation, asdict(data))


class LdapConsumer(Object):
    """An LDAP consumer to consume data delivered by an LDAP provider charm."""

    on = LdapConsumerEvents()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
    ) -> None:
        super().__init__(charm, relation_name)

        self.charm = charm
        self.app = charm.app
        self.unit = charm.unit
        self._relation_name = relation_name

        self.framework.observe(
            self.charm.on[self._relation_name].relation_created,
            self._on_ldap_relation_created,
        )
        self.framework.observe(
            self.charm.on[self._relation_name].relation_changed,
            self._on_ldap_relation_changed,
        )
        self.framework.observe(
            self.charm.on[self._relation_name].relation_broken,
            self._on_ldap_relation_broken,
        )

    def _on_ldap_relation_created(self, event: RelationCreatedEvent) -> None:
        """Handle the event emitted when an LDAP integration is created."""

        app = self.app.name
        model = self.model.name
        _update_relation_app_databag(
            self.charm, event.relation, {"app": app, "model": model}
        )

    def _on_ldap_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the event emitted when the LDAP related information is
        ready."""

        provider_app = event.relation.app

        if not event.relation.data.get(provider_app):
            return

        self.on.ldap_ready.emit(event.relation)

    def _on_ldap_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the LDAP integration is broken."""

        self.on.ldap_unavailable.emit(event.relation)

    @staticmethod
    def consume_ldap_relation_data(
        relation: Relation,
    ) -> Optional[LdapProviderData]:
        """An API for the consumer charm to consume the LDAP related
        information in the application databag."""

        provider_data = relation.data.get(relation.app)
        return (
            from_dict(data_class=LdapProviderData, data=provider_data)
            if provider_data
            else None
        )
