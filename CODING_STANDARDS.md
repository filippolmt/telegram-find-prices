# Coding standards (review)

Judgement calls for the reviewer; mechanical rules live in ruff and the tests.

- **Re-check after a conversation.** A check made before awaiting a user's reply (owner, authorization, a row's existence) is repeated once the reply arrives, before acting on it.
- **Reconcile derived state.** When a monitored channel, a user or a product changes, every record derived from it (pending Channel requests, matches) is updated on every path that changes it, not only the path the feature added.
- **Authorize at the send site.** Every bot message to a user other than the sender checks the user is still authorized when it is sent.
