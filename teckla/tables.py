from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm.decl_api import registry
from aiogoogle.auth.creds import UserCreds
from dataclasses import dataclass, field
from sqlalchemy.orm import relationship
from typing import List

import datetime

mapper = registry()


@mapper.mapped
@dataclass
class Scope:
    __tablename__ = 'scopes'

    __sa_dataclass_metadata_key__ = 'sa'

    id: int = field(metadata={'sa': Column(BigInteger, ForeignKey('tokens.id'), primary_key=True)})
    scope: str = field(metadata={'sa': Column(String(200), nullable=False)})


@mapper.mapped
@dataclass
class Token:
    __tablename__ = 'tokens'

    __sa_dataclass_metadata_key__ = 'sa'

    id: int = field(metadata={'sa': Column(BigInteger, primary_key=True)})
    token: str = field(metadata={'sa': Column(String(200), nullable=False)})
    expiry: datetime.datetime = field(
        metadata={'sa': Column(DateTime(timezone=True), nullable=False)}
    )
    refresh_token: str = field(default=None, metadata={'sa': Column(String(200))})

    scopes: List[Scope] = field(
        default_factory=list, metadata={'sa': relationship(Scope, lazy='selectin')}
    )

    def user_creds(self):
        return UserCreds(
            access_token=self.token,
            refresh_token=self.refresh_token,
            expires_at=self.expiry.isoformat()
        )
