# Shared channels, chosen by the owner

Every channel is read through the owner's own Telegram account, so a user adding a channel made that account join it without the owner's say. We dropped per-user channels: monitored channels are shared by all users, only the owner adds or removes them, and other users can only file a channel request the owner approves or rejects (with a reason). With a Channel folder configured, the folder is the list of monitored channels and approvals write to it; without one, users cannot make requests and only the owner's `/add_channel` channels are monitored.

## Considered Options

- **Per-user channels with approval** (keep each user's own list, gate only the join): rejected because the account still holds every channel anyone asked for, and the folder would not describe what is monitored.

## Consequences

- An approved removal also makes the owner's account leave the channel, including one the owner followed before it was monitored; the approval prompt says so.
- Notifications go to every user currently authorized and not paused, not to "users subscribed to the channel".
