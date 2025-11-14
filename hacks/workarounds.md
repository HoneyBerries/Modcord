# vLLM Workarounds

This document describes patches and workarounds for known issues with vLLM in this project.

## WSL Detection Patch

### Issue

The vLLM platform detection logic incorrectly identifies WSL environments, causing platform-specific initialization issues.

### Solution

Apply the `interface.patch` file to fix the WSL detection in vLLM's platform interface.

### How to Apply

1. Navigate to your project directory:
   ```bash
   cd "/path/to/your/project/root"
   ```

2. Apply the patch:
   ```bash
   patch <your-venv>/lib/python3.12/site-packages/vllm/platforms/interface.py < hacks/interface.patch
   ```

3. Verify the patch was applied successfully:
   ```bash
   cat venv/lib/python3.12/site-packages/vllm/platforms/interface.py | grep -A 3 "def in_wsl"
   ```

   You should see:
   ```python
   def in_wsl() -> bool:
       # Reference: https://github.com/microsoft/WSL/issues/4071
       uname_str = " ".join(platform.uname()).lower()
       return "microsoft" in uname_str and "wsl2" not in uname_str
   ```

### What Changed

The `in_wsl()` function now properly differentiates between WSL1 and WSL2 environments by checking for the presence of "wsl2" in the uname string, while still detecting WSL1 systems that contain "microsoft" in their uname output.

### Reverting the Patch

If you need to revert the patch:

```bash
patch -R <your-venv>/lib/python3.12/site-packages/vllm/platforms/interface.py < hacks/interface.patch
```

### For Fresh Installations

After installing vLLM in a new virtual environment, apply this patch before running the application to ensure proper platform detection.