import cv2
import mediapipe as mp
import numpy as np
from pythonosc import udp_client

class WorkingSqueezeTracker:
    def __init__(self):
        # Initialize MediaPipe
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )

        # Initialize OSC client
        self.osc = udp_client.SimpleUDPClient("127.0.0.1", 57120)

        # Min/max trackers for scaling to [0, 1]
        self.global_min = {}
        self.global_max = {}

        # Smoothing buffers
        self.buffers = {}

        self.fixed_min = {"Left": {}, "Right": {}}
        self.fixed_max = {"Left": {}, "Right": {}}  # stores locked max values for each metric
        self.calibrate_mode = False  # optional, to trigger calibration state


        print("Press 'q' to quit")

    ### Utility functions ###

    def distance(self, point1, point2, frame):
        dx = (point1.x - point2.x) * frame.shape[1]
        dy = (point1.y - point2.y) * frame.shape[0]
        return np.sqrt(dx*dx + dy*dy)

    def update_global_range(self, key, value):
        # Detect which hand the key belongs to
        hand = "Left" if key.startswith("Left_") else "Right"

        # Don't update if that hand's max is fixed
        if key not in self.fixed_max[hand]:
            if key not in self.global_min or value < self.global_min[key]:
                self.global_min[key] = value
            if key not in self.global_max or value > self.global_max[key]:
                self.global_max[key] = value



    def normalize(self, key, value):
        hand = "Left" if key.startswith("Left_") else "Right"

        min_val = self.fixed_min[hand].get(key, self.global_min.get(key, 0.0))
        max_val = self.fixed_max[hand].get(key, self.global_max.get(key, 1.0))

        if max_val - min_val < 1e-9:
            return 0.0

        return np.clip((value - min_val) / (max_val - min_val), 0.0, 1.0)


    
    def lock_current_as_min(self, hand):
        """Save current global MIN values as fixed min for this hand."""
        self.fixed_min[hand] = {
            key: self.global_min[key] for key in self.global_min if key.startswith(hand + "_")
        }
        print(f"Fixed MIN for {hand}: {len(self.fixed_min[hand])} metrics locked.")

    def lock_current_as_max(self, hand):
        """Save current global MAX values as fixed max for this hand."""
        self.fixed_max[hand] = {
            key: self.global_max[key] for key in self.global_max if key.startswith(hand + "_")
        }
        print(f"Fixed MAX for {hand}: {len(self.fixed_max[hand])} metrics locked.")

    def clear_calibration(self, hand):
        self.fixed_min[hand].clear()
        self.fixed_max[hand].clear()
        print(f"Calibration cleared for {hand} hand.")





    def smooth_value(self, key, value, size=5):
        if key not in self.buffers:
            self.buffers[key] = []
        buffer = self.buffers[key]
        buffer.append(value)
        if len(buffer) > size:
            buffer.pop(0)
        return np.mean(buffer)

    def detect_hand_side(self, hand_landmarks, handedness):
        if handedness and handedness.classification:
            return handedness.classification[0].label
        # fallback by comparing wrist to mcp
        landmarks = hand_landmarks.landmark
        return "Right" if landmarks[0].x < landmarks[9].x else "Left"

    ### Hand Tracking & OSC ###

    def process_hand(self, hand_landmarks, frame, hand_label):
        lm = hand_landmarks.landmark
        wrist = lm[0]

        # Fingertip and MCP indices (thumb excluded for tip_to_mcp)
        tips = [lm[i] for i in [8, 12, 16, 20]]     # index, middle, ring, pinky tips
        mcps = [lm[i] for i in [5, 9, 13, 17]]      # corresponding MCPs

        # Thumb tip and index MCP
        thumb_tip = lm[4]
        index_mcp = lm[9]

        # Compute distances
        tip_to_mcp = [self.distance(tip, mcp, frame) for tip, mcp in zip(tips, mcps)]
        thumb_to_index_mcp = self.distance(thumb_tip, index_mcp, frame)
        avg_tip_to_wrist = np.mean([self.distance(tip, wrist, frame) for tip in tips])
        mcp_to_mcp = np.mean([self.distance(m1, m2, frame) for i, m1 in enumerate(mcps) for j, m2 in enumerate(mcps) if j > i])

        # Collect raw metrics
        raw_metrics = tip_to_mcp + [thumb_to_index_mcp, avg_tip_to_wrist, mcp_to_mcp]

        # Normalize, smooth, and update global ranges
        smoothed = []
        metric_names = [f"{hand_label}_tip_to_mcp_{i}" for i in range(4)] + \
                       [f"{hand_label}_thumb_to_index_mcp",
                        f"{hand_label}_avg_tip_to_wrist",
                        f"{hand_label}_mcp_to_mcp"]

        for key, value in zip(metric_names, raw_metrics):
            self.update_global_range(key, value)
            norm_value = self.normalize(key, value)
            smoothed_val = self.smooth_value(key, norm_value)
            smoothed.append(smoothed_val)

        # Send via OSC as bundle
        self.osc.send_message(f"/hand/{hand_label.lower()}", smoothed)

        # Package for visuals
        metrics = dict(zip(metric_names, smoothed))
        return metrics, hand_landmarks

    ### Visualization ###

    def draw_visuals(self, frame, metrics, hand_label, lm):
        # Set x position based on hand side
        if hand_label == "Left":
            x = 10
            y = 30
        else:  # Right hand on the right side of the screen
            x = frame.shape[1] - 250  # Adjust width offset as needed
            y = 30

        for key, val in metrics.items():
            clean_key = key.split("_", 1)[1]  # Remove the "Left_" or "Right_" prefix
            cv2.putText(frame, f"{hand_label} {clean_key}: {val:.2f}", (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y += 20

        if lm:
            self.mp_drawing.draw_landmarks(
                frame, lm, self.mp_hands.HAND_CONNECTIONS
            )

    ### Main loop ###

    def run(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Error: Cannot open camera")
            return
        print("Camera opened successfully")

        while True:
            ret, frame = cap.read()
            if not ret:
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

            # Draw visuals
            if left_metrics:
                self.draw_visuals(frame, left_metrics, "Left", left_lm)
            if right_metrics:
                self.draw_visuals(frame, right_metrics, "Right", right_lm)

            cv2.imshow("Dynamic Hand Tracking", frame)
            key = cv2.waitKey(1) & 0xFF
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
            elif key == ord('c'):
                self.clear_calibration("Left")
                self.clear_calibration("Right")

            elif key == ord('c'):
                self.clear_fixed_max("Left")
                self.clear_fixed_max("Right")



        cap.release()
        cv2.destroyAllWindows()
        print("Tracker stopped")

if __name__ == "__main__":
    tracker = WorkingSqueezeTracker()
    tracker.run()
