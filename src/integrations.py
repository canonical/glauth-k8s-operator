import hashlib
import logging
from dataclasses import dataclass
from secrets import token_bytes
from typing import Optional

from charms.glauth_k8s.v0.ldap import LdapProviderData
from configs import DatabaseConfig
from constants import DEFAULT_GID, DEFAULT_UID, GLAUTH_LDAP_PORT
from database import Capability, Group, Operation, User
from ops.charm import CharmBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BindAccount:
    cn: Optional[str] = None
    ou: Optional[str] = None
    password: Optional[str] = None


def _create_bind_account(dsn: str, user_name: str, group_name: str) -> BindAccount:
    with Operation(dsn) as op:
        if not op.select(Group, Group.name == group_name):
            group = Group(name=group_name, gid_number=DEFAULT_GID)
            op.add(group)

        if not (user := op.select(User, User.name == user_name)):
            new_password = hashlib.sha256(token_bytes()).hexdigest()
            user = User(
                name=user_name,
                uid_number=DEFAULT_UID,
                gid_number=DEFAULT_GID,
                password_sha256=new_password,
            )
            op.add(user)
        password = user.password_bcrypt or user.password_sha256

        if not op.select(Capability, Capability.user_id == DEFAULT_UID):
            capability = Capability(user_id=DEFAULT_UID)
            op.add(capability)

    return BindAccount(user_name, group_name, password)


class LdapIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._bind_account: Optional[BindAccount] = None

    def load_bind_account(self, user: str, group: str) -> None:
        database_config = DatabaseConfig.load(self._charm.database_requirer)
        self._bind_account = _create_bind_account(database_config.dsn, user, group)

    @property
    def provider_data(self) -> Optional[LdapProviderData]:
        if not self._bind_account:
            return None

        return LdapProviderData(
            url=f"ldap://{self._charm.config.get('hostname')}:{GLAUTH_LDAP_PORT}",
            base_dn=self._charm.config.get("base_dn"),
            bind_dn=f"cn={self._bind_account.cn},ou={self._bind_account.ou},{self._charm.config.get('base_dn')}",
            bind_password_secret=self._bind_account.password or "",
            auth_method="simple",
            starttls=True,
        )
