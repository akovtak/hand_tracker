created by ChatGPT-5.1, because i'm too lazy






# Hand Tracker README

## Overview

This project provides a **real-time hand tracking and gesture analysis tool** using MediaPipe and OpenCV, with OSC output for integration with environments like SuperCollider, Max/MSP, TouchDesigner, or any OSC-capable software.

It supports:

* Tracking **both hands independently**
* Calculating distances between hand landmarks
* Recognizing squeeze/gesture values (0–1 normalized)
* Sending OSC messages with multiple metrics
* Optional manual calibration logic

---

## Features

* **MediaPipe Hands** (21 landmarks per hand)
* Custom metrics:

  * `tip_to_mcp`
  * `tip_to_tip`
  * `avg_tip_to_wrist`
  * `mcp_to_mcp`
  * `avg_mcp_to_wrist`
* Automatic scaling of gesture values to **0–1** range
* Separate OSC messages for **left** and **right** hands
* On-screen visualization with text overlays (moved to avoid overlap)
* Stable logic for two-hand tracking and key interactions

---

## Requirements

Your system should have the following dependencies installed:

### Python-side

* **Python 3.9–3.12**
* **uv** (for managing Python packages)
* **OpenCV**
* **MediaPipe**
* **python-osc**
* **NumPy**

Install using uv:

```bash
uv pip install opencv-python mediapipe python-osc numpy
```

### External tools

* **SuperCollider** (for receiving OSC messages)

Install dependencies:

```bash
pip install opencv-python mediapipe python-osc numpy
```

---

## How It Works

1. MediaPipe detects hands and provides 3D landmark coordinates.
2. The script computes distances (norms) between selected landmark pairs.
3. Distances are normalized between 0–1 using either:

   * Fixed min/max values, or
   * Calibrated values
4. Values are sent through OSC as floats.
5. The camera view displays debug info for each hand.

---

## OSC Outputs

Each hand sends a dictionary of values:

```
/hand/left  tip_to_mcp  tip_to_tip  avg_tip_to_wrist  mcp_to_mcp  avg_mcp_to_wrist
/hand/right tip_to_mcp  tip_to_tip  avg_tip_to_wrist  mcp_to_mcp  avg_mcp_to_wrist
```

Each value is a float between **0 and 1**.

---

## Keyboard Controls (optional)

| Key | Action                |
| --- | --------------------- |
| `q` | Quit application      |
| `c` | Clear calibration     |
| `1` | Calibrate OPEN hand   |
| `2` | Calibrate CLOSED hand |

Calibration sets min/max ranges for normalization.

---

## Project Structure

```
hand_tracker/
├── hand_tracker.py
├── README.md (this file)
└── requirements.txt
```

---

## Typical SuperCollider Usage Example

```supercollider
OSCdef.new(\handL, { |msg| ~leftValue = msg[1]; }, '/hand/left');
OSCdef.new(\handR, { |msg| ~rightValue = msg[1]; }, '/hand/right');
```

---

## Troubleshooting

### Camera is detected but no OSC output

* Check that the OSC IP and port match your target application.
* Firewalls may block UDP on some systems.

### Values are stuck (always 1 or always 0)

* Recalibrate using `1` and `2`.
* Ensure your hand is fully inside the frame.

### Lag or low FPS

* Reduce camera resolution.
* Disable drawing if not needed.
