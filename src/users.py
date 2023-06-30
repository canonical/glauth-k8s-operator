#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Helper class for managing users in GLAuth."""

import hashlib
import json
import logging

# from datetime import datetime
from typing import List, Tuple

from ops.charm import CharmBase

logger = logging.getLogger(__name__)

BASE_UID = 5000


class User:
    """Structure storing information about GLAuth User."""

    def __init__(self, name: str, password: str, uidnumber: str, distinguished_name: str) -> None:
        self._name = name
        self._passsha256 = password
        self._uidNumber = uidnumber
        self._object = distinguished_name


class UserEncoder(json.JSONEncoder):
    """Helper class for serializing User class."""

    def default(self, obj: User):
        """Interface for json.dump."""
        if isinstance(obj, User):
            return {
                "name": obj._name,
                "passsha256": obj._passsha256,
                "uidnumber": obj._uidNumber,
                "object": obj._object,
            }
        return super().default(obj)


class UserManager:
    """UserManager stores, creates, and retrieves GLAuth users."""

    def __init__(self, charm: CharmBase, peer_relation_name: str) -> None:
        self._charm = charm
        self._peer_relation_name = peer_relation_name

        self._userList = self._retrieve_users(charm, peer_relation_name)

    def add_user(self, name: str, password: str, distinguished_name: str) -> bool:
        """Adds new GLAuth user."""
        passsh256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
        new_user = User(name, passsh256, str(self.next_uidnumber), distinguished_name)
        ok = self._store_user(new_user)
        if not ok:
            return False
        self._userList.append(new_user)
        return True

    def _store_user(self, user: User) -> bool:
        peer_relation = self._charm.model.relations[self._peer_relation_name]
        if not peer_relation:
            return False

        if self._charm.unit.is_leader():
            userjson = json.dumps(user, cls=UserEncoder)
            peer_relation[0].data[self._charm.app].update(
                {
                    user._uidNumber: userjson,
                }
            )
            return True
        return False

    def _retrieve_users(self, charm: CharmBase, peer_relation_name: str) -> List[User]:
        peer_relation = charm.model.relations[peer_relation_name]
        if not peer_relation:
            return []

        if charm.unit.is_leader():
            if not peer_relation[0].data[charm.app]:
                return []
            users = []
            for key, data in peer_relation[0].data[charm.app].items:
                userjson = json.loads(data)
                user = User(
                    userjson["name"],
                    userjson["passsha256"],
                    userjson["uidnumber"],
                    userjson["object"],
                )
                users.append(user)
            return users
        else:
            return []

    @property
    def next_uidnumber(self) -> int:
        """Property for next UID Number for new Users."""
        return BASE_UID + 1 + len(self._userList)

    @property
    def users(self) -> List[User]:
        """Property for retrieving list of current GLAuth users."""
        return self._userList

    def generate_user(
        self, relation_name: str, relation_id: str, distinguished_name: str
    ) -> Tuple[str, str]:
        """Method for creating a user from distinguished name from ldap relation requirer."""
        username = self.get_user_from_dn(distinguished_name)
        if not username:
            return ("", "")
        # now = str(datetime.now().timestamp())
        # passphrase = f"{username}-{now}"
        passphrase = f"{username}"
        password = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()

        ok = self.add_user(username, password, distinguished_name)
        if not ok:
            return ("", "")
        return (username, password)

    def get_user_from_dn(self, distinguished_name: str) -> str:
        """Helper function for generate_user. Gets the CN record from DN."""
        dn = distinguished_name.lower()
        if "cn=" not in dn:
            return ""
        nodes = distinguished_name.split(",")
        for node in nodes:
            if ("cn=" in node) or ("CN=" in node):
                snode = node.strip()
                start_index = snode.find("=") + 1
                return snode[start_index:]
