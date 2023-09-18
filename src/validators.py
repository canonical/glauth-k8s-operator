# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from functools import wraps
from typing import Any, Callable

from ops.charm import EventBase
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus

from constants import DATABASE_RELATION_NAME

logger = logging.getLogger(__name__)


def leader_unit(func: Callable):
    @wraps(func)
    def wrapper(self, *args: EventBase, **kwargs: Any):
        if not self.unit.is_leader():
            return

        return func(self, *args, **kwargs)

    return wrapper


def validate_container_connectivity(func: Callable):
    @wraps(func)
    def wrapper(self, *args: EventBase, **kwargs: Any):
        event, *_ = args
        logger.debug(f"Handling event: {event}")
        if not self._container.can_connect():
            logger.debug(f"Cannot connect to container, defer event {event}.")
            event.defer()

            self.unit.status = WaitingStatus(
                "Waiting to connect to " "container."
            )
            return

        return func(self, *args, **kwargs)

    return wrapper


def validate_database_relation(func: Callable):
    @wraps(func)
    def wrapper(self, *args: EventBase, **kwargs: Any):
        event, *_ = args
        logger.debug(f"Handling event: {event}")

        self.unit.status = MaintenanceStatus("Configuring resources")
        if not self.model.relations[DATABASE_RELATION_NAME]:
            logger.debug(f"Database relation is missing, defer event {event}.")
            event.defer()

            self.unit.status = BlockedStatus(
                "Missing required relation with " "database"
            )
            return

        return func(self, *args, **kwargs)

    return wrapper


def validate_database_resource(func: Callable):
    @wraps(func)
    def wrapper(self, *args: EventBase, **kwargs: Any):
        event, *_ = args
        logger.debug(f"Handling event: {event}")

        self.unit.status = MaintenanceStatus("Configuring resources")
        if not self.database.is_resource_created():
            logger.debug(
                f"Database has not been created yet, defer event {event}"
            )
            event.defer()

            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        return func(self, *args, **kwargs)

    return wrapper
