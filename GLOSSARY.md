# Price watching

Users watch products and get notified when a Telegram channel they follow posts an offer for one of them.

## Language

**Match**:
A channel message that names a watched product, or links to its Amazon page, and, when the product has a target price, quotes a price at or below it; in a post listing several products, the price is taken from the paragraphs (or, in a one-per-line list, the lines) naming the product or holding its link. Every match is recorded in the user's price history, and stays there only while the product is watched: unwatching a product removes its matches. A product name without letters or digits names nothing, so that product matches only by link.
_Avoid_: Hit, alert, offer

**Realtime**:
The source of matches found in new messages as they arrive in a followed channel.
_Avoid_: Live, listener

**Backfill**:
The one-off scan of a channel's recent messages when the user adds that channel, and the source of the matches it finds.
_Avoid_: History scan, import

**Paused**:
The state of a user who receives no match notifications and no daily summary. Their matches are still recorded.
_Avoid_: Muted, disabled

**Channel folder**:
The one Telegram folder of the bot owner's account whose channels the owner follows without adding them one by one. A channel enters and leaves monitoring as it enters and leaves the folder; channels added by hand are not affected.
_Avoid_: Folder sync, chat list
