import cv2
import cv2.aruco as aruco


class ArucoDetector:

    def __init__(self):
        self.dictionary = aruco.getPredefinedDictionary(
            aruco.DICT_4X4_50
        )

        self.parameters = aruco.DetectorParameters()

        self.detector = aruco.ArucoDetector(
            self.dictionary,
            self.parameters
        )

    def detect(self, frame):
        corners, ids, _ = self.detector.detectMarkers(frame)

        detections = []

        if ids is not None:
            for i, corner in enumerate(corners):
                pts = corner[0]

                center_x = int(pts[:, 0].mean())
                center_y = int(pts[:, 1].mean())

                marker_id = int(ids[i][0])

                detections.append({
                    "id": marker_id,
                    "x": center_x,
                    "y": center_y,
                    "corners": pts
                })

        return detections
