"""
Iron-Hand Controller v3
========================
RIGHT HAND — cursor control (single hand gestures):
  ☝  Index only              → Move cursor
  👌  Pinch quick             → Left click
  👌  Pinch hold              → Drag
  🤙  Thumb+pinky close       → Right click
  ✌  Index+middle (rest down) → Scroll up/down
  🤟  Index+Pinky             → Alt+Tab (hold to keep cycling)
  🤘  Mid+Ring+Pinky          → Win+Tab / Task View
 
LEFT HAND — independent controls (right hand free for cursor):
  🤟  Index+Middle+Ring up     → Volume swipe
        swipe up                → Volume Up
        swipe down              → Volume Down
  ☝  Index only (point)       → Video scrubber
        move left               → ← arrow (rewind)
        move right              → → arrow (fast-forward)
  ✌  Peace sign (index+middle) → Mute toggle (instant)
 
DUAL HAND — requires BOTH hands visible simultaneously:
  Both fists (✊✊)            → Minimize all windows   [hold 0.6s]
  Both open (🖐🖐)            → Restore all windows    [hold 0.6s]
  Left fist + Right open      → Minimize all           [hold 0.6s]
  Left open + Right fist      → Restore all            [hold 0.6s]
  Both open, move apart        → Zoom In  (Ctrl++)
  Both open, move together     → Zoom Out (Ctrl+-)
 
The left hand acts as a "shift key" — it must be present to allow
minimize/restore. Single-hand fist/open will never minimize.
 
Press L to toggle legend.  ESC to quit.
 
INSTALL:
  pip install opencv-python mediapipe pyautogui numpy
"""
 
import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import math
import time
import collections
import platform
 
pyautogui.FAILSAFE = False
pyautogui.PAUSE    = 0
 
SCREEN_W, SCREEN_H = pyautogui.size()
CAM_W, CAM_H       = 640, 480
MARGIN             = 30     # reduced from 70 — nearly full frame is usable now
 
# ── Tuning ────────────────────────────────────────────────────────────────────
CURSOR_HISTORY   = 4       # slightly smaller = more responsive
PINCH_THRESH     = 18     # px — enter pinch (fingers must actually touch)
PINCH_RELEASE    = 38     # px — exit pinch (open wider to release)
CLICK_TIME       = 0.22     # pinch shorter than this = click, longer = drag
CLICK_COOLDOWN   = 0.45
SCROLL_SCALE     = 0.22
SCROLL_DEADZONE  = 8
 
# Pointer acceleration — makes slow=precise, fast=reaches edges
# 1.0 = linear. 1.6 = acceleration curve (recommended)
ACCEL_POWER      = 1.6
 
# Intent guard — right hand must be inside box and still for this long
# before ANY gesture fires. Prevents misfires when raising hand into frame.
INTENT_SETTLE    = 0.30     # seconds
 
# Dual-hand gestures need a firm hold to avoid accidents
DUAL_HOLD        = 0.6      # seconds both hands must hold the gesture
 
# Left-hand volume swipe (index + middle + ring up, move hand up/down)
VOL_SWIPE_DEADZONE = 10     # px vertical movement to ignore (kills tremor)
VOL_REPEAT_DELAY   = 0.15   # seconds between volume key repeats while swiping
 
# Left-hand video scrubber
SCRUB_DEADZONE     = 20     # px horizontal movement before sending arrow key
SCRUB_PX_PER_KEY   = 18     # px of additional movement per extra arrow keypress
SCRUB_KEY_DELAY    = 0.08   # seconds between repeated arrow keys while scrubbing
 
# Left-hand mute (peace sign)
MUTE_COOLDOWN      = 1.0    # seconds between mute toggles

# Clap gesture — both palms come close together → minimize all
CLAP_THRESH        = 120    # px — wrist-to-wrist distance to count as clapped
CLAP_COOLDOWN      = 1.2    # sec — prevent rapid re-fire

# Snap gesture (task view) — thumb+middle quick touch-release on right hand
SNAP_COOLDOWN      = 0.8    # sec — prevent task view repeated fires

# Left hand pinch thresholds (distance-based, same idea as right hand)
LEFT_PINCH_THRESH  = 35     # px — thumb+finger distance to count as touching

# Scroll — index+middle must HOLD touching for this long before scroll activates
# This prevents accidental scroll when fingers briefly pass each other
SCROLL_TOUCH_THRESH = 28    # px — index-middle tip distance
SCROLL_HOLD_TIME    = 0.25  # sec — must hold touch before scroll mode locks in

# Dual-hand zoom (both open, hands apart/together)
ZOOM_DEADZONE      = 15     # px change in palm distance to ignore
ZOOM_PX_PER_STEP   = 25     # px distance change per Ctrl+/- press
ZOOM_KEY_DELAY     = 0.12   # seconds between zoom keypresses
 
OS = platform.system()
 
# ── OS actions ────────────────────────────────────────────────────────────────
def minimize_all():
    if OS == "Windows":   pyautogui.hotkey("win", "d")
    elif OS == "Darwin":  pyautogui.hotkey("command", "option", "m")
    else:                 pyautogui.hotkey("super", "d")
 
def restore_all():
    minimize_all()   # Win+D / Super+D are toggles
 
def task_view():
    if OS == "Windows":   pyautogui.hotkey("win", "tab")
    elif OS == "Darwin":  pyautogui.hotkey("ctrl", "up")
    else:                 pyautogui.hotkey("super", "w")
 
def volume_up():
    if OS == "Windows":   pyautogui.press("volumeup")
    elif OS == "Darwin":  pyautogui.hotkey("shift", "option", "f12")   # fine step
    else:                 import subprocess; subprocess.call(["amixer","-D","pulse","sset","Master","5%+"])
 
def volume_down():
    if OS == "Windows":   pyautogui.press("volumedown")
    elif OS == "Darwin":  pyautogui.hotkey("shift", "option", "f11")
    else:                 import subprocess; subprocess.call(["amixer","-D","pulse","sset","Master","5%-"])
 
def mute_toggle():
    if OS == "Windows":   pyautogui.press("volumemute")
    elif OS == "Darwin":  pyautogui.hotkey("shift", "option", "f10")
    else:                 import subprocess; subprocess.call(["amixer","-D","pulse","sset","Master","toggle"])
 
# ── MediaPipe — 2 hands ───────────────────────────────────────────────────────
mp_hands   = mp.solutions.hands
hands      = mp_hands.Hands(
    max_num_hands            = 2,
    min_detection_confidence = 0.75,
    min_tracking_confidence  = 0.65,
)
draw_utils = mp.solutions.drawing_utils
draw_styl  = mp.solutions.drawing_styles
 
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
cap.set(cv2.CAP_PROP_FPS, 60)
 
# ── State ─────────────────────────────────────────────────────────────────────
cursor_hist   = collections.deque(maxlen=CURSOR_HISTORY)
scroll_anchor = None
dragging      = False
pinch_start   = None
last_click    = 0.0
dbl_click_window   = 0.35
last_click_release = 0.0

# Snap (task view) state
last_snap       = 0.0     # last time task view fired
left_pinch_start = None   # time left thumb+index first touched

# Clap (minimize) state
clap_armed      = False   # True when hands were apart, ready to clap
last_clap       = 0.0     # last time clap fired

# Gesture debounce — committed gesture only changes when GESTURE_CONFIRM_FRAMES
# consecutive raw readings agree. Kills move↔idle flicker from MediaPipe noise.
GESTURE_CONFIRM_FRAMES = 4
gesture_buf       = collections.deque(maxlen=GESTURE_CONFIRM_FRAMES)
committed_gesture = "idle"   # the stable gesture shown and acted on

# Scroll touch-hold state
scroll_touch_start = None  # time index+middle first touched
scroll_locked      = False # True once hold confirmed — stays until fingers separate
 
# Dual-hand one-shot timers
dual_timers = {}   # gesture_key → time first seen
dual_fired  = set()
 
# Intent guard state — right hand must settle before gestures fire
hand_enter_time = None   # when right hand first appeared inside active box
hand_active     = False  # True once INTENT_SETTLE seconds have passed
 
# Left-hand gesture state
vol_last_time    = 0.0          # last volume key sent
vol_anchor_y     = None         # y position when vol swipe gesture started
scrub_anchor_x   = None         # x position when scrub gesture started
scrub_last_time  = 0.0          # last arrow key sent
scrub_remainder  = 0            # sub-threshold px accumulator
last_mute_time   = 0.0          # last mute toggle
zoom_anchor_dist = None         # palm distance when zoom gesture started
zoom_last_time   = 0.0          # last zoom key sent
zoom_remainder   = 0            # sub-threshold px accumulator
 
# ── Helpers ───────────────────────────────────────────────────────────────────
def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])
 
def fingers_up(lm):
    """[thumb, index, middle, ring, pinky] — robust, camera-agnostic thumb."""
    up = []
    wrist_x   = lm[0][0]
    thumb_mcp = lm[2][0]
    thumb_tip = lm[4][0]
    if wrist_x < thumb_mcp:
        up.append(1 if thumb_tip > lm[3][0] else 0)
    else:
        up.append(1 if thumb_tip < lm[3][0] else 0)
    for tip in [8, 12, 16, 20]:
        up.append(1 if lm[tip][1] < lm[tip-2][1] else 0)
    return up
 
def is_fist(fi):
    return sum(fi) == 0
 
def is_open(fi):
    return sum(fi) == 5
 
def accel_move(raw_x, raw_y, cam_w, cam_h):
    """
    Maps index MCP camera position → screen coords with acceleration.
    Slow hand movement = fine precision near centre.
    Fast hand movement = reaches screen edges easily.
    """
    nx = (np.clip(raw_x, MARGIN, cam_w - MARGIN) - MARGIN) / (cam_w - 2*MARGIN)
    ny = (np.clip(raw_y, MARGIN, cam_h - MARGIN) - MARGIN) / (cam_h - 2*MARGIN)
    # Remap to -1..1, apply power curve, remap back to 0..1
    ax = math.copysign(abs(nx * 2 - 1) ** ACCEL_POWER, nx * 2 - 1)
    ay = math.copysign(abs(ny * 2 - 1) ** ACCEL_POWER, ny * 2 - 1)
    sx = (ax + 1) / 2 * SCREEN_W
    sy = (ay + 1) / 2 * SCREEN_H
    return float(np.clip(sx, 0, SCREEN_W)), float(np.clip(sy, 0, SCREEN_H))
 
def inside_box(lm, cam_w, cam_h):
    """True if index MCP (lm[5]) is inside the active zone."""
    x, y = lm[5]
    return MARGIN <= x <= cam_w - MARGIN and MARGIN <= y <= cam_h - MARGIN
 
def dual_one_shot(key, now):
    """Fire exactly once when key gesture held for DUAL_HOLD seconds."""
    if key not in dual_timers:
        dual_timers[key] = now
    if now - dual_timers[key] >= DUAL_HOLD and key not in dual_fired:
        dual_fired.add(key)
        return True
    return False
 
def clear_dual(key):
    dual_timers.pop(key, None)
    dual_fired.discard(key)
 
def identify_hands(result, w, h):
    """
    Returns (right_lm, left_lm) or (None, None).
    MediaPipe labels are from the person's perspective (already flipped).
    right_lm = the dominant/control hand.
    """
    right_lm = None
    left_lm  = None
    if not result.multi_hand_landmarks:
        return None, None
 
    for i, hand_lm in enumerate(result.multi_hand_landmarks):
        lm = [(int(p.x*w), int(p.y*h)) for p in hand_lm.landmark]
        label = "Right"
        if result.multi_handedness:
            try:
                label = result.multi_handedness[i].classification[0].label
            except Exception:
                pass
        if label == "Right":
            right_lm = lm
        else:
            left_lm = lm
    return right_lm, left_lm
 
# ── Display ───────────────────────────────────────────────────────────────────
COLORS = {
    "move"      : (0,   220, 100),
    "lclick"    : (0,   200, 255),
    "dblclick"  : (0,   255, 180),
    "rclick"    : (50,  80,  255),
    "drag"      : (220, 60,  255),
    "scroll"    : (255, 180, 0  ),
    "alt_tab"   : (0,   255, 255),
    "task_view" : (255, 255, 0  ),
    "minimize"  : (255, 80,  30 ),
    "clap"      : (255, 60,  60 ),
    "restore"   : (50,  255, 180),
    "dual_ready": (255, 200, 0  ),
    "vol_up"    : (0,   255, 120),
    "vol_down"  : (255, 80,  80 ),
    "scrub"     : (180, 120, 255),
    "mute"      : (200, 200, 200),
    "zoom_in"   : (0,   220, 255),
    "zoom_out"  : (255, 140, 0  ),
}
 
LABELS = {
    "move"      : "MOVE",
    "lclick"    : "LEFT CLICK",
    "dblclick"  : "DOUBLE CLICK ⚡",
    "rclick"    : "RIGHT CLICK",
    "drag"      : "DRAG",
    "scroll"    : "SCROLL",
    "alt_tab"   : "ALT+TAB",
    "task_view" : "TASK VIEW",
    "minimize"  : "MINIMIZE ALL",
    "restore"   : "RESTORE ALL",
    "dual_ready": "DUAL HAND READY...",
    "vol_up"    : "VOL UP  🔊",
    "vol_down"  : "VOL DOWN 🔇",
    "scrub"     : "SCRUBBING ⏩",
    "mute"      : "MUTE TOGGLED 🔇",
    "zoom_in"   : "ZOOM IN 🔍",
    "zoom_out"  : "ZOOM OUT 🔍",
}
 
LEGEND_RIGHT = [
    ("Index only",        "Move"),
    ("Pinch  (quick)",    "Left Click"),
    ("Pinch  2x quick",   "Double Click"),
    ("Pinch  (hold)",     "Drag"),
    ("Thumb + Pinky",     "Right Click"),
    ("Idx+Mid HOLD+move", "Scroll"),
]
LEGEND_LEFT = [
    ("Thumb+Middle touch", "Task View"),
    ("Thumb+Index quick",  "Minimize All"),
    ("Thumb+Index hold",   "Restore All"),
    ("Idx+Mid+Ring up",    "Volume Swipe up/dn"),
    ("Index point+move",   "Scrub Video L/R"),
    ("Peace sign V",       "Mute Toggle"),
]
LEGEND_DUAL = [
    ("Clap  👏",           "Minimize All"),
    ("Both open +apart",  "Zoom In"),
    ("Both open +close",  "Zoom Out"),
]
 
show_legend = True
fps_time    = time.time()
fps_count   = 0
fps_disp    = 0.0
 
print("[Iron-Hand v3]  Dual-hand minimize/restore active")
print("                L = legend   ESC = quit")
 
# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    ret, img = cap.read()
    if not ret:
        continue
 
    img = cv2.flip(img, 1)
    h, w, _ = img.shape
 
    fps_count += 1
    elapsed = time.time() - fps_time
    if elapsed >= 0.5:
        fps_disp  = fps_count / elapsed
        fps_count = 0
        fps_time  = time.time()
 
    cv2.rectangle(img, (MARGIN, MARGIN), (w-MARGIN, h-MARGIN), (80,80,80), 1)
 
    rgb    = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)
 
    gesture = "move"
    now     = time.time()
 
    # Draw all detected hands
    if result.multi_hand_landmarks:
        for hand_lm in result.multi_hand_landmarks:
            draw_utils.draw_landmarks(img, hand_lm, mp_hands.HAND_CONNECTIONS,
                draw_styl.get_default_hand_landmarks_style(),
                draw_styl.get_default_hand_connections_style())
 
    right_lm, left_lm = identify_hands(result, w, h)
 
    # ══════════════════════════════════════════════════════════════════════════
    #  INTENT GUARD — right hand must be inside box + settled before anything fires
    # ══════════════════════════════════════════════════════════════════════════
    if right_lm is not None and inside_box(right_lm, w, h):
        if hand_enter_time is None:
            hand_enter_time = now
        if not hand_active and now - hand_enter_time >= INTENT_SETTLE:
            hand_active = True
        # Show settle progress bar above knuckle
        if not hand_active:
            pct   = (now - hand_enter_time) / INTENT_SETTLE
            bar_w = int(80 * pct)
            kx, ky = right_lm[5]
            cv2.rectangle(img, (kx-40, ky-30), (kx+40, ky-18), (60,60,60), -1)
            cv2.rectangle(img, (kx-40, ky-30), (kx-40+bar_w, ky-18), (255,200,0), -1)
    else:
        # Hand left the box or disappeared — full reset
        hand_enter_time = None
        if right_lm is None:
            hand_active = False
            cursor_hist.clear()
            if dragging:
                pyautogui.mouseUp()
                dragging = False
            if pinch_start is not None:
                pinch_start = None
            scroll_anchor = None
 
    # ══════════════════════════════════════════════════════════════════════════
    #  DUAL-HAND CHECK — runs before single-hand logic
    #  Both hands must be visible.  Left hand = "shift key".
    # ══════════════════════════════════════════════════════════════════════════
    dual_active_keys = set()
    handled_by_dual  = False
 
    if right_lm is not None and left_lm is not None:
        r_fi = fingers_up(right_lm)
        l_fi = fingers_up(left_lm)

        r_fist = is_fist(r_fi)
        r_open = is_open(r_fi)
        l_fist = is_fist(l_fi)
        l_open = is_open(l_fi)

        l_thumb, l_index, l_middle, l_ring, l_pinky = l_fi

        # ── CLAP → Minimize all ───────────────────────────────────────────────
        # Arms when wrists are far apart, fires the moment they clap together
        wrist_dist = dist(right_lm[0], left_lm[0])
        if wrist_dist > CLAP_THRESH * 2.5:
            clap_armed = True
        if clap_armed and wrist_dist < CLAP_THRESH and now - last_clap > CLAP_COOLDOWN:
            minimize_all()
            gesture    = "minimize"
            last_clap  = now
            clap_armed = False
            handled_by_dual = True
        # ── ZOOM: both hands open, measure palm-to-palm distance ─────────────
        if r_open and l_open:
            # Palm centre = wrist landmark
            r_palm = right_lm[0]
            l_palm = left_lm[0]
            cur_dist = dist(r_palm, l_palm)
 
            if zoom_anchor_dist is None:
                zoom_anchor_dist = cur_dist
            else:
                delta = cur_dist - zoom_anchor_dist
                if abs(delta) > ZOOM_DEADZONE:
                    # accumulate and fire one Ctrl+/- per ZOOM_PX_PER_STEP
                    zoom_remainder += delta
                    steps = int(zoom_remainder / ZOOM_PX_PER_STEP)
                    if steps != 0 and now - zoom_last_time > ZOOM_KEY_DELAY:
                        if steps > 0:
                            for _ in range(abs(steps)):
                                pyautogui.hotkey("ctrl", "equal")   # Ctrl++
                            gesture = "zoom_in"
                        else:
                            for _ in range(abs(steps)):
                                pyautogui.hotkey("ctrl", "minus")   # Ctrl+-
                            gesture = "zoom_out"
                        zoom_remainder  -= steps * ZOOM_PX_PER_STEP
                        zoom_last_time   = now
                        zoom_anchor_dist = cur_dist
                    handled_by_dual = True
        else:
            zoom_anchor_dist = None
            zoom_remainder   = 0
 
        # Clear timers (no longer used but kept for safety)
        for key in {"both_fist","both_open","lf_ro","lo_rf"} - dual_active_keys:
            clear_dual(key)
 
    else:
        # Clear all dual timers if both hands aren't present
        for key in {"both_fist","both_open","lf_ro","lo_rf"}:
            clear_dual(key)
        zoom_anchor_dist = None
        zoom_remainder   = 0
 
    # ══════════════════════════════════════════════════════════════════════════
    #  LEFT HAND SOLO — volume swipe, scrubber, mute
    # ══════════════════════════════════════════════════════════════════════════
    if left_lm is not None and not handled_by_dual:
        l_fi = fingers_up(left_lm)
        l_thumb, l_index, l_middle, l_ring, l_pinky = l_fi

        d_ltm = dist(left_lm[4], left_lm[12])  # thumb–middle  → task view
        d_lti = dist(left_lm[4], left_lm[8])   # thumb–index   → minimize/restore

        # ── TASK VIEW: thumb + middle touch ──────────────────────────────────
        if d_ltm < LEFT_PINCH_THRESH:
            if now - last_snap > SNAP_COOLDOWN:
                task_view()
                last_snap = now
                gesture = "task_view"
            scrub_anchor_x = None
            vol_last_time  = 0.0
            vol_anchor_y   = None

        # ── MINIMIZE / RESTORE: thumb + index touch ───────────────────────────
        # Quick touch (< 0.4s) = minimize, hold (>= 0.4s) = restore
        elif d_lti < LEFT_PINCH_THRESH:
            if left_pinch_start is None:
                left_pinch_start = now
            scrub_anchor_x = None
            vol_last_time  = 0.0
            vol_anchor_y   = None

        # ── MUTE: peace sign (index + middle only) ───────────────────────────
        elif l_index==1 and l_middle==1 and l_ring==0 and l_pinky==0 and l_thumb==0:
            if now - last_mute_time > MUTE_COOLDOWN:
                mute_toggle()
                last_mute_time = now
                gesture = "mute"
            scrub_anchor_x = None
            vol_last_time  = 0.0
            vol_anchor_y   = None

        # ── VOLUME SWIPE: index + middle + ring up, thumb + pinky down ───────
        elif l_index==1 and l_middle==1 and l_ring==1 and l_pinky==0 and l_thumb==0:
            scrub_anchor_x = None
            cur_y = left_lm[12][1]
            if vol_anchor_y is None:
                vol_anchor_y = cur_y
            dy = cur_y - vol_anchor_y
            if abs(dy) > VOL_SWIPE_DEADZONE:
                if now - vol_last_time > VOL_REPEAT_DELAY:
                    if dy < 0:
                        volume_up();   gesture = "vol_up"
                    else:
                        volume_down(); gesture = "vol_down"
                    vol_last_time = now
                    vol_anchor_y  = cur_y
            else:
                pass

        # ── VIDEO SCRUBBER: index only, move left/right ───────────────────────
        elif l_index==1 and l_middle==0 and l_ring==0 and l_pinky==0 and l_thumb==0:
            vol_last_time = 0.0
            cur_x = left_lm[8][0]
            if scrub_anchor_x is None:
                scrub_anchor_x  = cur_x
                scrub_remainder = 0
            dx = cur_x - scrub_anchor_x
            if abs(dx) > SCRUB_DEADZONE:
                scrub_remainder += dx
                steps = int(scrub_remainder / SCRUB_PX_PER_KEY)
                if steps != 0 and now - scrub_last_time > SCRUB_KEY_DELAY:
                    key_to_press = "right" if steps > 0 else "left"
                    for _ in range(abs(steps)):
                        pyautogui.press(key_to_press)
                    scrub_remainder -= steps * SCRUB_PX_PER_KEY
                    scrub_last_time  = now
                    scrub_anchor_x   = cur_x
                gesture = "scrub"

        else:
            scrub_anchor_x = None
            vol_last_time  = 0.0
            vol_anchor_y   = None

        # ── Left pinch release: minimize (quick) or restore (hold) ───────────
        if d_lti >= LEFT_PINCH_THRESH and left_pinch_start is not None:
            held = now - left_pinch_start
            if held < 0.4:
                minimize_all()
                gesture = "minimize"
            else:
                restore_all()
                gesture = "restore"
            left_pinch_start = None
 
    # ══════════════════════════════════════════════════════════════════════════
    #  SINGLE-HAND (right hand) — cursor control
    #  Only runs if dual logic didn't handle this frame
    # ══════════════════════════════════════════════════════════════════════════
    if right_lm is not None and not handled_by_dual and hand_active:
        lm    = right_lm
        fi    = fingers_up(lm)
        thumb, index, middle, ring, pinky = fi
 
        # Accelerated cursor from index MCP (landmark 5)
        # Slow = precise, fast = reaches screen edges
        sx, sy = accel_move(lm[5][0], lm[5][1], w, h)
        cursor_hist.append((sx, sy))
        smooth_x = float(np.mean([p[0] for p in cursor_hist]))
        smooth_y = float(np.mean([p[1] for p in cursor_hist]))
 
        d_ti  = dist(lm[4], lm[8])    # thumb–index tip
        d_tp  = dist(lm[4], lm[20])   # thumb–pinky tip
        d_im  = dist(lm[8], lm[12])   # index–middle tips (scroll touch)

        # 1. SCROLL: index+middle tips must HOLD touching for SCROLL_HOLD_TIME
        if index==1 and middle==1 and ring==0 and pinky==0 and thumb==0:
            if d_im < SCROLL_TOUCH_THRESH:
                if scroll_touch_start is None:
                    scroll_touch_start = now
                if not scroll_locked and now - scroll_touch_start >= SCROLL_HOLD_TIME:
                    scroll_locked = True
            else:
                scroll_touch_start = None
                if d_im > SCROLL_TOUCH_THRESH * 2.0:
                    scroll_locked = False
                    scroll_anchor = None

            if scroll_locked:
                gesture = "scroll"
                yp = lm[8][1]
                if scroll_anchor is None:
                    scroll_anchor = yp
                dy = yp - scroll_anchor
                if abs(dy) > SCROLL_DEADZONE:
                    pyautogui.scroll(int(-dy * SCROLL_SCALE))
                    scroll_anchor = yp

        # 2. PINCH → click or drag
        elif (d_ti < PINCH_THRESH or (pinch_start is not None and d_ti < PINCH_RELEASE)) and not scroll_locked:
            if pinch_start is None:
                pinch_start = now
            pd = now - pinch_start
            if pd >= CLICK_TIME:
                gesture = "drag"
                if not dragging:
                    pyautogui.mouseDown()
                    dragging = True
                pyautogui.moveTo(smooth_x, smooth_y)
            else:
                gesture = "lclick"

        # 3. RIGHT CLICK: thumb+pinky
        elif d_tp < PINCH_THRESH and now - last_click > CLICK_COOLDOWN:
            gesture    = "rclick"
            pyautogui.rightClick()
            last_click = now

        # DEFAULT: always move
        else:
            gesture = "move"
            pyautogui.moveTo(smooth_x, smooth_y)
 
        # ── Post cleanup ──────────────────────────────────────────────────────
        # Fire click on pinch release — only when fingers open past PINCH_RELEASE
        if d_ti >= PINCH_RELEASE and pinch_start is not None:
            pd = now - pinch_start
            if pd < CLICK_TIME and now - last_click > CLICK_COOLDOWN:
                if now - last_click_release < dbl_click_window:
                    pyautogui.doubleClick()
                    gesture            = "dblclick"
                    last_click_release = 0.0
                else:
                    pyautogui.click()
                    gesture            = "lclick"
                    last_click_release = now
                last_click = now
            pinch_start = None

        if d_ti >= PINCH_RELEASE and dragging:
            pyautogui.mouseUp()
            dragging = False

        if gesture != "scroll":
            scroll_anchor = None
            # Only fully reset scroll lock when hand is in a clearly different pose
            if not (index==1 and middle==1 and ring==0 and pinky==0 and thumb==0):
                scroll_touch_start = None
                scroll_locked      = False
 
        # Dot on index MCP (the actual control point)
        c = COLORS.get(gesture, (200,200,200))
        cv2.circle(img, lm[5], 12, c, -1)
        cv2.circle(img, lm[5], 12, (255,255,255), 2)
 
    elif right_lm is None:
        if dragging:
            pyautogui.mouseUp(); dragging = False
        scroll_anchor      = None
        scroll_touch_start = None
        scroll_locked      = False
        cursor_hist.clear()
        pinch_start = None
 
    # ── Left hand indicator ───────────────────────────────────────────────────
    if left_lm is not None:
        l_fi_disp = fingers_up(left_lm)
        l_thumb_d, l_index_d, l_middle_d, l_ring_d, l_pinky_d = l_fi_disp
        if is_fist(l_fi_disp):
            l_label = "L: FIST"
        elif is_open(l_fi_disp):
            l_label = "L: OPEN"
        elif l_index_d==1 and l_middle_d==1 and l_ring_d==0 and l_pinky_d==0 and l_thumb_d==0:
            l_label = "L: MUTE"
        elif l_index_d==1 and l_middle_d==1 and l_ring_d==1 and l_pinky_d==0 and l_thumb_d==0:
            l_label = "L: VOL SWIPE"
        elif l_index_d==1 and l_middle_d==0:
            l_label = "L: SCRUB"
        else:
            l_label = "L: HAND"
        l_color = (255, 200, 0) if right_lm is not None else (180, 180, 180)
        cv2.putText(img, l_label, (left_lm[0][0]-40, left_lm[0][1]-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,0,0), 3)
        cv2.putText(img, l_label, (left_lm[0][0]-40, left_lm[0][1]-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, l_color, 1)
 
    # ── Gesture debounce ──────────────────────────────────────────────────────
    # Push raw gesture into buffer. Only update committed_gesture when all
    # slots agree — a single noisy frame can never flip move↔idle.
    gesture_buf.append(gesture)
    if len(gesture_buf) == GESTURE_CONFIRM_FRAMES and len(set(gesture_buf)) == 1:
        committed_gesture = gesture_buf[0]
    # Action gestures (click, drag, scroll, etc.) bypass debounce — they have
    # their own timing guards and should not be delayed.
    if gesture in ("lclick","dblclick","rclick","drag","scroll",
                   "alt_tab","task_view","minimize","restore",
                   "vol_up","vol_down","mute","scrub","zoom_in","zoom_out"):
        committed_gesture = gesture

    # ── HUD ───────────────────────────────────────────────────────────────────
    # Active zone box — green when active, yellow when settling, gray otherwise
    if hand_active:
        box_col, box_thick = (0, 220, 100), 2
        status_txt, status_col = "ACTIVE", (0, 220, 100)
    elif hand_enter_time is not None:
        box_col, box_thick = (255, 200, 0), 1
        status_txt, status_col = "Settling...", (255, 200, 0)
    else:
        box_col, box_thick = (80, 80, 80), 1
        status_txt, status_col = "No hand", (120, 120, 120)
 
    cv2.rectangle(img, (MARGIN, MARGIN), (w-MARGIN, h-MARGIN), box_col, box_thick)
 
    # Corner tick marks so edges are obvious
    tick = 16
    for cx_, cy_, dx, dy in [
        (MARGIN,   MARGIN,    1,  1),
        (w-MARGIN, MARGIN,   -1,  1),
        (MARGIN,   h-MARGIN,  1, -1),
        (w-MARGIN, h-MARGIN, -1, -1),
    ]:
        cv2.line(img, (cx_, cy_), (cx_ + dx*tick, cy_), box_col, 2)
        cv2.line(img, (cx_, cy_), (cx_, cy_ + dy*tick), box_col, 2)
 
    label = LABELS.get(committed_gesture, committed_gesture.upper())
    color = COLORS.get(committed_gesture, (200,200,200))
 
    cv2.putText(img, label, (14,42), cv2.FONT_HERSHEY_DUPLEX, 0.9, (0,0,0), 4)
    cv2.putText(img, label, (14,42), cv2.FONT_HERSHEY_DUPLEX, 0.9, color, 2)
    cv2.putText(img, f"FPS {fps_disp:.0f}", (14,70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150,150,150), 1)
    cv2.putText(img, status_txt, (14, 95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_col, 1)
 
    # Legend
    if show_legend:
        px   = w - 245
        rows = len(LEGEND_RIGHT) + len(LEGEND_LEFT) + len(LEGEND_DUAL) + 3
        overlay = img.copy()
        cv2.rectangle(overlay, (px-8, 4), (w-4, 10 + rows*20),
                      (15,15,15), -1)
        cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)
        row = 0
        cv2.putText(img, "-- RIGHT HAND --", (px, 22 + row*20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,220,100), 1); row += 1
        for sym, act in LEGEND_RIGHT:
            cv2.putText(img, f"{sym:<20} {act}", (px, 22 + row*20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,200), 1); row += 1
        cv2.putText(img, "-- LEFT HAND --", (px, 22 + row*20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100,180,255), 1); row += 1
        for sym, act in LEGEND_LEFT:
            cv2.putText(img, f"{sym:<20} {act}", (px, 22 + row*20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,200), 1); row += 1
        cv2.putText(img, "-- DUAL HAND --", (px, 22 + row*20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,200,0), 1); row += 1
        for sym, act in LEGEND_DUAL:
            line = f"{sym:<20} {act}" if act else sym
            cv2.putText(img, line, (px, 22 + row*20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200,200,200), 1); row += 1
 
    cv2.imshow("Iron-Hand v3", img)
    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break
    if key in (ord('l'), ord('L')):
        show_legend = not show_legend
 
# ── Cleanup ───────────────────────────────────────────────────────────────────
if dragging:  pyautogui.mouseUp()
cap.release()
cv2.destroyAllWindows()
print("[Iron-Hand v3] Stopped.")
 