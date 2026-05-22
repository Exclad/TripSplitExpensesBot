# TripSplitExpenses

TripSplitExpenses is a Telegram bot for one trip group chat. It helps friends add messy travel expenses quickly, preserve original currencies, see balances, and settle up in the trip base currency.

## What Works

- Persistent Telegram buttons expose the common actions: **Add expense**, **Balances**, **People**, **Expenses**, **Members**, and **Trip**.
- **Set up trip** walks the group through trip name, settlement currency, and default country expense currency.
- `/newtrip Korea 2026 SGD KRW` remains available as a shortcut.
- `/trip` shows the trip, status, settlement currency, default expense currency, total spend, and members.
- Friends join by tapping **Join this trip** after the trip is created.
- `/members add Sam` adds someone manually when Telegram identity is unavailable.
- `/members claim` and `/members map Sam` link manual members to Telegram users later.
- **Add expense** starts a guided expense flow that defaults to the trip country currency, with a button to switch to the settlement currency.
- `/add 25 lunch` remains available as a shortcut.
- Exact split, multiple payers, itemized meals, shared charges, and custom categories are available from buttons.
- Foreign-currency expenses keep the original amount and show the trip-currency equivalent.
- Live exchange rates are fetched automatically when available; missing or wrong rates can still be overridden with a manual rate or exact trip-currency amount.
- Saved expense Details show payers, split details, exchange metadata, and per-expense history.
- `/refund` and `/correction` add auditable adjustments linked to the original expense.
- **Balances**, **People**, and **Expenses** buttons expose settlement, person breakdown, and expense list views. `/balance` remains available as a shortcut.
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
   - `TRIPSPLIT_DATA_DIR`: an absolute NAS path such as `/volume2/docker/trip-expenses-bot`.
5. Deploy the stack.

Using Git keeps updates simple: push changes, then redeploy or enable Portainer GitOps updates. Avoid committing `.env`; keep secrets in Portainer's stack environment variables.

The Compose file joins an existing external Docker network named `allowed-internet` and runs the container as `0:0` so SQLite can write to NAS bind mounts that do not map neatly to the image's non-root user. Create that Docker network in Portainer before deploying, or rename the network in `docker-compose.yml` to match your NAS.

## Manual Smoke Test

### Trip Setup

1. Add the bot to your Telegram group.
2. Tap **Set up trip**.
3. Enter the trip name.
4. Enter the settlement currency, for example `SGD`.
5. Enter the default country expense currency, for example `KRW`.
6. Confirm the trip and tap **Join this trip**.
7. Open **Members** and add anyone missing with `/members add Name`.
8. Tap **Trip** and confirm the trip name, settlement currency, default expense currency, total spend placeholder, and member list appear.
9. Restart the bot and tap **Trip** again to confirm the trip and members are still there.

### Equal-Split Expense

1. Tap **Add expense**.
2. Enter the amount. The bot assumes the default country currency unless you tap **Use SGD instead** first.
3. Enter what it was for.
4. Tap a category such as **Food**.
5. Confirm who should split it with the member buttons.
6. Review the compact confirmation: amount, payer, split members, category, date, and Save/Edit/Cancel buttons.
7. Tap **Save**.
8. Confirm the group receives a compact saved expense card with Edit, Delete, and Details buttons.
9. Tap **Trip** and confirm total spent has increased.

### Exact Split

1. Start `/add 25 lunch` and choose a category.
2. Tap **Exact split**.
3. Enter each person's amount when prompted.
4. If the amounts do not total the expense, confirm the bot blocks saving and shows the expected total, entered total, and difference.
5. If the difference is one cent, use the auto-adjust option and confirm the expense can be saved.

### Foreign Currency

1. Tap **Add expense** and enter a country-currency expense such as `3500`.
2. Confirm the main card shows the original amount plus the SGD equivalent, for example `KRW 3,500.00 (~SGD 3.50)`.
3. Tap **Details** to see the exchange rate, date, and source.
4. Tap **Override rate** if the rate is missing or wrong.

### Balances and Settlement

1. Tap **Balances**.
2. Confirm the first section is the settlement plan.
3. Tap **People** for person breakdown.
4. Tap **Expenses** for newest-first expense list.
5. Use the inline balance buttons for category breakdown and audit.

### Trip Closeout

1. Send `/archive` when the trip is done and confirm.
2. Confirm `/trip` and `/balance` still work.
3. Confirm `/add` is blocked while archived.
4. Send `/reopen` if more edits are needed.

## Telegram Privacy Note

Telegram bots cannot reliably fetch every group member. TripSplitExpenses therefore starts with a visible join button, plus manual add as a fallback. This keeps setup clear without pretending the bot can see more than Telegram allows.
