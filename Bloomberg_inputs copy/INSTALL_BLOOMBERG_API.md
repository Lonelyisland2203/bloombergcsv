# Bloomberg API Installation Guide

## Phase 0 Checkpoint: Bloomberg Python API Required

The Bloomberg API Python library (`blpapi`) is **not available via standard PyPI** and requires manual installation.

---

## Installation Methods (Choose One)

### Method 1: Bloomberg Terminal (Recommended)
If you have Bloomberg Terminal installed:

1. Open Bloomberg Terminal
2. Type `WAPI<GO>` and press Enter
3. Navigate to **Downloads** → **Python API**
4. Download the version matching your Python version:
   - Current system: **Python 3.13** (macOS)
   - Required file: `blpapi-*-cp313-*.whl`
5. Install the wheel:
   ```bash
   pip3 install ~/Downloads/blpapi-*-cp313-*.whl
   ```

### Method 2: Conda (If Available)
If you use Anaconda/Miniconda:
```bash
conda install -c conda-forge blpapi
```

### Method 3: Bloomberg Developer Portal
1. Visit: https://www.bloomberg.com/professional/support/api-library/
2. Log in with Bloomberg credentials
3. Download **Python SDK** for your OS
4. Extract and install:
   ```bash
   cd ~/Downloads/blpapi-python-*
   python3 setup.py install
   ```

---

## Verification Test

After installation, run this test:

```bash
python3 -c "import blpapi; print('✓ blpapi version:', blpapi.__version__)"
```

**Expected output**:
```
✓ blpapi version: 3.24.12  (or similar)
```

**If you see `ModuleNotFoundError`**, the installation was unsuccessful. Try a different method.

---

## Bloomberg Terminal DAPI Verification

Once `blpapi` is installed, verify Bloomberg Terminal Desktop API is enabled:

```bash
python3 -c "
import blpapi

session_options = blpapi.SessionOptions()
session_options.setServerHost('localhost')
session_options.setServerPort(8194)

session = blpapi.Session(session_options)
if session.start():
    print('✓ Bloomberg Terminal DAPI connection successful')
    session.stop()
else:
    print('✗ Bloomberg Terminal not running or DAPI disabled')
    print('  Solution: Open Bloomberg Terminal and type DAPI<GO> to enable')
"
```

**Expected output**:
```
✓ Bloomberg Terminal DAPI connection successful
```

---

## Common Issues

### Issue 1: "No module named 'blpapi'"
**Cause**: Package not installed or wrong Python environment
**Solution**:
- Verify Python version: `python3 --version`
- Check installation target: `pip3 show blpapi`
- Reinstall using correct method above

### Issue 2: "Failed to start session"
**Cause**: Bloomberg Terminal not running or DAPI disabled
**Solution**:
1. Open Bloomberg Terminal (blue icon)
2. Log in with credentials
3. Type `DAPI<GO>` and press Enter
4. Ensure **Desktop API** is enabled
5. Restart Terminal if needed

### Issue 3: "Import error: DLL load failed" (Windows) or "Library not loaded" (macOS)
**Cause**: Missing C++ runtime dependencies
**Solution**:
- macOS: Install Xcode Command Line Tools: `xcode-select --install`
- Windows: Install Visual C++ Redistributable from Bloomberg API package

---

## Next Steps

Once `blpapi` is installed and Terminal connectivity is verified:

1. Return to main terminal
2. Run: `python3 -c "import blpapi; print('Ready for Phase 0 completion')"`
3. If successful, Phase 0 can proceed to Task 12 (CSV validation) and Task 13 (field config)

---

## Support

- Bloomberg API Documentation: `WAPI<GO>` in Terminal
- Developer Forum: https://www.bloomberg.com/professional/support/api-library/
- Contact: Bloomberg Help Desk (HELP HELP on Terminal)

