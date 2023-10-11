# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from lightkube import Client
from lightkube.core.client import AllNamespacedResource
from lightkube.core.exceptions import ApiError
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import ConfigMap

logger = logging.getLogger(__name__)


class KubernetesResourceError(Exception):
    def __init__(self, message: str):
        self.message = message


class ConfigMapResource:
    def __init__(self, client: Client, name: str):
        self._client = client
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get(self) -> AllNamespacedResource:
        try:
            cm = self._client.get(ConfigMap, self._name, namespace=self._client.namespace)
            return cm
        except ApiError as e:
            logging.error(f"Error fetching ConfigMap: {e}")

    def create(self) -> None:
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
            raise KubernetesResourceError(f"Failed to create ConfigMap {self._name}")

    def patch(self, data: dict) -> None:
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

    def delete(self) -> None:
        try:
            self._client.delete(ConfigMap, self._name, namespace=self._client.namespace)
        except ApiError as e:
            logging.error(f"Error deleting ConfigMap: {e}")


class StatefulSetResource:
    def __init__(self, client: Client, name: str):
        self._client = client
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get(self) -> AllNamespacedResource:
        try:
            ss = self._client.get(StatefulSet, self._name, namespace=self._client.namespace)
            return ss
        except ApiError as e:
            logging.error(f"Error fetching ConfigMap: {e}")

    def patch(self, data: dict) -> None:
        try:
            self._client.patch(
                StatefulSet,
                name=self._name,
                namespace=self._client.namespace,
                obj=data,
            )
        except ApiError as e:
            logging.error(f"Error patching the StatefulSet: {e}")
