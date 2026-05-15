import cv2
import mediapipe as mp
import numpy as np
from pythonosc import udp_client

class WorkingSqueezeTracker:
    def __init__(self, osc_host="127.0.0.1", osc_port=57120):
        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )

        # OSC
        self.osc = udp_client.SimpleUDPClient(osc_host, osc_port)

        # Running dynamic range (for auto-scaling learning)
        self.global_min = {}
        self.global_max = {}

        # Fixed calibration: dicts keyed by "Left" or "Right", each mapping metric_name -> value
        self.fixed_min = {"Left": {}, "Right": {}}
        self.fixed_max = {"Left": {}, "Right": {}}

        # Current instantaneous raw metric values (un-normalized, per frame)
        self.current_values = {}

        # Smoothing buffers for normalized values
        self.buffers = {}

        print("Controls: q = quit, 3/4 = lock Left min/max, 5/6 = lock Right min/max, "
              "z = clear Left, x = clear Right, c = clear both")

    # ---------------------------
    # Utility helpers
    # ---------------------------

    def distance(self, p1, p2, frame):
        """Euclidean distance in pixels between two normalized landmarks, scaled to frame size."""
        dx = (p1.x - p2.x) * frame.shape[1]
        dy = (p1.y - p2.y) * frame.shape[0]
        return float(np.sqrt(dx*dx + dy*dy))

    def smooth_value(self, key, value, size=5):
        """Simple moving average smoother."""
        buf = self.buffers.setdefault(key, [])
        buf.append(value)
        if len(buf) > size:
            buf.pop(0)
        return float(np.mean(buf))

    def detect_hand_side(self, hand_landmarks, handedness):
        """Prefer MediaPipe handedness label; fallback to wrist vs middle MCP heuristic."""
        if handedness and handedness.classification:
            return handedness.classification[0].label  # 'Left' or 'Right'
        lm = hand_landmarks.landmark
        # If wrist.x < middle_mcp.x, then it's likely right-hand from camera perspective
        return "Right" if lm[0].x < lm[9].x else "Left"

    # ---------------------------
    # Calibration functions
    # ---------------------------

    def lock_current_as_min(self, hand):
        """Lock current instantaneous values as fixed MIN for a hand."""
        locked = 0
        for k, v in self.current_values.items():
            if k.startswith(hand + "_"):
                self.fixed_min[hand][k] = float(v)
                locked += 1
        print(f"[CALIB] Locked MIN for {hand}: {locked} metrics")

    def lock_current_as_max(self, hand):
        """Lock current instantaneous values as fixed MAX for a hand."""
        locked = 0
        for k, v in self.current_values.items():
            if k.startswith(hand + "_"):
                self.fixed_max[hand][k] = float(v)
                locked += 1
        print(f"[CALIB] Locked MAX for {hand}: {locked} metrics")

    def clear_calibration_for(self, hand):
        self.fixed_min[hand].clear()
        self.fixed_max[hand].clear()
        print(f"[CALIB] Cleared calibration for {hand}")

    def clear_all_calibration(self):
        self.clear_calibration_for("Left")
        self.clear_calibration_for("Right")
        print("[CALIB] Cleared ALL calibration")

    # ---------------------------
    # Range / normalize
    # ---------------------------

    def update_global_range(self, key, value):
        """Track dynamic global min/max for adaptive ranges (helps if user never calibrates)."""
        if key not in self.global_min or value < self.global_min[key]:
            self.global_min[key] = float(value)
        if key not in self.global_max or value > self.global_max[key]:
            self.global_max[key] = float(value)

    def normalize(self, key, value):
        """
        Normalize value to [0,1].
        Priority:
         - If both fixed_min and fixed_max exist for this key -> use those (calibrated mode)
         - If only one is present -> combine fixed with global other side
         - Otherwise use global_min/global_max
        """
        hand = "Left" if key.startswith("Left_") else "Right"

        has_fixed_min = key in self.fixed_min[hand]
        has_fixed_max = key in self.fixed_max[hand]

        if has_fixed_min and has_fixed_max:
            min_val = self.fixed_min[hand][key]
            max_val = self.fixed_max[hand][key]
        elif has_fixed_min:
            min_val = self.fixed_min[hand][key]
            max_val = self.global_max.get(key, min_val + 1e-6)
        elif has_fixed_max:
            max_val = self.fixed_max[hand][key]
            min_val = self.global_min.get(key, max_val - 1e-6)
        else:
            min_val = self.global_min.get(key, value)
            max_val = self.global_max.get(key, value + 1e-6)

        # Avoid division by zero
        if (max_val - min_val) < 1e-9:
            return 0.0

        return float(np.clip((value - min_val) / (max_val - min_val), 0.0, 1.0))

    # ---------------------------
    # Hand processing
    # ---------------------------

    def process_hand(self, hand_landmarks, frame, hand_label):
        lm = hand_landmarks.landmark
        wrist = lm[0]
        # tips and mcps (thumb excluded for tip_to_mcp computation)
        tip_indices = [8, 12, 16, 20]
        mcp_indices = [5, 9, 13, 17]

        tips = [lm[i] for i in tip_indices]
        mcps = [lm[i] for i in mcp_indices]

        thumb_tip = lm[4]
        index_mcp = lm[9]  # using middle finger MCP as scale anchor (index 9 is middle_mcp in Mediapipe)

        # --- Camera distance estimation ---
        index_mcp_true = lm[5]
        pinky_mcp = lm[17]
        middle_mcp = lm[9]

        palm_width_px = self.distance(index_mcp_true, pinky_mcp, frame)
        palm_height_px = self.distance(wrist, middle_mcp, frame)

        hand_size = (palm_width_px + palm_height_px) * 0.5

        # inverse so bigger value = farther away
        camera_distance = 1.0 / (hand_size + 1e-6)

        # scale reference: wrist -> middle_mcp distance (non-zero if hand visible)
        scale = self.distance(wrist, lm[9], frame)
        if scale < 1e-6:
            scale = 1.0  # fallback so we don't divide by zero; will be normalized anyway

        # compute absolute distances, then convert to scale-invariant ratios
        tip_to_mcp_px = [self.distance(t, m, frame) for t, m in zip(tips, mcps)]
        tip_to_mcp = [d / scale for d in tip_to_mcp_px]

        thumb_to_index_mcp_px = self.distance(thumb_tip, index_mcp, frame)
        thumb_to_index_mcp = thumb_to_index_mcp_px / scale

        avg_tip_to_wrist_px = np.mean([self.distance(t, wrist, frame) for t in tips])
        avg_tip_to_wrist = avg_tip_to_wrist_px / scale

        # MCP-to-MCP cluster spread (mean pairwise) as ratio
        pairwise = []
        for i, m1 in enumerate(mcps):
            for j, m2 in enumerate(mcps):
                if j > i:
                    pairwise.append(self.distance(m1, m2, frame))
        mcp_to_mcp_px = np.mean(pairwise) if pairwise else 0.0
        mcp_to_mcp = mcp_to_mcp_px / scale

        # Raw (scaled) metrics list
        raw_metrics = tip_to_mcp + [
            thumb_to_index_mcp,
            avg_tip_to_wrist,
            mcp_to_mcp,
            camera_distance
        ]

        # Names for metrics
        metric_names = [f"{hand_label}_tip_to_mcp_{i}" for i in range(4)] + [
            f"{hand_label}_thumb_to_index_mcp",
            f"{hand_label}_avg_tip_to_wrist",
            f"{hand_label}_mcp_to_mcp",
            f"{hand_label}_camera_distance"
        ]

        # Save current raw values (for locking current frame as calibration)
        for key, val in zip(metric_names, raw_metrics):
            self.current_values[key] = float(val)

        # Update global ranges (helpful if user never calibrates)
        for key, val in zip(metric_names, raw_metrics):
            self.update_global_range(key, val)

        # Normalize & smooth
        smoothed = []
        normalized_map = {}
        for key, val in zip(metric_names, raw_metrics):
            norm = self.normalize(key, val)
            sm = self.smooth_value(key, norm, size=5)
            smoothed.append(sm)
            normalized_map[key] = sm

        # Compute a single "openness" metric (mean of finger tip-to-mcp normalized)
        #openness_keys = [f"{hand_label}_tip_to_mcp_{i}" for i in range(4)]
        #openness_vals = [normalized_map[k] for k in openness_keys if k in normalized_map]
        #openness = float(np.mean(openness_vals)) if openness_vals else 0.0

        # Send OSC: per-hand array plus openness separately
        try:
            self.osc.send_message(f"/hand/{hand_label.lower()}", smoothed)
            #self.osc.send_message(f"/hand/{hand_label.lower()}/openness", openness)
        except Exception as e:
            # don't crash on OSC errors
            print("[OSC] send error:", e)

        # Prepare metrics for visualization
        metrics = normalized_map
        #metrics[f"{hand_label}_openness"] = openness

        return metrics, hand_landmarks

    # ---------------------------
    # Drawing
    # ---------------------------

    def draw_visuals(self, frame, metrics, hand_label, lm):
        # left = left column, right = right column
        if hand_label == "Left":
            x = 10
            y = 30
        else:
            x = frame.shape[1] - 260
            y = 30

        # draw numeric metrics
        ordered_keys = [
            f"{hand_label}_tip_to_mcp_{i}" for i in range(4)
        ] + [
            f"{hand_label}_thumb_to_index_mcp",
            f"{hand_label}_avg_tip_to_wrist",
            f"{hand_label}_mcp_to_mcp",
            f"{hand_label}_camera_distance"
        ]

        for key in ordered_keys:
            if key in metrics:
                clean = key.split("_", 1)[1]
                cv2.putText(frame, f"{hand_label} {clean}: {metrics[key]:.2f}", (x, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y += 18


        # draw landmarks if present
        if lm is not None:
            self.mp_drawing.draw_landmarks(frame, lm, self.mp_hands.HAND_CONNECTIONS)

    # ---------------------------
    # Main loop
    # ---------------------------

    def run(self, camera_index=0):
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print("Error: cannot open camera")
            return
        print("Camera opened")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Empty frame, exiting")
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)

            left_metrics = right_metrics = None
            left_lm = right_lm = None

            if results.multi_hand_landmarks:
                for i, lm in enumerate(results.multi_hand_landmarks):
                    handed = results.multi_handedness[i] if results.multi_handedness else None
                    side = self.detect_hand_side(lm, handed)
                    metrics, landmarks = self.process_hand(lm, frame, side)
                    if side == "Left":
                        left_metrics, left_lm = metrics, landmarks
                    else:
                        right_metrics, right_lm = metrics, landmarks

            if left_metrics:
                self.draw_visuals(frame, left_metrics, "Left", left_lm)
            if right_metrics:
                self.draw_visuals(frame, right_metrics, "Right", right_lm)

            cv2.imshow("Dynamic Hand Tracking (scale-invariant)", frame)
            key = cv2.waitKey(1) & 0xFF

            # Controls:
            if key == ord('q'):
                break
            elif key == ord('3'):
                self.lock_current_as_min("Left")
            elif key == ord('4'):
                self.lock_current_as_max("Left")
            elif key == ord('5'):
                self.lock_current_as_min("Right")
            elif key == ord('6'):
                self.lock_current_as_max("Right")
            elif key == ord('z'):
                self.clear_calibration_for("Left")
            elif key == ord('x'):
                self.clear_calibration_for("Right")
            elif key == ord('c'):
                self.clear_all_calibration()

        cap.release()
        cv2.destroyAllWindows()
        print("Stopped")

if __name__ == "__main__":
    tracker = WorkingSqueezeTracker()
    tracker.run()
