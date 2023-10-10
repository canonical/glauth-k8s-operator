# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from functools import wraps
from typing import Any, Callable

from ops.charm import CharmBase, EventBase
from ops.model import BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)


def leader_unit(func: Callable):
    @wraps(func)
    def wrapper(self: CharmBase, *args: EventBase, **kwargs: Any):
        if not self.unit.is_leader():
            return

        return func(self, *args, **kwargs)

    return wrapper


def validate_container_connectivity(func: Callable):
    @wraps(func)
    def wrapper(self: CharmBase, *args: EventBase, **kwargs: Any):
        event, *_ = args
        logger.debug(f"Handling event: {event}")
        if not self._container.can_connect():
            logger.debug(f"Cannot connect to container, defer event {event}.")
            event.defer()

            self.unit.status = WaitingStatus("Waiting to connect to container.")
            return

        return func(self, *args, **kwargs)

    return wrapper


def validate_integration_exists(integration_name: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self: CharmBase, *args: EventBase, **kwargs: Any):
            event, *_ = args
            logger.debug(f"Handling event: {event}")

            if not self.model.relations[integration_name]:
                logger.debug(f"Integration {integration_name} is missing, defer event {event}.")
                event.defer()

                self.unit.status = BlockedStatus(
                    f"Missing required integration {integration_name}"
                )
                return

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def validate_database_resource(func: Callable):
    @wraps(func)
    def wrapper(self: CharmBase, *args: EventBase, **kwargs: Any):
        event, *_ = args
        logger.debug(f"Handling event: {event}")

        if not self.database.is_resource_created():
            logger.debug(f"Database has not been created yet, defer event {event}")
            event.defer()

            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        return func(self, *args, **kwargs)

    return wrapper
