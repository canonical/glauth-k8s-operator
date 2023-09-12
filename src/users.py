#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Helper class for managing users in GLAuth."""

import hashlib
import logging
import psycopg2

# from datetime import datetime
from typing import List, Tuple

from ops.charm import CharmBase

logger = logging.getLogger(__name__)

BASE_UID = 5000
BASE_GID = 5500


class User:
    """Structure storing information about GLAuth User."""
    """Postgresql schema:"""
    """ id        | name       | uidnumber  | primarygroup | othergroups   |
        givenname | sn         | mail       | loginshell   | homedirectory |
        disabled  | passsha256 | passbcrypt | otpsecret    | yubikey       |
        sshkeys   | custattr   |"""
    def __init__(self, name: str, passsha256: str, uidnumber: int, primarygroup: int) -> None:
        self._name = name
        self._passsha256 = passsha256
        self._uidNumber = uidnumber
        self._primaryGroup = primarygroup

    def _get_insert_string(self) -> str:
        return f"INSERT INTO users(name, uidnumber, primarygroup, passsha256) VALUES('{self._name}', {self._uidNumber}, {self._primaryGroup}, '{self._passsha256}');"


class Group:
    """Structure storing information about GLAuth Group."""
    """Postgresql schema:"""
    """ id | name  | gidnumber |"""
    def __init__(self, name: str, gidnumber: int) -> None:
        self._name = name
        self._gidNumber = gidnumber

    def _get_insert_string(self) -> str:
        return f"INSERT INTO groups(name, gidnumber) VALUES('{self._name}', {self._gidNumber});"


class Capability:
    """Structure storing information about GLAuth Capabilities."""
    """Currently the only Capability supported is `search`"""
    """Postgresql schema:"""
    """ id | userid | action | object |"""
    def __init__(self, userid: int) -> None:
        self._userID = userid
        self._action = "search"
        self._object = "*"

    def _get_insert_string(self) -> str:
        return f"INSERT INTO capabilities(userid, action, object) VALUES({self._userID}, '{self._action}', '{self._object}');"


class GLAuthManager:
    """GLAuth Manager interacts with the Postgresql Database for GLAuth."""
    """Stores and retrieves objects from the users, groups, and capabilities tables."""

    def __init__(self, charm: CharmBase, databaseName: str, dbHost: str, dbUser: str, dbPassword: str, dbPort: str, baseDN: str, autogroup: bool = False) -> None:
        self._charm = charm
        # DO NOT ACCESS THESE DIRECTLY! USE PROPERTIES next_uidnumber and next_gidnumber
        self._current_user_number = 0
        self._current_group_number = 0
        # DB info
        self._database = databaseName
        self._dbHost = dbHost
        self._dbUser = dbUser
        self._dbPassword = dbPassword
        self._dbPort = dbPort
        # Functional settings
        self._autogroup = autogroup
        self._baseDN = baseDN

    @property
    def next_uidnumber(self) -> int:
        """Property for next UID Number for new Users."""
        temp_user_number = self._current_user_number
        self._current_user_number = self._current_user_number + 1
        return BASE_UID + 1 + temp_user_number

    @property
    def next_gidnumber(self) -> int:
        """Property for next GID Number for new Groups."""
        temp_group_number = self._current_group_number
        self._current_group_number = self._current_group_number + 1
        return BASE_GID + 1 + temp_group_number

    def _user_from_postgres_tuple(self, db_row: Tuple) -> User:
        return User(db_row[1], "unset", db_row[2], db_row[3])

    def _group_from_postgres_tuple(self, db_row: Tuple) -> Group:
        return Group(db_row[1], db_row[2])

    def _capability_from_postgres_tuple(self, db_row: Tuple) -> Capability:
        return Capability(db_row[1])

    def _check_if_user_exists(self, userName: str) -> bool:
        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM users WHERE name = '{userName}';")
        result = cursor.fetchall()

        if not result:
            return False

        # close db connection
        cursor.close()
        conn.close()

        return True

    def _check_if_group_exists(self, groupName: str) -> bool:
        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM groups WHERE name = '{groupName}';")
        result = cursor.fetchall()

        if not result:
            return False

        # close db connection
        cursor.close()
        conn.close()

        return True

    def _create_group(self, name: str, checked_if_exist: bool = False) -> bool:
        if not checked_if_exist:
            exists = self._check_if_group_exists(name)
            if exists:
                return False

        gid = self.next_gidnumber
        newGroup = Group(name=name, gidnumber=gid)

        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(newGroup._get_insert_string())
        conn.commit()

        # close db connection
        cursor.close()
        conn.close()
        return True

    def _create_user(self, name: str, password: str, primarygroupName: str) -> bool:
        exists = self._check_if_user_exists(name)
        if exists:
            return False
        exists = self._check_if_group_exists(primarygroupName)
        if not exists:
            if self._autogroup:
                self._create_group(name=primarygroupName, checked_if_exist=True)
            else:
                return False

        uid = self.next_uidnumber
        passwordHash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        gid = self._get_primary_group_id(primarygroupName)
        newUser = User(name, passwordHash, uid, gid)
        newCapability = Capability(uid)

        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(newUser._get_insert_string())
        cursor.execute(newCapability._get_insert_string())
        conn.commit()

        # close db connection
        cursor.close()
        conn.close()
        return True

    def _get_primary_group_name(self, gid: int) -> str:
        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM groups WHERE gidnumber = {gid};")
        result = cursor.fetchall()

        if not result:
            return ""

        resultGroup = self._group_from_postgres_tuple(result[0])

        # close db connection
        cursor.close()
        conn.close()
        return resultGroup._name

    def _get_primary_group_id(self, groupName: str) -> int:
        # open db connection
        conn = psycopg2.connect(database=self._database, host=self._dbHost, user=self._dbUser, password=self._dbPassword, port=self._dbPort)
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM groups WHERE name = '{groupName}';")
        result = cursor.fetchall()

        if not result:
            return 0

        resultGroup = self._group_from_postgres_tuple(result[0])

        # close db connection
        cursor.close()
        conn.close()
        return resultGroup._gidNumber

    def _generate_user(
        self, relation_name: str, relation_id: str, distinguished_name: str
    ) -> Tuple[str, str]:
        """Method for creating a user from distinguished name from ldap relation requirer."""
        """Password is the sha256 hashed value of relation_name-relation_id"""
        if not self._validate_dn(distinguished_name):
            return ("", "")

        username = self._get_user_from_dn(distinguished_name)
        if not username:
            return ("", "")
        # now = str(datetime.now().timestamp())
        # passphrase = f"{relation_id}-{now}"
        passphrase = f"{relation_name}-{relation_id}"
        password = hashlib.sha256(passphrase.encode("utf-8")).hexdigest()
        primary_group = self._get_primary_group_from_dn(distinguished_name)

        ok = self._create_user(username, password, primary_group)
        if not ok:
            return ("", "")
        return (username, password)

    def _get_user_from_dn(self, distinguished_name: str) -> str:
        """Helper function for _generate_user. Gets the CN record from DN."""
        dn = distinguished_name.lower()
        if "cn=" not in dn:
            return ""
        nodes = distinguished_name.split(",")
        for node in nodes:
            if ("cn=" in node) or ("CN=" in node):
                snode = node.strip()
                start_index = snode.find("=") + 1
                return snode[start_index:]

    def _get_primary_group_from_dn(self, distinguished_name: str) -> str:
        """Helper function for _generate_user. Extracts primary group record from DN."""
        dn = distinguished_name.lower()
        if "ou=" not in dn:
            return ""
        nodes = distinguished_name.split(",")
        for node in nodes:
            if ("ou=" in node) or ("OU=" in node):
                snode = node.strip()
                start_index = snode.find("=") + 1
                return snode[start_index:]

    def _validate_dn(self, distinguished_name: str) -> bool:
        """Helper function for _generate_user. Makes sure the recieved DN has the correct dc fields, and has one ou and one cn fields."""
        # check for name and group
        dn = distinguished_name.lower()
        if dn.count("ou=") != 1:
            return False
        if dn.count("cn=") != 1:
            return False
        # check domain components
        dcIndex = -1 * len(self._baseDN)
        dcs = distinguished_name[dcIndex:]
        return dcs == self._baseDN
