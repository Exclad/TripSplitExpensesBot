JOIN_CALLBACK_DATA = "trip:join"

DUPLICATE_TRIP_MESSAGE = (
    "There is already an active trip in this chat. Use /trip to see it, or /archive it before starting another."
)
MISSING_TRIP_MESSAGE = "No active trip yet. Tap Set up trip to get started."
ARCHIVED_TRIP_READ_ONLY_MESSAGE = "This trip is archived, so I won't change expenses. Use /reopen if the trip needs more edits."
ARCHIVE_CONFIRM_MESSAGE = "Archive this trip? It will stay visible, but expenses will be read-only until reopened."
REOPEN_CONFIRM_MESSAGE = "Reopen this trip? People will be able to add and edit expenses again."
JOIN_SUCCESS_MESSAGE = "You're in. I'll include you when this trip starts tracking expenses."
MANUAL_ADD_SUCCESS_TEMPLATE = "Added {name}. They can be mapped to a Telegram user later."
MEMBER_MAPPING_CONFIRM_TEMPLATE = (
    "Link {name} to your Telegram account? Existing expenses stay tied to {name}; this only helps me recognize them in chat."
)
MEMBER_MAPPING_SUCCESS_TEMPLATE = "Linked {name}. Existing expenses still use the same member record."
NEWTRIP_GUIDE_MESSAGE = "Tap Set up trip, or use /newtrip Korea 2026 SGD KRW as a shortcut."
ADD_EXPENSE_GUIDE_MESSAGE = "Tell me the amount and what it was for, like /add 25 lunch."
