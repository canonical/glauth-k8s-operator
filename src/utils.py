# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from functools import wraps
from typing import Any, Callable, Optional

from constants import GLAUTH_CONFIG_FILE
from ops.charm import CharmBase, EventBase
from ops.model import BlockedStatus, WaitingStatus
from tenacity import Retrying, TryAgain, wait_fixed

logger = logging.getLogger(__name__)


def leader_unit(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        if not charm.unit.is_leader():
            return None

        return func(charm, *args, **kwargs)

    return wrapper


def validate_container_connectivity(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: EventBase, **kwargs: Any) -> Optional[Any]:
        event, *_ = args
        logger.debug(f"Handling event: {event}")
        if not charm._container.can_connect():
            logger.debug(f"Cannot connect to container, defer event {event}.")
            event.defer()

            charm.unit.status = WaitingStatus("Waiting to connect to container.")
            return None

        return func(charm, *args, **kwargs)

    return wrapper


def validate_integration_exists(integration_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(charm: CharmBase, *args: EventBase, **kwargs: Any) -> Optional[Any]:
            event, *_ = args
            logger.debug(f"Handling event: {event}")

            if not charm.model.relations[integration_name]:
                logger.debug(f"Integration {integration_name} is missing, defer event {event}.")
                event.defer()

                charm.unit.status = BlockedStatus(
                    f"Missing required integration {integration_name}"
                )
                return None

            return func(charm, *args, **kwargs)

        return wrapper

    return decorator


def validate_database_resource(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: EventBase, **kwargs: Any) -> Optional[Any]:
        event, *_ = args
        logger.info(f"Handling event: {event}")

        if not charm.database_requirer.is_resource_created():
            logger.info(f"Database has not been created yet, defer event {event}")
            event.defer()

            charm.unit.status = WaitingStatus("Waiting for database creation")
            return None

        return func(charm, *args, **kwargs)

    return wrapper


def after_config_updated(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        for attempt in Retrying(
            wait=wait_fixed(3),
        ):
            expected_config = charm.config_file.content
            current_config = charm._container.pull(GLAUTH_CONFIG_FILE).read()
            with attempt:
                if expected_config != current_config:
                    raise TryAgain

        return func(charm, *args, **kwargs)

    return wrapper
