# Price watching

Users watch products and get notified when a Telegram channel they follow posts an offer for one of them.

## Language

**Match**:
A channel message that names a watched product and, when the product has a target price, quotes a price at or below it. Every match is recorded in the user's price history.
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
