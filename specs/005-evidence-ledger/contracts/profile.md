# Contract: Use-case profile

## Versions

- **Version 0** is the empty profile.
- **When a run closes** with `pass` or `exception` and its `emitted` values are not empty, the
  close transaction writes version `n+1` = version `n`'s values, with each emitted name
  replaced by its new value; a table is replaced whole, never merged by row. The version
  records `source_run_id`. Open runs keep the version they started with.
- **Artifact references** in emitted values are stored as `{artifact, version, content_hash}`.
- **When a run opens**, it records `profile_version = n` (the current version).

## Reading

```text
class ProfileSource(Protocol):           # feature 004, extended
    values(usecase_id: str, run_id: str | None = None) -> Mapping[str, Any]
```

- **With `run_id`**: the values of the profile version recorded on that run. **Without it**: the
  current version.
- **Parameter resolution** (004): a value whose name equals a guardrail name is the use case's
  proposed value. A plain number is used as is; a mapping with `value` uses that.
- **Policy evidence**: `profile.<name>` in an expression reads the run's version. It is real
  evidence, not synthetic.

## Read operation

`profile_history(usecase_id)` returns versions with values, source run and time, for 007 and
013.
