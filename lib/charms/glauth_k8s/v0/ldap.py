# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Juju Charm Library for the `ldap` Juju Interface

This juju charm library contains the Provider and Requirer classes for handling
the `ldap` interface.

## Requirer Charm

The requirer charm is expected to:

- Provide information for the provider charm to deliver LDAP related
information in the juju integration, in order to communicate with the LDAP
server and authenticate LDAP operations
- Listen to the custom juju event `LdapReadyEvent` to obtain the LDAP
related information from the integration
- Listen to the custom juju event `LdapUnavailableEvent` to handle the
situation when the LDAP integration is broken

```python

from charms.glauth_k8s.v0.ldap import (
    LdapRequirer,
    LdapReadyEvent,
    LdapUnavailableEvent,
)

class RequirerCharm(CharmBase):
    # LDAP requirer charm that integrates with an LDAP provider charm.

    def __init__(self, *args):
        super().__init__(*args)

        self.ldap_requirer = LdapRequirer(self)
        self.framework.observe(
            self.ldap_requirer.on.ldap_ready,
            self._on_ldap_ready,
        )
        self.framework.observe(
            self.ldap_requirer.on.ldap_unavailable,
            self._on_ldap_unavailable,
        )

    def _on_ldap_ready(self, event: LdapReadyEvent) -> None:
        # Consume the LDAP related information
        ldap_data = self.ldap_requirer.consume_ldap_relation_data(
            event.relation.id,
        )

        # Configure the LDAP requirer charm
        ...

    def _on_ldap_unavailable(self, event: LdapUnavailableEvent) -> None:
        # Handle the situation where the LDAP integration is broken
        ...
```

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

- ldap_ready: event emitted when the LDAP related information is ready for
requirer charm to use.
- ldap_unavailable: event emitted when the LDAP integration is broken.

Additionally, the requirer charmed operator needs to declare the `ldap`
interface in the `metadata.yaml`:

```yaml
requires:
  ldap:
    interface: ldap
```

## Provider Charm

The provider charm is expected to:

- Use the information provided by the requirer charm to provide LDAP related
information for the requirer charm to connect and authenticate to the LDAP
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
        # Consume the information provided by the requirer charm
        requirer_data = event.data

        # Prepare the LDAP related information using the requirer's data
        ldap_data = ...

        # Update the integration data
        self.ldap_provider.update_relation_app_data(
            relation.id,
            ldap_data,
        )
```

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

-  ldap_requested: event emitted when the requirer charm is requesting the
LDAP related information in order to connect and authenticate to the LDAP server
"""

from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Callable, Optional, Union

from dacite import Config, from_dict
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
LIBPATCH = 2

PYDEPS = ["dacite~=1.8.0"]

DEFAULT_RELATION_NAME = "ldap"


def leader_unit(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(
        obj: Union["LdapProvider", "LdapRequirer"], *args: Any, **kwargs: Any
    ) -> Optional[Any]:
        if not obj.unit.is_leader():
            return None

        return func(obj, *args, **kwargs)

    return wrapper


@leader_unit
def _update_relation_app_databag(
    ldap: Union["LdapProvider", "LdapRequirer"], relation: Relation, data: dict
) -> None:
    if relation is None:
        return

    data = {k: str(v) if v else "" for k, v in data.items()}
    relation.data[ldap.app].update(data)


@dataclass(frozen=True)
class LdapProviderData:
    url: str
    base_dn: str
    bind_dn: str
    bind_password_secret: str
    auth_method: str
    starttls: bool


@dataclass(frozen=True)
class LdapRequirerData:
    user: str
    group: str


class LdapRequestedEvent(RelationEvent):
    """An event emitted when the LDAP integration is built."""

    @property
    def data(self) -> Optional[LdapRequirerData]:
        relation_data = self.relation.data.get(self.relation.app)
        return (
            from_dict(data_class=LdapRequirerData, data=relation_data)
            if relation_data
            else None
        )


class LdapProviderEvents(ObjectEvents):
    ldap_requested = EventSource(LdapRequestedEvent)


class LdapReadyEvent(RelationEvent):
    """An event when the LDAP related information is ready."""


class LdapUnavailableEvent(RelationEvent):
    """An event when the LDAP integration is unavailable."""


class LdapRequirerEvents(ObjectEvents):
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
        """Handle the event emitted when the requirer charm provides the
        necessary data."""

        self.on.ldap_requested.emit(event.relation)

    def update_relation_app_data(
        self, /, relation_id: int, data: LdapProviderData
    ) -> None:
        """An API for the provider charm to provide the LDAP related
        information."""

        relation = self.charm.model.get_relation(
            self._relation_name, relation_id
        )
        _update_relation_app_databag(self.charm, relation, asdict(data))


class LdapRequirer(Object):
    """An LDAP requirer to consume data delivered by an LDAP provider charm."""

    on = LdapRequirerEvents()

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        *,
        data: Optional[LdapRequirerData] = None,
    ) -> None:
        super().__init__(charm, relation_name)

        self.charm = charm
        self.app = charm.app
        self.unit = charm.unit
        self._relation_name = relation_name
        self._data = data

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

        user = self._data.user or self.app.name
        group = self._data.group or self.model.name
        _update_relation_app_databag(
            self.charm, event.relation, {"user": user, "group": group}
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

    def consume_ldap_relation_data(
        self,
        /,
        relation_id: Optional[int] = None,
    ) -> Optional[LdapProviderData]:
        """An API for the requirer charm to consume the LDAP related
        information in the application databag."""

        relation = self.charm.model.get_relation(
            self._relation_name, relation_id
        )

        if not relation:
            return None

        provider_data = relation.data.get(relation.app)
        return (
            from_dict(
                data_class=LdapProviderData,
                data=provider_data,
                config=Config(cast=[bool]),
            )
            if provider_data
            else None
        )
