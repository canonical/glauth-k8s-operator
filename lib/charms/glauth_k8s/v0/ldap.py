# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Juju Charm Library for the `ldap` Juju Interface.

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
        self.ldap_provider.update_relations_app_data(
            relation.id,
            ldap_data,
        )
```

As shown above, the library offers custom juju events to handle specific
situations, which are listed below:

-  ldap_requested: event emitted when the requirer charm is requesting the
LDAP related information in order to connect and authenticate to the LDAP server
"""

from functools import wraps
from string import Template
from typing import Any, Callable, Literal, Optional, Union

import ops
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    RelationEvent,
)
from ops.framework import EventSource, Object, ObjectEvents
from ops.model import Relation, SecretNotFoundError
from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    ValidationError,
    field_serializer,
    field_validator,
)

# The unique CharmHub library identifier, never change it
LIBID = "5a535b3c4d0b40da98e29867128e57b9"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3

PYDEPS = ["pydantic~=2.5.3"]

DEFAULT_RELATION_NAME = "ldap"
BIND_ACCOUNT_SECRET_LABEL_TEMPLATE = Template("relation-$relation_id-bind-account-secret")


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


class Secret:
    def __init__(self, secret: ops.Secret = None) -> None:
        self._secret: ops.Secret = secret

    @property
    def uri(self) -> str:
        return self._secret.id if self._secret else ""

    @classmethod
    def load(
        cls,
        charm: CharmBase,
        label: str,
        *,
        content: Optional[dict[str, str]] = None,
    ) -> "Secret":
        try:
            secret = charm.model.get_secret(label=label)
        except SecretNotFoundError:
            secret = charm.app.add_secret(label=label, content=content)

        return Secret(secret)

    def grant(self, relation: Relation) -> None:
        self._secret.grant(relation)

    def remove(self) -> None:
        self._secret.remove_all_revisions()


class LdapProviderBaseData(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    base_dn: str
    starttls: StrictBool

    @field_validator("url")
    @classmethod
    def validate_ldap_url(cls, v: str) -> str:
        if not v.startswith("ldap://"):
            raise ValidationError("Invalid LDAP URL scheme.")

        return v

    @field_validator("starttls", mode="before")
    @classmethod
    def deserialize_bool(cls, v: str | bool) -> bool:
        if isinstance(v, str):
            return True if v.casefold() == "true" else False

        return v

    @field_serializer("starttls")
    def serialize_bool(self, starttls: bool) -> str:
        return str(starttls)


class LdapProviderData(LdapProviderBaseData):
    bind_dn: str
    bind_password_secret: str
    auth_method: Literal["simple"]


class LdapRequirerData(BaseModel):
    model_config = ConfigDict(frozen=True)

    user: str
    group: str


class LdapRequestedEvent(RelationEvent):
    """An event emitted when the LDAP integration is built."""

    @property
    def data(self) -> Optional[LdapRequirerData]:
        relation_data = self.relation.data.get(self.relation.app)
        return LdapRequirerData(**relation_data) if relation_data else None


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
        self.framework.observe(
            self.charm.on[self._relation_name].relation_broken,
            self._on_relation_broken,
        )

    @leader_unit
    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the event emitted when the requirer charm provides the necessary data."""
        self.on.ldap_requested.emit(event.relation)

    @leader_unit
    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the LDAP integration is broken."""
        secret = Secret.load(
            self.charm,
            label=BIND_ACCOUNT_SECRET_LABEL_TEMPLATE.substitute(relation_id=event.relation.id),
        )
        secret.remove()

    def update_relations_app_data(
        self, /, data: Optional[LdapProviderBaseData] = None, relation_id: Optional[int] = None
    ) -> None:
        """An API for the provider charm to provide the LDAP related information."""
        if data is None:
            return

        if not (relations := self.charm.model.relations.get(self._relation_name)):
            return

        if relation_id is not None:
            relations = [relation for relation in relations if relation.id == relation_id]
            secret = Secret.load(
                self.charm,
                BIND_ACCOUNT_SECRET_LABEL_TEMPLATE.substitute(relation_id=relation_id),
                content={"password": data.bind_password_secret},
            )
            secret.grant(relations[0])
            data = data.model_copy(update={"bind_password_secret": secret.uri})

        for relation in relations:
            _update_relation_app_databag(self.charm, relation, data.model_dump())  # type: ignore[union-attr]


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
        user = self._data.user if self._data else self.app.name
        group = self._data.group if self._data else self.model.name
        _update_relation_app_databag(self.charm, event.relation, {"user": user, "group": group})

    def _on_ldap_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the event emitted when the LDAP related information is ready."""
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
        """An API for the requirer charm to consume the LDAP related information in the application databag."""
        relation = self.charm.model.get_relation(self._relation_name, relation_id)

        if not relation:
            return None

        provider_data = relation.data.get(relation.app)
        return LdapProviderData(**provider_data) if provider_data else None
