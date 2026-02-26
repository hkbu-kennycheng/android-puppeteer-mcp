mcp-name: io.github.pedro-rivas/android-puppeteer-mcp

<div align="center">

 <h1>Android Puppeteer</h1>

 <a href="https://https://github.com/pedro-rivas/android-puppeteer-mcp/blob/main/LICENSE">
   <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
 </a>
 <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
 <img src="https://img.shields.io/badge/platform-Android%2010+-blue" alt="Platform">
 <img src="https://img.shields.io/badge/mcp-server-purple" alt="MCP Server">

</div>

<br>

**Android Puppeteer** is a lightweight, visual-first MCP (Model Context Protocol) server that enables AI agents to interact with Android devices through intelligent UI element detection and automated interactions. Built on uiautomator2, it provides comprehensive Android automation capabilities including visual element detection, touch interactions, text input, and video recording.

🎥 **[Watch the demo in action](https://www.linkedin.com/feed/update/urn:li:activity:7373122958866825216/)**

## Features

- **Visual Element Detection**
  Automatically detects and annotates interactive UI elements with numbered overlays for precise targeting.

- **Comprehensive Touch Interactions**
  Support for tap, long press, swipe, scroll, and drag gestures with coordinate-based precision.

- **Multi-Device Support**
  Connect to multiple Android devices or emulators simultaneously with device-specific targeting.

- **Video Recording Integration**
  Built-in screen recording capabilities using scrcpy for documentation and testing workflows.

- **Real-Time UI Analysis**
  Live UI hierarchy parsing and element information extraction for dynamic interaction strategies.

- **MCP Protocol Integration**
  Seamless integration with Claude Desktop and other MCP-compatible AI platforms.

### Supported Operating Systems

- Android 10+
- Windows, macOS, Linux (host systems)

## Installation

### Prerequisites

- Python 3.10+
- uiautomator2
- Android 10+ (Emulator or Physical Device)
- ADB (Android Debug Bridge)
- scrcpy (for video recording features)

### Getting Started

1. **Clone the repository**

```shell
uvx --from git+https://github.com/pedro-rivas/android-puppeteer-mcp.git android-puppeteer-mcp
```

2. **Setup Android device**

```shell
# Enable USB debugging on your Android device
# For emulator, ensure it's running
adb devices  # Verify device connection
```

4. **Connect to the MCP server**

1. Locate your Claude Desktop configuration file:

   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add the following JSON to your Claude Desktop config:

   ```json
   {
     "mcpServers": {
       "android-puppeteer": {
         "command": "uvx",
         "args": [
            "--from",
            "git+https://github.com/pedro-rivas/android-puppeteer-mcp.git",
            "android-puppeteer-mcp"
         ]
       }
     }
   }
   ```

3. **Restart Claude Desktop**

Restart your Claude Desktop. You should see "android-puppeteer" listed as an available integration.

---

## Available Tools

Android Puppeteer provides the following tools for comprehensive Android device interaction:

### Device Management
- **`list_emulators`**: List all available Android emulators and devices with their status and dimensions
- **`get_device_dimensions`**: Get the screen dimensions of a specific Android device
- **`get_ui_elements_info`**: Get detailed information about all interactive UI elements on screen

### Visual Interaction
- **`take_screenshot`**: Capture annotated screenshots with numbered UI element overlays
- **`press`**: Tap on specific coordinates with optional long press duration
- **`long_press`**: Perform long press gestures on specific coordinates

### Navigation & Input
- **`press_back`**: Press the hardware back button
- **`swipe`**: Perform directional or custom coordinate swipes
- **`type_text`**: Type text into focused input fields with optional text clearing
- **`scroll_element`**: Scroll specific UI elements in any direction

### Recording & Documentation
- **`record_video`**: Start screen recording with customizable quality settings
- **`stop_video`**: Stop active screen recordings and save to local storage

## Usage Examples

### Basic Device Interaction

```python
# Take an annotated screenshot
screenshot = await take_screenshot()

# Tap on a specific element (element 5 from screenshot)
await press(x=500, y=300)

# Type text into an input field
await type_text("Hello, Android!")

# Swipe to scroll down
await swipe(direction="down")
```

### Multi-Device Automation

```python
# List available devices
devices = await list_emulators()

# Target specific device
await take_screenshot(device_id="emulator-5554")
await press(x=200, y=400, device_id="emulator-5554")
```

### Video Recording Workflow

```python
# Start recording
await record_video(filename="test_session.mp4")

# Perform automation steps
await press(x=300, y=500)
await type_text("Automated test input")

# Stop recording
await stop_video()
```

## Project Structure

```
android-puppeteer/
    puppeteer.py          # Main MCP server implementation
    main.py              # Entry point
    pyproject.toml       # Project configuration
    ss/                  # Screenshots directory
    videos/              # Video recordings directory
    README.md           # This file
```

## Important Notes

- **Device Permissions**: Ensure USB debugging is enabled on target Android devices
- **Network Access**: Some features require network connectivity for device communication
- **Storage**: Screenshot and video files are saved locally in `ss/` and `videos/` directories
- **Performance**: Response times depend on device performance and network latency

## Troubleshooting

### Common Issues

1. **Device not found**: Verify ADB connection with `adb devices`
2. **Permission denied**: Check USB debugging and device authorization
3. **Screenshot failures**: Ensure device screen is unlocked and accessible
4. **Video recording issues**: Verify scrcpy installation and device compatibility

### Debug Mode

Run the server directly for debugging:
```shell
uv run puppeteer.py
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure code quality
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Related Projects

- [Android MCP](https://github.com/CursorTouch/Android-MCP) - Alternative Android automation MCP server
- [uiautomator2](https://github.com/openatx/uiautomator2) - Core Android automation library
- [MCP Protocol](https://modelcontextprotocol.io/) - Model Context Protocol specification

---

**Star this repo if you find it useful!** 