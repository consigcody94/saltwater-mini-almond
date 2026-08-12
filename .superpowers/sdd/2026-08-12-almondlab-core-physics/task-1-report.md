# Task 1 report: bootstrap and public contracts

## Result

Task 1 is complete. The project is locked with `uv.lock`, its local `.venv`
uses the bundled CPython 3.12.13 interpreter, and the public enum/error
contract is covered by two passing tests.

## Files changed

- `.gitignore`
- `pyproject.toml`
- `uv.lock`
- `src/almondlab/__init__.py`
- `src/almondlab/contracts.py`
- `src/almondlab/errors.py`
- `tests/test_contracts.py`
- `.superpowers/sdd/2026-08-12-almondlab-core-physics/task-1-report.md`

## Toolchain and environment

- Bundled bootstrap interpreter: `C:\Users\fowlb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` (`Python 3.12.13`)
- Actual `uv` version: `uv 0.12.3 (507230998 2026-08-07 x86_64-pc-windows-msvc)`
- Final project interpreter: `Python 3.12.13`; `.venv/pyvenv.cfg` has `include-system-site-packages = false`.

Bootstrap commands run:

```powershell
& 'C:\Users\fowlb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap'
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\python.exe' -m pip install uv
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' lock
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' sync --extra dev --frozen
```

The initial sync auto-selected an inaccessible local CPython 3.12.10. Before
completion, the project-local environment was correctly recreated with:

```powershell
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' sync --extra dev --frozen --python 'C:\Users\fowlb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

Output confirmed removal/recreation of `.venv`, `Using CPython 3.12.13`, and
installation of all 61 locked packages.

## RED

Command:

```powershell
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py -v
```

Output (before either implementation module existed):

```text
collecting ... collected 0 items / 1 error
E   ModuleNotFoundError: No module named 'almondlab.contracts'
============================== 1 error in 0.44s ===============================
```

This was the expected missing-module contract failure.

## GREEN

Commands:

```powershell
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run pytest tests/test_contracts.py -v
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' run python -c "from almondlab.contracts import ConservedEntity, DataOrigin, ECKind, EvidenceLabel, GateState; from almondlab.errors import AlmondLabError, fail; print('public import smoke: PASS')"
```

Output:

```text
tests/test_contracts.py::test_public_enums_and_stable_error_code PASSED
tests/test_contracts.py::test_error_serializes_structured_fields PASSED
============================== 2 passed in 1.27s ==============================
public import smoke: PASS
Python 3.12.13
```

Final consistency command:

```powershell
& 'C:\Users\fowlb\Documents\Codex\2026-08-12\lets\work\.uv-bootstrap\Scripts\uv.exe' lock --check
```

Output: `Resolved 61 packages in 1ms` (exit 0).

## Commit

Bootstrap commit: `2eeb3ab52c0f4ab386ec207b9256aacc05c8fa00`
(`build: bootstrap locked almondlab package`).

## Self-review

- `EvidenceLabel`, `DataOrigin`, `ECKind`, `ConservedEntity`, and `GateState`
  use the required `StrEnum` members and literal values.
- `AlmondLabError` retains structured `code`, `message`, `field_path`, and
  optional `details`; `to_dict()` serializes fields directly rather than
  parsing error text.
- `fail(code, message, field_path)` always raises `AlmondLabError`, while its
  string representation includes the stable error code for pytest matching.
- The final project environment is isolated from global site-packages and
  launches with the bundled interpreter.

## Concerns

None outstanding. The initially auto-selected inaccessible interpreter was
replaced before final verification; `.venv` is ignored and was not committed.
