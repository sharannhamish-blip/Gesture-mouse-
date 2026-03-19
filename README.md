🖐 Iron-Hand — Webcam Gesture Mouse
Control your entire computer with hand gestures. No hardware, no gloves, just your webcam.
Built with Python, OpenCV, and MediaPipe. Works on Windows, macOS, and Linux.

✨ What it does
Iron-Hand turns your webcam into a gesture controller. Your right hand moves the cursor and clicks. Your left hand controls system-level actions like volume, media scrubbing, task view, and minimize/restore — without touching the keyboard or mouse.

🎥 Demo

Record a short screen capture and drop a GIF here — this is the #1 thing that gets attention on GitHub.


🖐 Gesture Reference
Right Hand — Cursor Control
GestureActionAny poseMove cursor (always active)Pinch thumb + index (quick)Left clickPinch thumb + index (2× quick)Double clickPinch thumb + index (hold)DragThumb + pinky closeRight clickIndex + middle tips touch → move up/downScroll

Tip: The cursor tracks your index knuckle (MCP), not the fingertip — so pinching doesn't pull the cursor down.


Left Hand — System Controls
GestureActionThumb + middle touchTask View (Win+Tab)Thumb + index quick touchMinimize all windowsThumb + index holdRestore all windowsIndex + middle + ring up → swipe up/downVolume up / downIndex finger only → move left/rightScrub video (← →)Peace sign ✌️ (index + middle)Mute toggle

Dual Hand
GestureAction👏 Clap (bring both wrists together)Minimize all windowsBoth hands open → spread apartZoom in (Ctrl++)Both hands open → bring togetherZoom out (Ctrl+−)

⚙️ How it works

MediaPipe Hands detects 21 hand landmarks per hand at up to 60fps
Index MCP (knuckle) is used as the cursor anchor — it doesn't move when you pinch, eliminating click drift
Hysteresis thresholds on pinch detection (enter at 18px, exit at 38px) prevent click/drag flickering
Gesture debounce buffer (4 frames) prevents move↔idle flicker from landmark noise
Pointer acceleration makes slow movements precise and fast movements reach screen edges easily
Intent guard requires the hand to settle inside the active zone for 0.3s before gestures fire — prevents accidental triggers when raising your hand


🚀 Install & Run
Requirements

Python 3.8+
Webcam (any USB or built-in)
Windows, macOS, or Linux

Install dependencies
bashpip install -r requirements.txt
Run
bashpython iron_hand.py
Press L to toggle the gesture legend overlay.
Press ESC to quit.

📦 requirements.txt
opencv-python
mediapipe
pyautogui
numpy

🔧 Tuning
All sensitivity values are constants at the top of iron_hand.py:
ConstantDefaultWhat it controlsPINCH_THRESH18pxHow close fingers must be to register a pinchPINCH_RELEASE38pxHow far apart to release a pinchCLICK_TIME0.22sPinch shorter than this = click, longer = dragACCEL_POWER1.6Cursor acceleration (1.0 = linear, higher = more acceleration)INTENT_SETTLE0.30sTime hand must be still before gestures activateSCROLL_HOLD_TIME0.25sHow long to hold index+middle together before scroll activatesMARGIN30pxBorder of the active zone in the camera frame

🖥️ Platform Notes
OSVolume controlMinimize/RestoreTask ViewWindowsvolumeup / volumedown keysWin+DWin+TabmacOSShift+Option+F11/F12Cmd+Option+MCtrl+UpLinuxamixer pulseSuper+DSuper+W

📁 Project Structure
iron-hand/
├── iron_hand.py        # Main script
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── .gitignore

🗺️ Roadmap

 Calibration mode — auto-tune pinch threshold to your hand size
 Config file — save tuning values without editing source
 Multi-monitor support
 Gesture recorder — create custom macros
 Virtual keyboard trigger


📄 License
MIT License — free to use, modify, and distribute.

🙏 Built with

MediaPipe — hand landmark detection
OpenCV — camera capture and frame processing
PyAutoGUI — mouse and keyboard control
