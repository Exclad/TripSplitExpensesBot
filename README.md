# TripSplitExpenses

TripSplitExpenses is a Telegram bot for one trip group chat. It helps friends add messy travel expenses quickly, preserve original currencies, see balances, and settle up in the trip base currency.

## What Works In v1

- `/newtrip Demo Trip SGD` starts one active trip in the current Telegram group.
- `/newtrip` without enough details responds with a short guided prompt.
- `/trip` shows the trip, status, base currency, total spend, and members.
- Friends join by tapping **Join this trip** after the trip is created.
- `/members add Sam` adds someone manually when Telegram identity is unavailable.
- `/members claim` and `/members map Sam` link manual members to Telegram users later.
- `/add 25 lunch` starts a guided expense flow with category buttons, equal split by default, and a compact save confirmation.
- Exact split, multiple payers, itemized meals, shared charges, and custom categories are available from buttons.
- Foreign-currency expenses keep the original amount and show the trip-currency equivalent.
- Missing or wrong exchange rates can be overridden with a manual rate or exact trip-currency amount.
- Saved expense Details show payers, split details, exchange metadata, and per-expense history.
- `/refund` and `/correction` add auditable adjustments linked to the original expense.
- `/balance` shows a simplified settlement plan plus person, category, expense-list, and audit breakdowns.
- `/archive` makes a trip read-only while keeping it viewable; `/reopen` allows edits again.
- `/help` gives a compact overview with task-specific buttons.
- SQLite data lives in a configured data directory and survives restarts.

## Local Setup

Use Python 3.12 or newer.

```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

## Telegram Token

Create a bot with BotFather in Telegram, then copy `.env.example` to `.env` and set:

```env
TELEGRAM_BOT_TOKEN=replace-me
OWNER_TELEGRAM_ID=123456789
TRIPSPLIT_DATA_DIR=./data
```

Set `OWNER_TELEGRAM_ID` to your numeric Telegram user ID if you want the bot to answer only in groups where you are currently a member. This keeps random Telegram users from using your NAS-backed bot.

Do not commit `.env`. The example file only contains placeholders.

## Run Locally

```powershell
python -m tripsplitexpenses
```

By default, local data is written to `./data/tripsplitexpenses.sqlite3`. In Docker, data is written under `/data`.

## Docker Compose

Validate the Compose file:

```powershell
docker compose config
```

Start the bot on a NAS or local Docker host:

```powershell
docker compose up -d
```

The Compose service mounts `${TRIPSPLIT_DATA_DIR:-./data}` to `/data` and uses `restart: unless-stopped`.

## Portainer

The easiest Portainer setup is a Git-backed stack, not a tar upload:

1. Push this repository to a Git host your NAS can reach.
2. In Portainer, open **Stacks** -> **Add stack** -> **Git repository**.
3. Set **Compose path** to `docker-compose.yml`.
4. Add stack environment variables:
   - `TELEGRAM_BOT_TOKEN`: your BotFather token.
   - `OWNER_TELEGRAM_ID`: your numeric Telegram user ID.
   - `TRIPSPLIT_DATA_DIR`: an absolute NAS path such as `/volume1/docker/tripsplitexpenses/data`.
5. Deploy the stack.

Using Git keeps updates simple: push changes, then redeploy or enable Portainer GitOps updates. Avoid committing `.env`; keep secrets in Portainer's stack environment variables.

## Manual Smoke Test

### Trip Setup

1. Add the bot to your Telegram group.
2. Send `/newtrip Demo Trip SGD`.
3. Tap **Join this trip**.
4. Send `/members add Sam` for someone who did not tap the button.
5. Send `/trip` and confirm the trip name, base currency, total spend placeholder, and member list appear.
6. Restart the bot and send `/trip` again to confirm the trip and members are still there.

### Equal-Split Expense

1. Send `/add 25 lunch`.
2. Tap a category such as **Food**.
3. Review the compact confirmation: amount, payer, split members, category, date, and Save/Edit/Cancel buttons.
4. Tap **Save**.
5. Confirm the group receives a compact saved expense card with Edit, Delete, and Details buttons.
6. Send `/trip` and confirm total spent has increased.

### Exact Split

1. Start `/add 25 lunch` and choose a category.
2. Tap **Exact split**.
3. Enter each person's amount when prompted.
4. If the amounts do not total the expense, confirm the bot blocks saving and shows the expected total, entered total, and difference.
5. If the difference is one cent, use the auto-adjust option and confirm the expense can be saved.

### Foreign Currency

1. Send a foreign-currency expense such as `/add 1930 JPY ramen`.
2. Confirm the main card shows the original amount plus the SGD equivalent, for example `JPY 1,930 (~SGD 17.18)`.
3. Tap **Details** to see the exchange rate, date, and source.
4. Tap **Override rate** if the rate is missing or wrong.

### Balances and Settlement

1. Send `/balance`.
2. Confirm the first section is the settlement plan.
3. Use the buttons for person breakdown, category breakdown, expense list, and audit.

### Trip Closeout

1. Send `/archive` when the trip is done and confirm.
2. Confirm `/trip` and `/balance` still work.
3. Confirm `/add` is blocked while archived.
4. Send `/reopen` if more edits are needed.

## Telegram Privacy Note

Telegram bots cannot reliably fetch every group member. TripSplitExpenses therefore starts with a visible join button, plus manual add as a fallback. This keeps setup clear without pretending the bot can see more than Telegram allows.
