# Replay recordings (feature 008)

One folder per reference use case (`data/reference_usecases/<id>.yaml`), one `<agent>.jsonl` per
agent: the model's replies in call order (`text`, `tokens_in`, `tokens_out`). No prompts, no keys.

They start as hand-written replies (synthetic artifacts plus one knowledge read and a citation)
and are replaced by a live recording:

```bash
uv run adlc-replay --profile dev --record tests/fixtures/replays
```
