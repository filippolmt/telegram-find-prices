"""
Replay: run recent posts of real channels through two versions of the matcher and show what changes.

`dump` saves recent posts (text, hidden links, URL buttons) with the local user-client session.
`diff` matches every post against candidate product names (the first three words of each of its
lines) with `src/` at a git ref and with the working tree, and lists every price that changes.
Offline and repeatable, it covers what `live_check.py` cannot: posts and products nobody picked.

Run it with `make dump-posts` and `make replay` (see the Makefile for the arguments).
"""

import argparse
import asyncio
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parent
DEFAULT_POSTS = SRC.parent / "data" / "posts.json"


async def dump(channels: list[str], limit: int, out: Path) -> int:
    from telethon.tl.types import InlineButtonTypeUrl, MessageEntityTextUrl

    from bot import create_client
    from config import Config as cf

    if not channels:
        from database import SessionLocal
        from models import Channel

        with SessionLocal() as session:
            channels = [identifier for (identifier,) in session.query(Channel.identifier)]
    client = create_client(cf.CLIENT_SESSION_NAME, cf.API_ID, cf.API_HASH, session_string=cf.CLIENT_SESSION_STRING)
    await client.connect()
    if not await client.is_user_authorized():
        print("User session not authorized: run `make auth` first")
        return 1
    posts = []
    for identifier in channels:
        entity = await client.get_entity(int(identifier) if identifier.lstrip("-").isdigit() else identifier)
        async for message in client.iter_messages(entity, limit=limit):
            posts.append({
                "channel": identifier,
                "id": message.id,
                "message": message.message or "",
                "entities": [[e.offset, e.length, e.url] for e in message.entities or () if isinstance(e, MessageEntityTextUrl)],
                "buttons": [
                    button.type.url
                    for row in getattr(message.reply_markup, "rows", ())
                    for button in row.buttons
                    if isinstance(button.type, InlineButtonTypeUrl)
                ],
            })
    await client.disconnect()
    out.write_text(json.dumps(posts, ensure_ascii=False))
    print(f"{len(posts)} posts from {len(channels)} channels -> {out}")
    return 0


def candidate_names(text: str) -> set[str]:
    """First three words of each line: product names as a user might watch them, plus the post's other lines."""
    names = {" ".join(re.sub(r"^[\W_]+", "", line).split()[:3]).lower() for line in text.split("\n")}
    return {name for name in names if len(name) >= 8 and "http" not in name}


def score_posts(posts: list[dict]) -> dict[str, float | None]:
    """Price found for each post and candidate name by the matcher importable now (None: no match)."""
    from telethon.tl.custom.message import Message
    from telethon.tl.types import (
        InlineButtonTypeUrl,
        KeyboardInlineButton,
        KeyboardInlineButtonRow,
        MessageEntityTextUrl,
        PeerChannel,
        ReplyInlineMarkup,
    )

    from match_recorder import check_product_match, message_text

    scores = {}
    for post in posts:
        buttons = [KeyboardInlineButtonRow([KeyboardInlineButton("link", InlineButtonTypeUrl(url))]) for url in post["buttons"]]
        message = Message(
            id=post["id"],
            peer_id=PeerChannel(1),
            message=post["message"],
            entities=[MessageEntityTextUrl(offset=o, length=n, url=u) for o, n, u in post["entities"]],
            reply_markup=ReplyInlineMarkup(buttons) if buttons else None,
        )
        text = message_text(message).match
        for name in candidate_names(post["message"]):
            result = check_product_match(SimpleNamespace(name=name, asin=None, target_price=float("inf")), text)
            scores[f"{post['channel']}/{post['id']}|{name}"] = result and result["price_found"]
    return scores


def _score_with(src: Path, posts: Path) -> dict[str, float | None]:
    # A subprocess per version: both import modules under the same names.
    out = subprocess.run([sys.executable, __file__, "score", "--src", str(src), "--posts", str(posts)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def diff(base: str, posts: Path, samples: int) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", base, "src"], cwd=SRC.parent, capture_output=True, check=True).stdout
        tarfile.open(fileobj=io.BytesIO(archive)).extractall(tmp, filter="data")
        old = _score_with(Path(tmp) / "src", posts)
    new = _score_with(SRC, posts)

    changes = defaultdict(list)
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) != new.get(key):
            changes[key.split("/")[0]].append((key, old.get(key), new.get(key)))
    print(f"{len(new)} post/name pairs, {sum(map(len, changes.values()))} changed between {base} and the working tree")
    for channel, rows in sorted(changes.items()):
        kinds = Counter("lost" if n is None else "gained" if o is None else "changed" for _, o, n in rows)
        print(f"\n== {channel}: {dict(kinds)}")
        for key, o, n in rows[:samples]:
            print(f"  {key}: {o} -> {n}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    dump_args = commands.add_parser("dump", help="save recent posts (needs the user session: bot stopped)")
    dump_args.add_argument("--channel", action="append", default=[], help="username or numeric id; default: every channel in the DB")
    dump_args.add_argument("--limit", type=int, default=150, help="recent posts per channel")
    dump_args.add_argument("--out", type=Path, default=DEFAULT_POSTS)
    diff_args = commands.add_parser("diff", help="compare the matcher at a git ref with the working tree")
    diff_args.add_argument("--base", default="main")
    diff_args.add_argument("--posts", type=Path, default=DEFAULT_POSTS)
    diff_args.add_argument("--samples", type=int, default=10, help="changes shown per channel")
    score_args = commands.add_parser("score", help=argparse.SUPPRESS)
    score_args.add_argument("--src", type=Path, required=True)
    score_args.add_argument("--posts", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "dump":
        return asyncio.run(dump(args.channel, args.limit, args.out))
    if args.command == "diff":
        return diff(args.base, args.posts, args.samples)
    sys.path[0] = str(args.src)  # import the matcher of that version, not this file's
    print(json.dumps(score_posts(json.loads(args.posts.read_text()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
