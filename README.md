# RPA Udskrivning Frit valg
TBW

## Test

Unit tests only (skips integration)
```bash
uv run pytest tests/ -v
```

All integration tests
```bash
uv run pytest tests/ -v -m integration -p no:faulthandler
```

Just the initialization integration tests
```bash
uv run pytest tests/test_integration_initialization.py -v -m integration -p no:faulthandler
```

Just the startup integration tests
```bash
uv run pytest tests/test_integration_solteq.py -v -m integration -p no:faulthandler
```

Everything together (unit + integration)
```bash
uv run pytest tests/ -v -m "integration or not integration" -p no:faulthandler
```