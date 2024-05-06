# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from io import StringIO
from unittest.mock import MagicMock, PropertyMock, patch, sentinel

from constants import DATABASE_INTEGRATION_NAME, WORKLOAD_CONTAINER
from ops.charm import CharmBase, HookEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness
from utils import (
    after_config_updated,
    block_when,
    container_not_connected,
    database_not_ready,
    integration_not_exists,
    leader_unit,
    tls_certificates_not_ready,
    wait_when,
)


class TestConditions:
    def test_container_not_connected(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        res, msg = container_not_connected(harness.charm)

        assert res is True and msg

    def test_container_connected(self, harness: Harness) -> None:
        res, msg = container_not_connected(harness.charm)

        assert res is False and not msg

    def test_integration_not_exists(self, harness: Harness) -> None:
        condition = integration_not_exists(DATABASE_INTEGRATION_NAME)
        res, msg = condition(harness.charm)

        assert res is True and msg

    def test_integration_exists(self, harness: Harness, database_relation: int) -> None:
        condition = integration_not_exists(DATABASE_INTEGRATION_NAME)
        res, msg = condition(harness.charm)

        assert res is False and not msg

    def test_tls_certificates_not_ready(self, harness: Harness) -> None:
        res, msg = tls_certificates_not_ready(harness.charm)

        assert res is True and msg

    def test_tls_certificates_ready(
        self, harness: Harness, mocked_tls_certificates: MagicMock
    ) -> None:
        res, msg = tls_certificates_not_ready(harness.charm)

        assert res is False and not msg

    def test_database_not_ready(self, harness: Harness) -> None:
        res, msg = database_not_ready(harness.charm)

        assert res is True and msg

    def test_database_ready(self, harness: Harness, database_resource: MagicMock) -> None:
        res, msg = database_not_ready(harness.charm)

        assert res is False and not msg

    def test_block_when(self, harness: Harness, mocked_hook_event: MagicMock) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)

        @block_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> sentinel:
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is None
        assert isinstance(harness.model.unit.status, BlockedStatus)

    def test_not_block_when(self, harness: Harness, mocked_hook_event: MagicMock) -> None:
        @block_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> sentinel:
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is sentinel

    def test_wait_when(self, harness: Harness, mocked_hook_event: MagicMock) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)

        @wait_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> sentinel:
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is None
        assert isinstance(harness.model.unit.status, WaitingStatus)

    def test_not_wait_when(self, harness: Harness, mocked_hook_event: MagicMock) -> None:
        @wait_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> sentinel:
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is sentinel


class TestUtils:
    def test_leader_unit(self, harness: Harness) -> None:
        @leader_unit
        def wrapped_func(charm: CharmBase) -> sentinel:
            return sentinel

        assert wrapped_func(harness.charm) is sentinel

    def test_not_leader_unit(self, harness: Harness) -> None:
        @leader_unit
        def wrapped(charm: CharmBase) -> sentinel:
            return sentinel

        harness.set_leader(False)

        assert wrapped(harness.charm) is None

    @patch("ops.model.Container.pull", return_value=StringIO("abc"))
    @patch("charm.ConfigFile.content", new_callable=PropertyMock, return_value="abc")
    def test_after_config_updated(
        self,
        mocked_container_pull: MagicMock,
        mocked_configfile_content: MagicMock,
        harness: Harness,
        mocked_hook_event: MagicMock,
    ) -> None:
        @after_config_updated
        def wrapped(charm: CharmBase, event: HookEvent) -> sentinel:
            charm.unit.status = ActiveStatus()
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is sentinel
        assert isinstance(harness.model.unit.status, ActiveStatus)
