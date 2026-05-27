# RPA Udskrivning Frit valg
TBW

## Test

### Unit tests (ingen GUI nødvendig)
```bash
uv run pytest tests/ -v
```

### Alle integrationstests
```bash
uv run pytest tests/ -v -m integration -p no:faulthandler
```

### Specifik testfil
```bash
uv run pytest tests/test_integration_solteq.py -v -m integration -p no:faulthandler
uv run pytest tests/test_integration_initialization.py -v -m integration -p no:faulthandler
uv run pytest tests/test_integration_update_patient_info.py -v -m integration -p no:faulthandler
```

### Specifik testklasse
```bash
uv run pytest tests/test_integration_update_patient_info.py::TestUpdateStatus -v -m integration -p no:faulthandler
```

### Specifik enkelt test
```bash
uv run pytest tests/test_integration_update_patient_info.py::TestUpdateStatus::test_status_updated_successfully -v -m integration -p no:faulthandler
```

### Kun full flow tests på tværs af alle filer
```bash
uv run pytest tests/ -v -m integration -p no:faulthandler -k "FullFlow or FullItemFlow"
```

### Alt sammen (unit + integration)
```bash
uv run pytest tests/ -v -m "integration or not integration" -p no:faulthandler
```