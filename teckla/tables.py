from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import backref, relationship
from sqlalchemy.orm.decl_api import registry
from aiogoogle.auth.creds import UserCreds
from dataclasses import dataclass, field
from typing import List

import datetime

mapper = registry()


@mapper.mapped
@dataclass
class Scope:
    __tablename__ = 'scopes'

    __sa_dataclass_metadata_key__ = 'sa'

    id: int = field(metadata={
        'sa': Column(
                BigInteger,
                ForeignKey('tokens.id', ondelete='CASCADE', onupdate='CASCADE'),
                primary_key=True
            )
        }
    )
    scope: str = field(metadata={'sa': Column(String(200), primary_key=True)})


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
    valid: bool = field(default=True, metadata={'sa': Column(Boolean, nullable=False)})

    scopes: List[Scope] = field(
        default_factory=list,
        metadata={
            'sa': relationship(
                Scope,
                lazy='selectin',
                cascade='all, delete-orphan',
                backref=backref('token', lazy='selectin')
            )
        }
    )

    documents: List['Document'] = field(
        default_factory=list, metadata={
            'sa': relationship(
                'Document',
                lazy='selectin',
                cascade='all, delete-orphan',
                backref=backref('token', lazy='selectin')
            )
        }
    )

    def user_creds(self):
        return UserCreds(
            access_token=self.token,
            refresh_token=self.refresh_token,
            expires_at=self.expiry.isoformat()
        )

    def is_expired(self):
        return self.expiry < datetime.datetime.today()


@mapper.mapped
@dataclass
class Document:
    __tablename__ = 'documents'
    __sa_dataclass_metadata_key__ = 'sa'

    doc_id: str = field(metadata={'sa': Column(String(44), primary_key=True)})
    channel_id: int = field(metadata={'sa': Column(BigInteger, primary_key=True)})
    last_message: int = field(metadata={'sa': Column(BigInteger, nullable=False)})
    last_message_date: datetime.datetime = field(metadata={'sa': Column(DateTime(timezone=True))})
    discord_id: int = field(
        metadata={'sa': Column(BigInteger, ForeignKey(Token.id, ondelete='CASCADE', onupdate='CASCADE'))}
    )
