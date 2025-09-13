from typing import Any
import subprocess
import os
import tempfile
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("android-puppeteer", "Puppeteer for Android")


@mcp.tool()
async def list_emulators() -> dict:
    """List all available Android emulators and devices with their name, ID, and status"""
    try:
        # Execute adb devices to get connected devices/emulators
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True)

        devices = []
        lines = result.stdout.strip().split('\n')[1:]  # Skip header line

        for line in lines:
            if line.strip():
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]

                    # Try to get AVD name if it's an emulator
                    avd_name = "Unknown"
                    if device_id.startswith('emulator-'):
                        try:
                            avd_result = subprocess.run(
                                ['adb', '-s', device_id, 'emu', 'avd', 'name'],
                                capture_output=True, text=True, timeout=5
                            )
                            if avd_result.returncode == 0:
                                avd_name = avd_result.stdout.strip()
                        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                            pass
                    else:
                        # For physical devices, try to get device model
                        try:
                            model_result = subprocess.run(
                                ['adb', '-s', device_id, 'shell', 'getprop', 'ro.product.model'],
                                capture_output=True, text=True, timeout=5
                            )
                            if model_result.returncode == 0:
                                avd_name = model_result.stdout.strip()
                        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                            pass

                    devices.append({
                        "id": device_id,
                        "name": avd_name,
                        "status": status,
                        "type": "emulator" if device_id.startswith('emulator-') else "device"
                    })

        return {
            "success": True,
            "devices": devices,
            "count": len(devices)
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to execute adb command: {e}",
            "devices": [],
            "count": 0
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "devices": [],
            "count": 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "devices": [],
            "count": 0
        }


@mcp.tool()
async def take_screenshot(device_id: str = None) -> dict:
    """Take a screenshot for the specified device/emulator. If no device_id is provided, uses the default device."""
    try:
        # Use android-puppeteer/ss directory for screenshots
        current_dir = os.path.dirname(os.path.abspath(__file__))
        screenshots_dir = os.path.join(current_dir, "ss")
        os.makedirs(screenshots_dir, exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(screenshots_dir, filename)

        # Build adb command
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['exec-out', 'screencap', '-p'])

        # Execute screenshot command
        result = subprocess.run(cmd, capture_output=True, check=True)

        # Save screenshot to file
        with open(filepath, 'wb') as f:
            f.write(result.stdout)

        return {
            "success": True,
            "message": f"Screenshot saved successfully",
            "filepath": filepath,
            "filename": filename,
            "device_id": device_id or "default"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to take screenshot: {e}",
            "filepath": None
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "filepath": None
        }
    except PermissionError:
        return {
            "success": False,
            "error": f"Permission denied: Cannot create directory or write to {screenshots_dir}",
            "filepath": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "filepath": None
        }


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')