# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from functools import wraps
from typing import Any, Callable, Optional

from constants import GLAUTH_CONFIG_FILE, SERVER_CERT, SERVER_KEY
from ops.charm import CharmBase, EventBase
from ops.model import BlockedStatus, WaitingStatus
from tenacity import Retrying, TryAgain, wait_fixed

logger = logging.getLogger(__name__)

ConditionEvaluation = tuple[bool, str]
Condition = Callable[[CharmBase], ConditionEvaluation]


def container_not_connected(charm: CharmBase) -> ConditionEvaluation:
    not_connected = not charm._container.can_connect()
    return not_connected, ("Container is not connected yet" if not_connected else "")


def integration_not_exists(integration_name: str) -> Condition:
    def wrapped(charm: CharmBase) -> ConditionEvaluation:
        not_exists = not charm.model.relations[integration_name]
        return not_exists, (f"Missing integration {integration_name}" if not_exists else "")

    return wrapped


def tls_certificates_not_ready(charm: CharmBase) -> ConditionEvaluation:
    not_exists = charm.config.get("starttls_enabled", True) and not (
        charm._container.exists(SERVER_KEY) and charm._container.exists(SERVER_CERT)
    )
    return not_exists, ("Missing TLS certificate and private key" if not_exists else "")


def database_not_ready(charm: CharmBase) -> ConditionEvaluation:
    not_exists = not charm.database_requirer.is_resource_created()
    return not_exists, ("Waiting for database creation" if not_exists else "")


def block_when(*conditions: Condition) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(charm: CharmBase, *args: EventBase, **kwargs: Any) -> Optional[Any]:
            event, *_ = args
            logger.debug(f"Handling event: {event}.")

            for condition in conditions:
                resp, msg = condition(charm)
                if resp:
                    event.defer()
                    charm.unit.status = BlockedStatus(msg)
                    return None

            return func(charm, *args, **kwargs)

        return wrapper

    return decorator


def wait_when(*conditions: Condition) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(charm: CharmBase, *args: EventBase, **kwargs: Any) -> Optional[Any]:
            event, *_ = args
            logger.debug(f"Handling event: {event}.")

            for condition in conditions:
                resp, msg = condition(charm)
                if resp:
                    event.defer()
                    charm.unit.status = WaitingStatus(msg)
                    return None

            return func(charm, *args, **kwargs)

        return wrapper

    return decorator


def leader_unit(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        if not charm.unit.is_leader():
            return None

        return func(charm, *args, **kwargs)

    return wrapper


def after_config_updated(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        charm.unit.status = WaitingStatus("Waiting for configuration to be updated")

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
