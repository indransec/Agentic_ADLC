# Data Model: Operations Console (019)

No new table. Reads 016's link table (object kind and id → work item id) and sync health.

## Settings

| Setting | Where | Meaning |
| --- | --- | --- |
| `ADLC_BOARD_PUBLIC_URL` | API and board processes (`BoardSettings`) | the board's address for browsers; defaults to `ADLC_BOARD_URL` |

## API answers (read-only)

- **Mode**: `mode` (`console` or `inbox`), `board_url` (public address or null), `can_operate`
  (the person holds the CoE role).
- **Board item**: `work_item_id`, `url`.

## Web app session

- `mode` with the time it was read (re-read after 60 s).
