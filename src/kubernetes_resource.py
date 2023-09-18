# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import Callable

from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import ConfigMap
from tenacity import (
    RetryError,
    Retrying,
    TryAgain,
    before_log,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def watch_for_update(func: Callable):
    def wrapper(self, *args, **kwargs):
        resource = self.get()
        version = resource.metadata.resourceVersion if resource else None

        func(self, *args, **kwargs)

        try:
            for attempt in Retrying(
                wait=wait_exponential(multiplier=1, min=1, max=30),
                stop=stop_after_attempt(5),
                before=before_log(logger, log_level=logging.INFO),
            ):
                with attempt:
                    resource = self.get()
                    if (
                        not resource
                        or resource.metadata.resourceVersion == version
                    ):
                        raise TryAgain
        except RetryError:
            logger.debug("No changes in the watched k8s resource")

    return wrapper


class ConfigMapResource:
    def __init__(self, client: Client, name: str):
        self._client = client
        self._name = name

    @property
    def name(self):
        return self._name

    def get(self):
        try:
            cm = self._client.get(
                ConfigMap, self._name, namespace=self._client.namespace
            )
            return cm
        except ApiError as e:
            logging.error(f"Error fetching ConfigMap: {e}")

    def create(self):
        cm = ConfigMap(
            apiVersion="v1",
            kind="ConfigMap",
            metadata=ObjectMeta(
                name=self._name,
                labels={
                    "app.kubernetes.io/managed-by": "juju",
                },
            ),
        )

        try:
            self._client.create(cm)
        except ApiError as e:
            logging.error(f"Error creating ConfigMap: {e}")

    @watch_for_update
    def patch(self, data: dict):
        patch_data = {"data": data}

        try:
            self._client.patch(
                ConfigMap,
                name=self._name,
                namespace=self._client.namespace,
                obj=patch_data,
            )
        except ApiError as e:
            logging.error(f"Error updating ConfigMap: {e}")

    def delete(self):
        try:
            self._client.delete(
                ConfigMap, self._name, namespace=self._client.namespace
            )
        except ApiError as e:
            logging.error(f"Error deleting ConfigMap: {e}")


class StatefulSetResource:
    def __init__(self, client, name: str):
        self._client = client
        self._name = name

    @property
    def name(self):
        return self._name

    def get(self):
        try:
            ss = self._client.get(
                StatefulSet, self._name, namespace=self._client.namespace
            )
            return ss
        except ApiError as e:
            logging.error(f"Error fetching ConfigMap: {e}")

    def patch(self, data: dict):
        try:
            self._client.patch(
                StatefulSet,
                name=self._name,
                namespace=self._client.namespace,
                obj=data,
            )
        except ApiError as e:
            logging.error(f"Error patching the StatefulSet: {e}")
