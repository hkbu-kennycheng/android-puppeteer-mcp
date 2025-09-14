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

# Initialize FastMCP server
mcp = FastMCP("android-puppeteer", "Puppeteer for Android")


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


def annotated_screenshot(device_id: str = None, scale: float = 0.7) -> tuple[Image.Image, list[ElementNode]]:
    """Take screenshot and annotate with UI elements"""
    try:
        # Get screenshot using adb (like the original function)
        cmd = ['adb']
        if device_id:
            cmd.extend(['-s', device_id])
        cmd.extend(['exec-out', 'screencap', '-p'])

        result = subprocess.run(cmd, capture_output=True, check=True)
        screenshot = Image.open(io.BytesIO(result.stdout))

        # Scale screenshot if needed
        if scale != 1.0:
            new_size = (int(screenshot.width * scale), int(screenshot.height * scale))
            screenshot = screenshot.resize(new_size, Image.Resampling.LANCZOS)

        # Get UI elements
        nodes = get_ui_elements(device_id)

        # Add padding
        padding = 15
        width = screenshot.width + (2 * padding)
        height = screenshot.height + (2 * padding)
        padded_screenshot = Image.new("RGB", (width, height), color=(255, 255, 255))
        padded_screenshot.paste(screenshot, (padding, padding))

        draw = ImageDraw.Draw(padded_screenshot)
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

            # Scale and pad the bounding box
            adjusted_box = (
                int(bounding_box.x1 * scale) + padding,
                int(bounding_box.y1 * scale) + padding,
                int(bounding_box.x2 * scale) + padding,
                int(bounding_box.y2 * scale) + padding
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
            label_x2 = min(label_x1 + label_width + 4, width - 1)
            label_y2 = label_y1 + label_height + 4

            # Draw label background and text
            draw.rectangle([(label_x1, label_y1), (label_x2, label_y2)], fill=color)
            draw.text((label_x1 + 2, label_y1 + 2), label_text, fill=(255, 255, 255), font=font)

        # Draw annotations sequentially
        for i, node in enumerate(nodes):
            draw_annotation(i, node)

        return padded_screenshot, nodes

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
async def take_screenshot(device_id: str = None, name: str = None, annotate_elements: bool = False) -> dict:
    """Take a screenshot for the specified device/emulator. If no device_id is provided, uses the default device.
    Set annotate_elements=True to overlay UI element bounding boxes and labels."""
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

        # Execute screenshot command or use annotated version
        if annotate_elements:
            try:
                # Use annotated screenshot with UI elements
                annotated_img, ui_elements = annotated_screenshot(device_id, scale=1.0)

                # Save only the annotated image
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


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')