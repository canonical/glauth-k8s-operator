#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Library to manage the relation for ldap authentication.

This library contains the Requires and Provides classes for handling the relation
between an application and an LDAP authentication provider such as glauth-k8s.
This charm library requires the charms.data_platform_libs.data_interfaces library to work.

#### Requires Charm
Using the LDAPRequires class and its events provides an interface for applications to
consume LDAP services

Following an example of using the LDAPEndpointsChangedEvent, and the LDAPCredentialsCreated in the context of the
application charm code:

```python

from charms.glauth_k8s.v0.ldap_public import (
    LDAPAvailable,
    LDAPRequires,
)

class ApplicationCharm(CharmBase):
    # Application charm that connects to database charms.

    def __init__(self, *args):
        super().__init__(*args)

        # Charm events defined in the database requires charm library.
        self.ldap = LDAPRequires(self, relation_name="ldap", distinguished_name="cn=user,ou=users,dc=com")
        self.framework.observe(self.ldap.on.ldap_available, self._on_ldap_available)

    def _on_ldap_available(self, event: LDAPAvailable) -> None:

        # Create configuration file for app
        config_file = self._render_app_config_file(
            event.username,
            event.password,
            event.endpoints,
            event.distinguished_name
        )

        # Start application with rendered configuration
        self._start_application(config_file)

        # Set active status
        self.unit.status = ActiveStatus("received ldap credentials")
```

As shown above, the library provides some custom events to handle specific situations,
which are listed below:

-  ldap_available: event emitted when the requested ldap credentials, and endpoint is available.

### Provider Charm

Following an example of using the DatabaseRequestedEvent, in the context of the
database charm code:

```python
from charms.glauth_k8s.v0.ldap_public import(
    LDAPProvides,
    LDAPRequestedEvent
)

class SampleCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        # Charm events defined in the database provides charm library.
        self.ldap = LDAPProvides(self, relation_name="ldap")
        self.framework.observe(self.ldap.on.ldap_requested,
            self._on_ldap_requested)

    def _on_ldap_requested(self, event: LDAPRequestedEvent) -> None:
        # Handle the event triggered by ldap authentication requested in the relation

```

"""

import logging
from datetime import datetime
from typing import Optional
from charms.data_platform_libs.v0.data_interfaces import (
    DataRequires,
    DataProvides,
)

from ops.charm import (
    CharmBase,
    CharmEvents,
    RelationChangedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
from ops.framework import EventSource


# The unique Charmhub library identifier, never change it
LIBID = "temporary"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 0

PYDEPS = ["ops>=2.0.0"]

logger = logging.getLogger(__name__)

RELATION_NAME = "ldap"
INTERFACE_NAME = "ldap_public"

# General events


class AuthenticationEvent(RelationEvent):
    """Base class for authentication fields for events."""

    @property
    def username(self) -> Optional[str]:
        """Returns the created username."""
        return self.relation.data[self.relation.app].get("username")

    @property
    def password(self) -> Optional[str]:
        """Returns the password for the created user."""
        return self.relation.data[self.relation.app].get("password")


# LDAP related events and fields


class LDAPProvidesEvent(RelationEvent):
    """Base class for ldap events."""

    @property
    def distinguished_name(self) -> Optional[str]:
        """Returns the distinguished name that was requested."""
        return self.relation.data[self.relation.app].get("distinguished_name")


class LDAPRequestedEvent(LDAPProvidesEvent):
    """Event emitted when a new distinguished name is passed onto the relation for authentication."""


class LDAPProvidesEvents(CharmEvents):
    """LDAP events.

    """
    ldap_requested = EventSource(LDAPRequestedEvent)


class LDAPRequiresEvent(RelationEvent):
    """Base class for ldap events."""

    @property
    def distinguished_name(self) -> Optional[str]:
        """Returns the distinguished name for authentication."""
        return self.relation.data[self.relation.app].get("distinguished_name")

    @property
    def endpoints(self) -> Optional[str]:
        """Returns a comma separated list of ldap endpoints.

        """
        return self.relation.data[self.relation.app].get("endpoints")


class LDAPAvailable(AuthenticationEvent, LDAPRequiresEvent):
    """Event emitted when a new credential is created for use on this relation."""


class LDAPRequiresEvents(CharmEvents):
    """LDAP events.

    This class defines the events that the LDAPRequires can emit.
    """

    ldap_available = EventSource(LDAPAvailable)


# LDAP Provider and Requires


class LDAPProvides(DataProvides):
    """Provider-side of the ldap relations."""

    on = LDAPProvidesEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Event emitted when the relation has changed."""
        # Only the leader should handle this event.
        if not self.local_unit.is_leader():
            return

        # Check which data has changed to emit customs events.
        diff = self._diff(event)

        # Emit a distinguished_name_requested event if the setup key (distinguished_name
        # ) was added to the relation databag by the application.
        if "distinguished_name" in diff.added:
            self.on.ldap_requested.emit(event.relation, app=event.app, unit=event.unit)

    def set_ldap_access(self, relation_id: int, distinguished_name: str, endpoints: str, username: str, password: str) -> None:
        """Set distinguished name, endpoints, and user credentials created for ldap authentication.

        This function writes in the application data bag, therefore,
        only the leader unit can call it.

        Args:
            relation_id: the identifier for a particular relation.
            distinguished_name: dn in parameters.
        """
        self._update_relation_data(
            relation_id,
            {
                "distinguished_name": distinguished_name,
                "endpoints": endpoints,
                "username": username,
                "password": password,
            }
        )


class LDAPRequires(DataRequires):
    """Requires-side of the ldap relation."""

    on = LDAPRequiresEvents()

    def __init__(
        self,
        charm,
        relation_name: str,
        distinguished_name: str,
    ):
        """Manager of ldap client relations."""
        super().__init__(charm, relation_name)
        self.distinguished_name = distinguished_name

    def _on_relation_joined_event(self, event: RelationJoinedEvent) -> None:
        """Event emitted when the application joins the ldap relation."""

        # Sets distinguished_name

        self._update_relation_data(event.relation.id, {"distinguished_name": self.distinguished_name})

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Event emitted when the ldap relation has changed."""
        # Check which data has changed to emit customs events.
        diff = self._diff(event)

        # Check if the ldap credentials are created
        if "username" in diff.added and "password" in diff.added and ("endpoints" in diff.added or "endpoints" in diff.changed):
            # Emit the default event.
            logger.info("ldap credentials created at %s", datetime.now())
            self.on.ldap_available.emit(event.relation, app=event.app, unit=event.unit)

            return
