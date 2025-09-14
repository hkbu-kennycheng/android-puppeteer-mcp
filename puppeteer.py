from typing import Any
import subprocess
import os
import tempfile
from datetime import datetime
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP
from PIL import Image, ImageDraw, ImageFont
import io
import uiautomator2 as u2
from xml.etree import ElementTree
import re
import random
import signal
import threading

# Initialize FastMCP server
mcp = FastMCP("android-puppeteer", "Puppeteer for Android")

# Global dictionary to track active video recordings
active_recordings = {}


# Element detection classes
@dataclass
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def to_string(self):
        return f'[{self.x1},{self.y1}][{self.x2},{self.y2}]'


@dataclass
class CenterCord:
    x: int
    y: int

    def to_string(self):
        return f'({self.x},{self.y})'


@dataclass
class ElementNode:
    name: str
    coordinates: CenterCord
    bounding_box: BoundingBox
    class_name: str = ""
    clickable: bool = False
    focusable: bool = False


# Interactive element classes (common Android UI elements)
INTERACTIVE_CLASSES = [
    "android.widget.Button",
    "android.widget.ImageButton",
    "android.widget.EditText",
    "android.widget.CheckBox",
    "android.widget.RadioButton",
    "android.widget.Switch",
    "android.widget.ToggleButton",
    "android.widget.Spinner",
    "android.widget.SeekBar",
    "android.widget.RatingBar",
    "android.widget.TabHost",
    "android.widget.NumberPicker",
    "android.support.v7.widget.RecyclerView",
    "androidx.recyclerview.widget.RecyclerView",
    "android.widget.ListView",
    "android.widget.GridView",
    "android.widget.ScrollView",
    "android.widget.HorizontalScrollView",
    "androidx.viewpager.widget.ViewPager",
    "androidx.viewpager2.widget.ViewPager2"
]


# Utility functions
def extract_coordinates(node):
    """Extract coordinates from Android UI hierarchy node bounds attribute"""
    attributes = node.attrib
    bounds = attributes.get('bounds')
    match = re.search(r'\[(\d+),(\d+)]\[(\d+),(\d+)]', bounds)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        return x1, y1, x2, y2
    return None


def get_center_coordinates(coordinates: tuple[int, int, int, int]):
    """Calculate center coordinates from bounding box"""
    x_center, y_center = (coordinates[0] + coordinates[2]) // 2, (coordinates[1] + coordinates[3]) // 2
    return x_center, y_center


def get_element_name(node) -> str:
    """Get a human-readable name for the UI element"""
    # Try to get text content first, then content description
    name = "".join([n.get('text') or n.get('content-desc') for n in node if n.get('class') == "android.widget.TextView"]) or node.get('content-desc') or node.get('text')
    return name if name else f"{node.get('class', 'Unknown').split('.')[-1]}"


def is_interactive(node) -> bool:
    """Check if a UI element is interactive"""
    attributes = node.attrib
    return (attributes.get('focusable') == "true" or
            attributes.get('clickable') == "true" or
            attributes.get('class') in INTERACTIVE_CLASSES)


def get_device_connection(device_id: str = None):
    """Get uiautomator2 device connection"""
    try:
        if device_id:
            device = u2.connect(device_id)
        else:
            device = u2.connect()  # Connect to default device
        # Test connection
        device.info
        return device
    except Exception as e:
        raise ConnectionError(f"Failed to connect to device {device_id}: {e}")


def get_ui_elements(device_id: str = None) -> list[ElementNode]:
    """Get interactive UI elements from the device"""
    try:
        device = get_device_connection(device_id)

        # Get UI hierarchy XML
        tree_string = device.dump_hierarchy()
        element_tree = ElementTree.fromstring(tree_string)

        interactive_elements = []
        nodes = element_tree.findall('.//node[@visible-to-user="true"][@enabled="true"]')

        for node in nodes:
            if is_interactive(node):
                coords = extract_coordinates(node)
                if not coords:
                    continue

                x1, y1, x2, y2 = coords
                name = get_element_name(node)

                if not name:
                    continue

                x_center, y_center = get_center_coordinates((x1, y1, x2, y2))

                interactive_elements.append(ElementNode(
                    name=name,
                    coordinates=CenterCord(x=x_center, y=y_center),
                    bounding_box=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    class_name=node.get('class', ''),
                    clickable=node.get('clickable') == 'true',
                    focusable=node.get('focusable') == 'true'
                ))

        return interactive_elements
    except Exception as e:
        raise RuntimeError(f"Failed to get UI elements: {e}")


def annotated_screenshot(device_id: str = None) -> tuple[Image.Image, list[ElementNode]]:
    """Take screenshot and annotate with UI elements"""
    try:
        # Get screenshot using adb
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['exec-out', 'screencap', '-p'])

        result = subprocess.run(cmd, capture_output=True, check=True)
        screenshot = Image.open(io.BytesIO(result.stdout))

        # Get UI elements
        nodes = get_ui_elements(device_id)

        # Use original screenshot without padding
        draw = ImageDraw.Draw(screenshot)
        font_size = 12
        try:
            font = ImageFont.truetype('arial.ttf', font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype('/System/Library/Fonts/Arial.ttf', font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

        def get_random_color():
            return "#{:06x}".format(random.randint(0, 0xFFFFFF))

        def draw_annotation(label, node: ElementNode):
            bounding_box = node.bounding_box
            color = get_random_color()

            # Use original coordinates without scaling or padding
            adjusted_box = (
                bounding_box.x1,
                bounding_box.y1,
                bounding_box.x2,
                bounding_box.y2
            )

            # Draw bounding box
            draw.rectangle(adjusted_box, outline=color, width=2)

            # Label dimensions
            label_text = f"{label}: {node.name}"
            bbox = draw.textbbox((0, 0), label_text, font=font)
            label_width = bbox[2] - bbox[0]
            label_height = bbox[3] - bbox[1]
            left, top, _, _ = adjusted_box

            # Label position above bounding box
            label_x1 = max(left, 0)
            label_y1 = max(top - label_height - 4, 0)
            label_x2 = min(label_x1 + label_width + 4, screenshot.width - 1)
            label_y2 = label_y1 + label_height + 4

            # Draw label background and text
            draw.rectangle([(label_x1, label_y1), (label_x2, label_y2)], fill=color)
            draw.text((label_x1 + 2, label_y1 + 2), label_text, fill=(255, 255, 255), font=font)

        # Draw annotations sequentially
        for i, node in enumerate(nodes):
            draw_annotation(i, node)

        return screenshot, nodes

    except Exception as e:
        raise RuntimeError(f"Failed to create annotated screenshot: {e}")


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
async def take_screenshot(device_id: str = None, name: str = None, annotate_elements: bool = True) -> dict:
    """Take a screenshot for the specified device/emulator. If no device_id is provided, uses the default device.
    Set annotate_elements=False to take a plain screenshot without UI element annotations."""
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

        # Use annotated screenshot by default
        if annotate_elements:
            try:
                # Use annotated screenshot with UI elements
                annotated_img, ui_elements = annotated_screenshot(device_id)

                # Save the annotated image
                annotated_img.save(filepath, 'PNG')

                # Convert UI elements to the same format as get_ui_elements_info
                elements_info = []
                for i, element in enumerate(ui_elements):
                    elements_info.append({
                        "index": i,
                        "name": element.name,
                        "center_coordinates": {
                            "x": element.coordinates.x,
                            "y": element.coordinates.y
                        },
                        "bounding_box": {
                            "x1": element.bounding_box.x1,
                            "y1": element.bounding_box.y1,
                            "x2": element.bounding_box.x2,
                            "y2": element.bounding_box.y2
                        },
                        "class_name": element.class_name,
                        "clickable": element.clickable,
                        "focusable": element.focusable
                    })

                return {
                    "success": True,
                    "message": f"Annotated screenshot saved successfully with {len(ui_elements)} UI elements",
                    "filepath": filepath,
                    "filename": filename,
                    "device_id": device_id or "default",
                    "ui_elements_count": len(ui_elements),
                    "ui_elements": elements_info,
                    "annotated": True
                }
            except Exception as e:
                # Fallback to regular screenshot if annotation fails
                pass

        # Take regular screenshot without annotations
        result = subprocess.run(cmd, capture_output=True, check=True)

        # Save the plain screenshot
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
async def press(x: int, y: int, device_id: str = None, duration: int = None) -> dict:
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


@mcp.tool()
async def long_press(x: int, y: int, device_id: str = None) -> dict:
    """Long press on specific coordinates on the Android screen."""
    try:
        # Validate coordinates
        if x < 0 or y < 0:
            return {
                "success": False,
                "error": "Coordinates must be positive integers",
                "x": x,
                "y": y
            }

        # Get device connection
        device = get_device_connection(device_id)

        # Execute long press using gesture with 1.5 second duration
        # Long press with gesture: [ (x, y, delay_ms) ]
        device.gesture(
            (x, y, 0),     # touch down immediately
            (x, y, 1500)   # stay at same position for 1500 ms (1.5 seconds)
        )

        return {
            "success": True,
            "message": f"Successfully executed long press at coordinates ({x}, {y}) for 1.5 seconds",
            "x": x,
            "y": y,
            "duration_ms": 1500,
            "action_type": "long_press",
            "device_id": device_id or "default"
        }

    except ConnectionError as e:
        return {
            "success": False,
            "error": f"Device connection failed: {e}",
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


@mcp.tool()
async def get_ui_elements_info(device_id: str = None) -> dict:
    """Get detailed information about all interactive UI elements on the screen including their coordinates and properties."""
    try:
        elements = get_ui_elements(device_id)

        elements_info = []
        for i, element in enumerate(elements):
            elements_info.append({
                "index": i,
                "name": element.name,
                "center_coordinates": {
                    "x": element.coordinates.x,
                    "y": element.coordinates.y
                },
                "bounding_box": {
                    "x1": element.bounding_box.x1,
                    "y1": element.bounding_box.y1,
                    "x2": element.bounding_box.x2,
                    "y2": element.bounding_box.y2
                },
                "class_name": element.class_name,
                "clickable": element.clickable,
                "focusable": element.focusable
            })

        return {
            "success": True,
            "message": f"Found {len(elements)} interactive UI elements",
            "device_id": device_id or "default",
            "elements": elements_info,
            "count": len(elements)
        }

    except ConnectionError as e:
        return {
            "success": False,
            "error": f"Device connection failed: {e}",
            "elements": [],
            "count": 0
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get UI elements: {e}",
            "elements": [],
            "count": 0
        }


@mcp.tool()
async def get_device_dimensions(device_id: str = None) -> dict:
    """Get the dimensions of the Android device/emulator screen."""
    try:
        # Get device dimensions using adb
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['shell', 'wm', 'size'])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()

        width, height = None, None
        if 'Physical size:' in output:
            size_part = output.split('Physical size:')[1].strip()
            width, height = map(int, size_part.split('x'))

        return {
            "success": True,
            "device_id": device_id or "default",
            "width": width,
            "height": height,
            "dimensions": f"{width}x{height}" if width and height else None
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to get device dimensions: {e}",
            "device_id": device_id or "default"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "device_id": device_id or "default"
        }


@mcp.tool()
async def press_back(device_id: str = None) -> dict:
    """Press the hardware back button on the Android device/emulator."""
    try:
        # Build adb command for back button press
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['shell', 'input', 'keyevent', 'KEYCODE_BACK'])

        # Execute back button press command
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {
            "success": True,
            "message": "Successfully pressed hardware back button",
            "action_type": "back_press",
            "device_id": device_id or "default"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to press back button: {e}",
            "stderr": e.stderr if e.stderr else "",
            "action_type": "back_press"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "action_type": "back_press"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "action_type": "back_press"
        }


@mcp.tool()
async def swipe(direction: str = None, x1: int = None, y1: int = None, x2: int = None, y2: int = None,
               device_id: str = None, distance: int = None, duration: int = 300) -> dict:
    """Swipe horizontally or vertically on the Android screen.

    Args:
        direction: 'left', 'right', 'up', 'down' for directional swipes
        x1, y1, x2, y2: Exact coordinates for custom swipes
        device_id: Optional device ID to target specific device/emulator
        distance: Distance of swipe in pixels (default: 50% of screen dimension)
        duration: Duration of swipe in milliseconds (default: 300ms)
    """
    try:
        # Validate input parameters
        if direction and (x1 is not None or y1 is not None or x2 is not None or y2 is not None):
            return {
                "success": False,
                "error": "Please provide either direction OR coordinates, not both"
            }

        if not direction and not all(coord is not None for coord in [x1, y1, x2, y2]):
            return {
                "success": False,
                "error": "Please provide either a direction ('left', 'right', 'up', 'down') or exact coordinates (x1, y1, x2, y2)"
            }

        if direction:
            # Get device dimensions for direction-based swipes
            dimensions = await get_device_dimensions(device_id)
            if not dimensions["success"]:
                return {
                    "success": False,
                    "error": f"Failed to get device dimensions: {dimensions['error']}"
                }

            screen_width = dimensions["width"]
            screen_height = dimensions["height"]

            if not screen_width or not screen_height:
                return {
                    "success": False,
                    "error": "Could not determine screen dimensions"
                }

            # Default distance is 50% of relevant screen dimension
            if distance is None:
                distance = min(screen_width, screen_height) // 2

            # Calculate swipe coordinates based on direction
            center_x = screen_width // 2
            center_y = screen_height // 2

            direction = direction.lower()
            if direction == 'left':
                x1, y1 = center_x + distance // 2, center_y
                x2, y2 = center_x - distance // 2, center_y
            elif direction == 'right':
                x1, y1 = center_x - distance // 2, center_y
                x2, y2 = center_x + distance // 2, center_y
            elif direction == 'up':
                x1, y1 = center_x, center_y + distance // 2
                x2, y2 = center_x, center_y - distance // 2
            elif direction == 'down':
                x1, y1 = center_x, center_y - distance // 2
                x2, y2 = center_x, center_y + distance // 2
            else:
                return {
                    "success": False,
                    "error": f'Invalid direction: {direction}. Use "left", "right", "up", or "down"'
                }

        # Validate coordinates
        if any(coord < 0 for coord in [x1, y1, x2, y2]):
            return {
                "success": False,
                "error": "All coordinates must be positive integers",
                "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
            }

        # Build adb swipe command
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['shell', 'input', 'swipe', str(x1), str(y1), str(x2), str(y2), str(duration)])

        # Execute swipe command
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Prepare response message
        if direction:
            message = f"Successfully swiped {direction} from ({x1}, {y1}) to ({x2}, {y2}) in {duration}ms"
            action_type = f"directional_swipe_{direction}"
        else:
            message = f"Successfully swiped from ({x1}, {y1}) to ({x2}, {y2}) in {duration}ms"
            action_type = "coordinate_swipe"

        return {
            "success": True,
            "message": message,
            "coordinates": {
                "start": {"x": x1, "y": y1},
                "end": {"x": x2, "y": y2}
            },
            "direction": direction if direction else None,
            "distance": distance if direction else None,
            "duration": duration,
            "action_type": action_type,
            "device_id": device_id or "default"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to execute swipe: {e}",
            "stderr": e.stderr if e.stderr else "",
            "action_type": "swipe"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "action_type": "swipe"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "action_type": "swipe"
        }


@mcp.tool()
async def type_text(text: str, device_id: str = None, clear_first: bool = False) -> dict:
    """Type text into the currently focused input field on the Android device/emulator.

    Args:
        text: The text to type into the input field
        device_id: Optional device ID to target specific device/emulator
        clear_first: If True, clears existing text before typing new text
    """
    try:
        if not text:
            return {
                "success": False,
                "error": "Text parameter cannot be empty",
                "text": text
            }

        # Get device connection for uiautomator2
        device = get_device_connection(device_id)

        # Enable fast input IME for reliable text input
        device.set_fastinput_ime(enable=True)

        # Use uiautomator2's send_keys method which is much more reliable
        device.send_keys(text=text, clear=clear_first)

        return {
            "success": True,
            "message": f"Successfully typed text into input field",
            "text": text,
            "cleared_first": clear_first,
            "action_type": "type_text",
            "device_id": device_id or "default"
        }

    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to type text: {e}",
            "stderr": e.stderr if e.stderr else "",
            "text": text,
            "action_type": "type_text"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "text": text,
            "action_type": "type_text"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "text": text,
            "action_type": "type_text"
        }


@mcp.tool()
async def scroll_element(element, direction: str, distance: int = 200, duration: int = 300, device_id: str = None) -> dict:
    """Scroll a specific UI element in the given direction for a specified distance.

    Args:
        element: Either an integer (element index from annotated screenshot) or string (element name)
        direction: Direction to scroll - 'up', 'down', 'left', 'right'
        distance: Distance to scroll in pixels (default: 200)
        duration: Duration of scroll gesture in milliseconds (default: 300)
        device_id: Optional device ID to target specific device/emulator
    """
    try:
        # Validate direction parameter
        direction = direction.lower()
        if direction not in ['up', 'down', 'left', 'right']:
            return {
                "success": False,
                "error": f'Invalid direction: {direction}. Use "up", "down", "left", or "right"',
                "element": element
            }

        # Validate distance parameter
        if distance <= 0:
            return {
                "success": False,
                "error": "Distance must be a positive integer",
                "element": element,
                "distance": distance
            }

        # Get UI elements
        elements = get_ui_elements(device_id)

        if not elements:
            return {
                "success": False,
                "error": "No UI elements found on screen",
                "element": element
            }

        # Find target element by index or name
        target_element = None
        if isinstance(element, int):
            # Find by index
            if 0 <= element < len(elements):
                target_element = elements[element]
            else:
                return {
                    "success": False,
                    "error": f"Element index {element} is out of range (0-{len(elements)-1})",
                    "element": element,
                    "available_count": len(elements)
                }
        else:
            # Find by name
            element_str = str(element)
            for elem in elements:
                if elem.name == element_str:
                    target_element = elem
                    break

            if not target_element:
                return {
                    "success": False,
                    "error": f"Element with name '{element_str}' not found",
                    "element": element,
                    "available_elements": [elem.name for elem in elements[:10]]  # Show first 10 for reference
                }

        # Check if element is likely scrollable
        scrollable_classes = [
            "android.widget.ScrollView",
            "android.widget.HorizontalScrollView",
            "android.support.v7.widget.RecyclerView",
            "androidx.recyclerview.widget.RecyclerView",
            "android.widget.ListView",
            "android.widget.GridView",
            "androidx.viewpager.widget.ViewPager",
            "androidx.viewpager2.widget.ViewPager2"
        ]

        is_scrollable = target_element.class_name in scrollable_classes

        # Get element bounds
        bbox = target_element.bounding_box
        element_width = bbox.x2 - bbox.x1
        element_height = bbox.y2 - bbox.y1

        # Calculate center point of the element
        center_x = bbox.x1 + element_width // 2
        center_y = bbox.y1 + element_height // 2

        # Calculate scroll coordinates within element boundaries with margins
        margin = 20  # Keep scroll gesture away from element edges

        if direction == 'up':
            # Scroll up: start lower in element, end higher
            start_y = min(center_y + distance // 2, bbox.y2 - margin)
            end_y = max(center_y - distance // 2, bbox.y1 + margin)
            start_x = end_x = center_x
        elif direction == 'down':
            # Scroll down: start higher in element, end lower
            start_y = max(center_y - distance // 2, bbox.y1 + margin)
            end_y = min(center_y + distance // 2, bbox.y2 - margin)
            start_x = end_x = center_x
        elif direction == 'left':
            # Scroll left: start right in element, end left
            start_x = min(center_x + distance // 2, bbox.x2 - margin)
            end_x = max(center_x - distance // 2, bbox.x1 + margin)
            start_y = end_y = center_y
        else:  # right
            # Scroll right: start left in element, end right
            start_x = max(center_x - distance // 2, bbox.x1 + margin)
            end_x = min(center_x + distance // 2, bbox.x2 - margin)
            start_y = end_y = center_y

        # Ensure coordinates are within element bounds
        start_x = max(bbox.x1 + margin, min(start_x, bbox.x2 - margin))
        end_x = max(bbox.x1 + margin, min(end_x, bbox.x2 - margin))
        start_y = max(bbox.y1 + margin, min(start_y, bbox.y2 - margin))
        end_y = max(bbox.y1 + margin, min(end_y, bbox.y2 - margin))

        # Build adb swipe command to perform scroll gesture
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['shell', 'input', 'swipe', str(start_x), str(start_y), str(end_x), str(end_y), str(duration)])

        # Execute scroll command
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        return {
            "success": True,
            "message": f"Successfully scrolled element '{target_element.name}' {direction} for {distance} pixels in {duration}ms",
            "element": {
                "name": target_element.name,
                "class_name": target_element.class_name,
                "bounding_box": {
                    "x1": bbox.x1, "y1": bbox.y1,
                    "x2": bbox.x2, "y2": bbox.y2
                }
            },
            "scroll_coordinates": {
                "start": {"x": start_x, "y": start_y},
                "end": {"x": end_x, "y": end_y}
            },
            "direction": direction,
            "distance": distance,
            "duration": duration,
            "is_scrollable_element": is_scrollable,
            "action_type": f"element_scroll_{direction}",
            "device_id": device_id or "default"
        }

    except ConnectionError as e:
        return {
            "success": False,
            "error": f"Device connection failed: {e}",
            "element": element,
            "action_type": "element_scroll"
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Failed to execute scroll: {e}",
            "stderr": e.stderr if e.stderr else "",
            "element": element,
            "action_type": "element_scroll"
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": "ADB not found. Please ensure Android SDK is installed and adb is in PATH.",
            "element": element,
            "action_type": "element_scroll"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "element": element,
            "action_type": "element_scroll"
        }


@mcp.tool()
async def record_video(device_id: str = None, filename: str = None, resolution: str = None, bitrate: str = "8M") -> dict:
    """Start recording a video using scrcpy. The video will be saved to the videos directory."""
    try:
        # Use android-puppeteer/videos directory for video recordings
        current_dir = os.path.dirname(os.path.abspath(__file__))
        videos_dir = os.path.join(current_dir, "videos")
        os.makedirs(videos_dir, exist_ok=True)

        # Generate filename if not provided
        if filename:
            # Ensure it has .mp4 extension
            if not filename.endswith('.mp4'):
                filename = f"{filename}.mp4"
        else:
            # Use timestamp if no filename provided
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.mp4"

        filepath = os.path.join(videos_dir, filename)

        # Create recording key for tracking
        recording_key = device_id or "default"

        # Check if already recording for this device
        if recording_key in active_recordings:
            return {
                "success": False,
                "error": f"Already recording for device {recording_key}. Stop the current recording first.",
                "device_id": device_id or "default"
            }

        # Build scrcpy command for recording
        cmd = ['scrcpy']

        # Add device selection if specified
        if device_id:
            cmd.extend(['-s', device_id])

        # Add recording parameters
        cmd.extend(['--record', filepath])

        # Add video quality parameters
        cmd.extend(['--video-bit-rate', bitrate])

        if resolution:
            cmd.extend(['--max-size', resolution])

        # Add minimal parameters for recording
        cmd.extend([
            '--no-playback'  # Don't show the device screen (updated flag for scrcpy v3.2+)
        ])

        # Start the recording process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group for proper termination
        )

        # Give the process a moment to start and check if it's still running
        import time
        time.sleep(1)

        # Check if process started successfully
        if process.poll() is not None:
            # Process terminated immediately, capture error output
            stderr_output = process.stderr.read().decode() if process.stderr else ""
            stdout_output = process.stdout.read().decode() if process.stdout else ""
            return {
                "success": False,
                "error": f"scrcpy process terminated immediately. stderr: {stderr_output}, stdout: {stdout_output}",
                "filepath": None,
                "command": ' '.join(cmd)
            }

        # Store the process for later termination
        active_recordings[recording_key] = {
            "process": process,
            "filepath": filepath,
            "filename": filename,
            "start_time": datetime.now(),
            "device_id": device_id or "default"
        }

        return {
            "success": True,
            "message": f"Video recording started successfully",
            "filepath": filepath,
            "filename": filename,
            "device_id": device_id or "default",
            "recording_key": recording_key,
            "bitrate": bitrate,
            "resolution": resolution,
            "process_id": process.pid
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "scrcpy not found. Please ensure scrcpy is installed and in PATH.",
            "filepath": None
        }
    except PermissionError:
        return {
            "success": False,
            "error": f"Permission denied: Cannot create directory or write to {videos_dir}",
            "filepath": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error starting recording: {e}",
            "filepath": None
        }


@mcp.tool()
async def stop_video(device_id: str = None) -> dict:
    """Stop the active video recording for the specified device."""
    try:
        recording_key = device_id or "default"

        if recording_key not in active_recordings:
            return {
                "success": False,
                "error": f"No active recording found for device {recording_key}",
                "device_id": device_id or "default"
            }

        recording_info = active_recordings[recording_key]
        process = recording_info["process"]
        filepath = recording_info["filepath"]
        filename = recording_info["filename"]
        start_time = recording_info["start_time"]

        # Check if process is still running
        if process.poll() is not None:
            # Process already terminated
            del active_recordings[recording_key]
            return {
                "success": False,
                "error": "Recording process has already terminated",
                "filepath": filepath,
                "filename": filename
            }

        # Gracefully terminate the scrcpy process
        try:
            # Send SIGTERM to the process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)

            # Wait for the process to terminate (with timeout)
            process.wait(timeout=10)

        except subprocess.TimeoutExpired:
            # If it doesn't terminate gracefully, force kill
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            # Process already terminated
            pass

        # Remove from active recordings
        del active_recordings[recording_key]

        # Calculate recording duration
        end_time = datetime.now()
        duration = end_time - start_time
        duration_seconds = duration.total_seconds()

        # Check if file exists and get size
        file_size = None
        file_exists = os.path.exists(filepath)
        if file_exists:
            file_size = os.path.getsize(filepath)

        return {
            "success": True,
            "message": f"Video recording stopped successfully",
            "filepath": filepath if file_exists else None,
            "filename": filename,
            "device_id": device_id or "default",
            "duration_seconds": duration_seconds,
            "file_size_bytes": file_size,
            "file_exists": file_exists
        }

    except Exception as e:
        # Clean up the recording entry even if there was an error
        recording_key = device_id or "default"
        if recording_key in active_recordings:
            del active_recordings[recording_key]

        return {
            "success": False,
            "error": f"Error stopping recording: {e}",
            "device_id": device_id or "default"
        }


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')