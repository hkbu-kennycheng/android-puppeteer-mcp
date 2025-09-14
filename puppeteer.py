from typing import Any
import subprocess
import os
import tempfile
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageFont
import io

# Initialize FastMCP server
mcp = FastMCP("android-puppeteer", "Puppeteer for Android")


@mcp.tool()
async def list_emulators() -> dict:
    """List all available Android emulators and devices with their name, ID, status, and dimensions"""
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

                    # Get device dimensions
                    width, height, dimensions = None, None, None
                    try:
                        size_result = subprocess.run(
                            ['adb', '-s', device_id, 'shell', 'wm', 'size'],
                            capture_output=True, text=True, timeout=5
                        )
                        if size_result.returncode == 0:
                            output = size_result.stdout.strip()
                            if 'Physical size:' in output:
                                size_part = output.split('Physical size:')[1].strip()
                                width, height = map(int, size_part.split('x'))
                                dimensions = f"{width}x{height}"
                    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
                        pass

                    devices.append({
                        "id": device_id,
                        "name": avd_name,
                        "status": status,
                        "type": "emulator" if device_id.startswith('emulator-') else "device",
                        "width": width,
                        "height": height,
                        "dimensions": dimensions
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
async def take_screenshot(device_id: str = None, name: str = None) -> dict:
    """Take a screenshot for the specified device/emulator. If no device_id is provided, uses the default device."""
    try:
        # Use android-puppeteer/ss directory for screenshots
        current_dir = os.path.dirname(os.path.abspath(__file__))
        screenshots_dir = os.path.join(current_dir, "ss")
        os.makedirs(screenshots_dir, exist_ok=True)

        # Generate filename
        if name:
            # Use custom name, ensure it has .png extension
            if not name.endswith('.png'):
                filename = f"{name}.png"
            else:
                filename = name
        else:
            # Use timestamp if no name provided
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

        # Create merged image with original and grid overlay
        try:
            # Open the screenshot with PIL
            img = Image.open(io.BytesIO(result.stdout))
            width, height = img.size

            # Create a copy for grid overlay
            grid_img = img.copy()
            draw = ImageDraw.Draw(grid_img)

            # Grid settings
            grid_size = 200
            grid_color = (255, 0, 0, 128)  # Semi-transparent red
            text_color = (255, 255, 255)  # White text

            # Try to use fonts for both grid and labels
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 32)
                label_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 48)
            except (OSError, IOError):
                font = ImageFont.load_default()
                label_font = ImageFont.load_default()

            # Draw vertical grid lines
            for x in range(0, width + 1, grid_size):
                if x <= width:
                    draw.line([(x, 0), (x, height)], fill=grid_color, width=1)

            # Draw horizontal grid lines
            for y in range(0, height + 1, grid_size):
                if y <= height:
                    draw.line([(0, y), (width, y)], fill=grid_color, width=1)

            # Draw coordinates at all grid intersections
            for x in range(0, width + 1, grid_size):
                for y in range(0, height + 1, grid_size):
                    if x <= width and y <= height:
                        coord_text = f"({x},{y})"
                        bbox = draw.textbbox((0, 0), coord_text, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]

                        # Position text to avoid going off screen
                        text_x = min(x + 2, width - text_width - 2)
                        text_y = min(y + 2, height - text_height - 2)

                        # Draw text with semi-transparent background for visibility
                        draw.rectangle([text_x - 1, text_y - 1, text_x + text_width + 1, text_y + text_height + 1],
                                     fill=(0, 0, 0, 180))
                        draw.text((text_x, text_y), coord_text, fill=text_color, font=font)

            # Create merged image with labels
            label_height = 60  # Space for labels above images
            merged_width = width * 2 + 20  # Two images with small gap
            merged_height = height + label_height

            # Create merged image with white background
            merged_img = Image.new('RGB', (merged_width, merged_height), color=(255, 255, 255))
            merged_draw = ImageDraw.Draw(merged_img)

            # Add labels
            merged_draw.text((width // 2 - 50, 10), "Original", fill=(0, 0, 0), font=label_font)
            merged_draw.text((width + 10 + width // 2 - 80, 10), "Coordinates", fill=(0, 0, 0), font=label_font)

            # Paste original image on the left
            merged_img.paste(img, (0, label_height))

            # Paste grid image on the right
            merged_img.paste(grid_img, (width + 20, label_height))

            # Save only the merged image
            merged_img.save(filepath, 'PNG')

        except Exception as e:
            # If merged creation fails, save original screenshot as fallback
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


@mcp.tool()
async def tap(x: int, y: int, device_id: str = None, duration: int = None) -> dict:
    """Tap on specific coordinates on the Android screen. Use duration for long press (in milliseconds)."""
    try:
        # Validate coordinates
        if x < 0 or y < 0:
            return {
                "success": False,
                "error": "Coordinates must be positive integers",
                "x": x,
                "y": y
            }

        # Build adb command
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])

        if duration and duration > 0:
            # Long press using swipe command (swipe from point to same point with duration)
            cmd.extend(['shell', 'input', 'swipe', str(x), str(y), str(x), str(y), str(duration)])
            action_type = f"long press ({duration}ms)"
        else:
            # Regular tap
            cmd.extend(['shell', 'input', 'tap', str(x), str(y)])
            action_type = "tap"

        # Execute tap command
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {
            "success": True,
            "message": f"Successfully executed {action_type} at coordinates ({x}, {y})",
            "x": x,
            "y": y,
            "action_type": action_type,
            "device_id": device_id or "default"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to execute tap: {e}",
            "stderr": e.stderr if e.stderr else "",
            "x": x,
            "y": y
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "x": x,
            "y": y
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "x": x,
            "y": y
        }




if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')