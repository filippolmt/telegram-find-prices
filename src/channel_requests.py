"""
Channel requests: users ask the owner to add a channel to the Channel folder, or to remove one from it.
"""

from enum import StrEnum

from sqlalchemy.orm import sessionmaker

from models import (
    ChannelInfo,
    ChannelRequest,
    ChannelRequestAction,
    ChannelRequester,
    User,
    identifier_in,
)
from translations import resolve_lang


class Filed(StrEnum):
    NEW = "new"
    SECONDED = "seconded"  # another user's request for the same change: the user waits for it too
    ALREADY_PENDING = "already_pending"  # the user's own
    OTHER_PENDING = "other_pending"  # the opposite change waits for the owner


class ChannelRequests:
    """The pending Channel requests: one per channel, with every user waiting for it."""

    def __init__(self, db_session_factory: sessionmaker):
        self._session_factory = db_session_factory

    def file(self, user_id: int, action: ChannelRequestAction, channel: ChannelInfo,
             invite_hash: str | None = None) -> tuple[Filed, ChannelRequest]:
        """File the request, or add the user to the pending one for the same channel.

        shortcut: an invite to a channel the account is not in has no identifier until joined (CheckChatInvite gives
        none), so it is told apart from a request for the same channel by @username or another invite; approving
        one answers the others naming the channel. Revisit if duplicate invite requests show up in /requests.
        """
        identifier, title = channel
        with self._session_factory() as session:
            same_channel = (identifier_in(ChannelRequest.identifier, [identifier]) if identifier
                            else ChannelRequest.invite_hash == invite_hash)
            request = session.query(ChannelRequest).filter(same_channel).first()
            if request is None:
                request = ChannelRequest(action=action, identifier=identifier, invite_hash=invite_hash, title=title)
                session.add(request)
                session.flush()
                filed = Filed.NEW
            elif request.action != action:
                filed = Filed.OTHER_PENDING
            elif session.get(ChannelRequester, (request.id, user_id)):
                filed = Filed.ALREADY_PENDING
            else:
                filed = Filed.SECONDED
            if filed in (Filed.NEW, Filed.SECONDED):
                session.add(ChannelRequester(request_id=request.id, user_id=user_id))
            session.commit()
            session.refresh(request)  # loaded before detaching: the commit expired it
            session.expunge(request)
            return filed, request

    def get(self, request_id: int) -> ChannelRequest | None:
        with self._session_factory() as session:
            request = session.get(ChannelRequest, request_id)
            if request:
                session.expunge(request)
            return request

    def pending(self, user_id: int | None = None) -> list[ChannelRequest]:
        """Every pending request, oldest first; only those user_id waits for, if given."""
        with self._session_factory() as session:
            query = session.query(ChannelRequest).order_by(ChannelRequest.id)
            if user_id is not None:
                query = query.join(ChannelRequester, ChannelRequester.request_id == ChannelRequest.id).filter(
                    ChannelRequester.user_id == user_id)
            requests = query.all()
            session.expunge_all()
            return requests

    def requesters(self, request_id: int) -> list[tuple[int, str | None]]:
        """Who waits for the request, as (user_id, username)."""
        with self._session_factory() as session:
            return [(u.user_id, u.username) for u in self._requesters(session, request_id)]

    @staticmethod
    def _requesters(session, request_id: int) -> list[User]:
        return (
            session.query(User)
            .join(ChannelRequester, ChannelRequester.user_id == User.user_id)
            .filter(ChannelRequester.request_id == request_id)
            .order_by(User.user_id)
            .all()
        )

    def close(self, request_id: int) -> list[tuple[int, str]] | None:
        """Delete a decided request, invite hash included; return its requesters as (user_id, language).

        None if it was already decided.
        """
        with self._session_factory() as session:
            requesters = [(u.user_id, resolve_lang(u.lang_code)) for u in self._requesters(session, request_id)]
            deleted = session.query(ChannelRequest).filter_by(id=request_id).delete()
            session.commit()
            if not deleted:
                return None
            return requesters
