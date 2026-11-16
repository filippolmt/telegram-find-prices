# Price watching

Users watch products and get notified when a Telegram channel they follow posts an offer for one of them.

## Language

**Match**:
A channel message that names a watched product, or links to its Amazon page, and, when the product has a target price, quotes a price at or below it; in a post listing several products, the price is taken from the paragraphs (or, in a one-per-line list, the lines) naming the product or holding its link. Every match is recorded in the user's price history, and stays there only while the product is watched: unwatching a product removes its matches. A product name without letters or digits names nothing, so that product matches only by link.
_Avoid_: Hit, alert, offer

**Offer link**:
The link to the matched product that a match notification carries: the one on the product's own lines of its post, else the first one of the post. Images and Telegram's own pages are never an offer link.
_Avoid_: Product link, deal link

**Realtime**:
The source of matches found in new messages as they arrive in a followed channel.
_Avoid_: Live, listener

**Backfill**:
The one-off scan of a channel's recent messages when the user adds that channel, and the source of the matches it finds.
_Avoid_: History scan, import

**Paused**:
The state of a user who receives no match notifications and no daily summary. Their matches are still recorded.
_Avoid_: Muted, disabled

**Monitored channel**:
A channel whose messages are matched against every user's products. Monitored channels are shared: no user has channels of their own. The owner decides which channels are monitored; the bot never acts on other channels of the owner's account.
_Avoid_: Followed channel, subscribed channel

**Channel folder**:
The one Telegram folder of the owner's account that, when the bot has one, holds exactly the monitored channels. Without it, the monitored channels are the ones the owner adds through the bot.
_Avoid_: Folder sync, chat list

**Owner**:
The person whose Telegram account the bot uses to read channels. Only the owner decides which channels are monitored.
_Avoid_: Admin, account holder

**Channel request**:
A user's request that a channel enter or leave the Channel folder; users can make one only when the bot has a Channel folder. It waits until the owner approves or rejects it; a rejection carries the owner's reason. An approved removal also takes the owner's account out of the channel. The owner's own changes need no request.
_Avoid_: Triage, proposal
