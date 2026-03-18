# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from io import StringIO
from unittest.mock import MagicMock, PropertyMock, patch, sentinel

from conftest import create_state
from ops.charm import CharmBase, HookEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Container, Context

from constants import DATABASE_INTEGRATION_NAME, WORKLOAD_CONTAINER
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
    def test_container_not_connected(self, context: Context) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        state = create_state(containers=[container])
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = container_not_connected(mgr.charm)

        assert res is True and msg

    def test_container_connected(self, context: Context) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = container_not_connected(mgr.charm)

        assert res is False and not msg

    def test_integration_not_exists(self, context: Context) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            condition = integration_not_exists(DATABASE_INTEGRATION_NAME)
            res, msg = condition(mgr.charm)

        assert res is True and msg

    def test_integration_exists(self, context: Context, db_relation: MagicMock) -> None:
        state = create_state(relations=[db_relation])
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            condition = integration_not_exists(DATABASE_INTEGRATION_NAME)
            res, msg = condition(mgr.charm)

        assert res is False and not msg

    def test_tls_certificates_not_ready(self, context: Context) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = tls_certificates_not_ready(mgr.charm)

        assert res is True and msg

    def test_tls_certificates_ready(
        self, context: Context, mocked_tls_certificates: MagicMock
    ) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = tls_certificates_not_ready(mgr.charm)

        assert res is False and not msg

    def test_database_not_ready(self, context: Context) -> None:
        state = create_state()
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = database_not_ready(mgr.charm)

        assert res is True and msg

    def test_database_ready(self, context: Context, db_relation_ready: MagicMock) -> None:
        state = create_state(relations=[db_relation_ready])
        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            res, msg = database_not_ready(mgr.charm)

        assert res is False and not msg

    def test_block_when(self, context: Context) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        state = create_state(containers=[container])
        fake_event = MagicMock(spec=HookEvent)

        @block_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> None:
            return None

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped(mgr.charm, fake_event)

        assert result is None
        assert isinstance(mgr.charm.unit.status, BlockedStatus)

    def test_not_block_when(self, context: Context) -> None:
        state = create_state()
        fake_event = MagicMock(spec=HookEvent)

        @block_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> object:
            return sentinel

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped(mgr.charm, fake_event)

        assert result is sentinel

    def test_wait_when(self, context: Context) -> None:
        container = Container(WORKLOAD_CONTAINER, can_connect=False)
        state = create_state(containers=[container])
        fake_event = MagicMock(spec=HookEvent)

        @wait_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> None:
            return None

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped(mgr.charm, fake_event)

        assert result is None
        assert isinstance(mgr.charm.unit.status, WaitingStatus)

    def test_not_wait_when(self, context: Context) -> None:
        state = create_state()
        fake_event = MagicMock(spec=HookEvent)

        @wait_when(container_not_connected)
        def wrapped(charm: CharmBase, event: HookEvent) -> object:
            return sentinel

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped(mgr.charm, fake_event)

        assert result is sentinel


class TestUtils:
    def test_leader_unit(self, context: Context) -> None:
        state = create_state()

        @leader_unit
        def wrapped_func(charm: CharmBase) -> object:
            return sentinel

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped_func(mgr.charm)

        assert result is sentinel

    def test_not_leader_unit(self, context: Context) -> None:
        state = create_state(leader=False)

        @leader_unit
        def wrapped(charm: CharmBase) -> object:
            return sentinel

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            result = wrapped(mgr.charm)

        assert result is None

    @patch("ops.model.Container.pull", return_value=StringIO("abc"))
    @patch("charm.ConfigFile.content", new_callable=PropertyMock, return_value="abc")
    def test_after_config_updated(
        self,
        mocked_container_pull: MagicMock,
        mocked_configfile_content: MagicMock,
        context: Context,
        mocked_configmap: MagicMock,
    ) -> None:
        # Make fetch_cm() return the same string as what Container.pull() returns
        # so the retry loop in after_config_updated exits immediately.
        mocked_configmap.get.return_value.data = {"glauth.cfg": "abc"}
        state = create_state()
        fake_event = MagicMock(spec=HookEvent)

        @after_config_updated
        def wrapped(charm: CharmBase, event: HookEvent) -> object:
            charm.unit.status = ActiveStatus()
            return sentinel

        with context(context.on.config_changed(), state) as mgr:
            mgr.run()
            # Simulate a config change so after_config_updated enters the retry path.
            mgr.charm.config_changed = True
            result = wrapped(mgr.charm, fake_event)

        assert result is sentinel
        assert isinstance(mgr.charm.unit.status, ActiveStatus)
