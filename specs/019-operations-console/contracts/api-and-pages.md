# Contract: API additions and console pages (019)

## API (read-only; every command unchanged)

| Method and path | Who | Answer |
| --- | --- | --- |
| `GET /board/mode` | any signed-in person | `{"mode": "console"\|"inbox", "board_url": str\|null, "can_operate": bool}` |
| `GET /board/items/{kind}/{object_id}` | any signed-in person | `{"work_item_id": int, "url": str}`; 404 when not on the board; 422 for an unknown kind (the API's convention for invalid input); when the sync is disabled, 404 |

`object_id` may contain `/` (run ids): the route takes the rest of the path.

## Web app

| Page | Console mode | Inbox mode |
| --- | --- | --- |
| Run (`?run=` deep link) | evidence and artifact editing; "Decide on the board" link | as 007 |
| Use cases (default in console) | as 007/013 | as 007/013 |
| Journey, Activity, Portfolio, Dead letters | as 013/007 | as 013/007 |
| Sync status (operators only) | 016 health, reconcile now, re-queue | same |
| Inbox, New use case, Clarification, Escalation, Waiver | a notice: made on the board, with a link | as 007 (Inbox is the default) |
