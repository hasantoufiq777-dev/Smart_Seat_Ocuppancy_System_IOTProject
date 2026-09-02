import os
import argparse
import numpy as np
import cv2
import seat_utils
from object_detector import ObjectDetector
from seat import Seat, SeatStatus
from seat_utils import CvColor, calculate_overlap_percentage, rectangle_overlap, rectangle_area, get_overlap_rectangle, draw_box_and_text
from tqdm import tqdm
import sys
sys.path.append(os.path.abspath("SSOS"))
from detector import SeatDetector


def _parse_args():
    """Read CLI arguments"""
    parser = argparse.ArgumentParser(description="Library seat status detection using more traditional computer vision methods.")
    parser.add_argument("--video", type=str, default=os.path.expanduser("data/output.mp4"),
                        help="Path to the video file or camera index (e.g. 0) to run seat detection.")
    parser.add_argument("--seat-bb-csv", type=str, default="seat_bb.csv",
                        help="The CSV file containing bounding box coordinates.")
    parser.add_argument("--pretrained-model", type=str, default="models/faster_rcnn_inception_v2/frozen_inference_graph.pb",
                        help="The frozen TF model downloaded from Tensorflow detection model zoo: "
                             "https://github.com/tensorflow/models/blob/master/research/object_detection/g3doc/detection_model_zoo.md")
    parser.add_argument("--output", type=str, default="",
                        help="Output file name. Leave blank if no output is needed")
    parser.add_argument("--detect-interval", type=int, default=1,
                        help="Inference interval. Run detection once every N frames to speed up processing (recommended: 5 or 10 on Pi).")
    args = parser.parse_args()

    return args


def main(args):
    # Read in the bounding box coordinates
    if not os.path.isfile(args.seat_bb_csv):
        print("Argument seat-bb-csv is not a file: {}".format(args.seat_bb_csv))
        exit()
    # Each seat bounding box is in the format of [x0, y0, x1, y1]
    seat_bounding_boxes = np.genfromtxt(args.seat_bb_csv, delimiter=',', dtype=int)
    # seat_bounding_boxes //= downsample_ratio
    num_seats = len(seat_bounding_boxes) - 1

    # Open the video or camera
    is_live_camera = args.video.isdigit()
    if is_live_camera:
        video_source = int(args.video)
        try:
            from app import CameraStream
            cap = CameraStream(width=1280, height=720)
            print("[System] Opened live camera using CameraStream wrapper (720p).")
        except Exception as e:
            print("[System] CameraStream initialization failed ({}); falling back to cv2.VideoCapture...".format(e))
            cap = cv2.VideoCapture(video_source)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    else:
        video_source = args.video
        if not os.path.isfile(video_source):
            print("Argument video is not a file: {}".format(video_source))
            exit()
        cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        raise IOError("Failed to open video source: {}".format(args.video))
    success, frame = cap.read()  # Read the first frame

    if not success:
        print("Failed to read the first frame from: {}".format(args.video))
        exit()

    frame_h, frame_w, _ = frame.shape
    # Bounding boxes were defined for 1920x1080 resolution
    scale_x = frame_w / 1920.0
    scale_y = frame_h / 1080.0
    
    # Scale bounding boxes to actual frame size
    scaled_bounding_boxes = []
    for box in seat_bounding_boxes:
        x0, y0, x1, y1 = box
        x0_scaled = int(round(x0 * scale_x))
        y0_scaled = int(round(y0 * scale_y))
        x1_scaled = int(round(x1 * scale_x))
        y1_scaled = int(round(y1 * scale_y))
        
        # Ensure coordinates are within frame bounds and valid
        x0_scaled = max(0, min(x0_scaled, frame_w - 1))
        x1_scaled = max(x0_scaled + 1, min(x1_scaled, frame_w))
        y0_scaled = max(0, min(y0_scaled, frame_h - 1))
        y1_scaled = max(y0_scaled + 1, min(y1_scaled, frame_h))
        
        scaled_bounding_boxes.append([x0_scaled, y0_scaled, x1_scaled, y1_scaled])
    
    seat_bounding_boxes = np.array(scaled_bounding_boxes)

    # Create the object detector from the frozen model
    obj_detector = ObjectDetector(args.pretrained_model)
    OBJ_DETECTION_THRESHOLD = 0.7

    # Initialize apparent gender detector
    gender_detector = SeatDetector()
    gender_detector.warmup()

    # Initialize Seats object
    seats = []
    table_bb = seat_bounding_boxes[0]
    for seat in range(num_seats):
        x0, y0, x1, y1 = seat_bounding_boxes[seat+1]
        seats.append(Seat(frame[y0:y1, x0:x1], seat_bounding_boxes[seat+1], table_bb))
    SEAT_OVERLAP_THRESHOLD = 0.3

    if is_live_camera:
        TOTAL_FRAME_COUNT = 0
        VIDEO_1_FRAME_COUNT = 0.0
        VIDEO_2_FRAME_COUNT = 0
        progress_bar = tqdm(unit='frames')
        seat_labels = []
    else:
        TOTAL_FRAME_COUNT = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        VIDEO_1_FRAME_COUNT = 525.0
        VIDEO_2_FRAME_COUNT = max(0.0, TOTAL_FRAME_COUNT - VIDEO_1_FRAME_COUNT)
        progress_bar = tqdm(range(int(TOTAL_FRAME_COUNT)), unit='frames')
        seat_labels = np.full((int(VIDEO_2_FRAME_COUNT), num_seats), -1, dtype=int)

    # JUMP_TO_FRAME = 2100
    # cap.set(cv2.CAP_PROP_POS_FRAMES, JUMP_TO_FRAME)
    # progress_bar.update(JUMP_TO_FRAME)

    if args.output:
        frame_width, frame_height = int(cap.get(3)), int(cap.get(4))
        out = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 30, (frame_width, frame_height))
    # Start the seat detection
    frame_count = 0
    loop_count = 0
    
    last_detected_faces = []
    last_detected_person_bounding_boxes = []
    last_detected_chair_bounding_boxes = []
    last_boxes = []
    last_scores = []
    last_classes = []

    while True:
        success, frame = cap.read()  # Read the next frame
        if not success:
            break  # No more frames
        progress_bar.update()
        draw_frame = frame.copy()

        # Downsample frame for fast inference
        inference_w = 640
        inference_h = int(inference_w * (frame_h / frame_w))
        frame_small = cv2.resize(frame, (inference_w, inference_h), interpolation=cv2.INTER_NEAREST)
        scale_x = frame_w / float(inference_w)
        scale_y = frame_h / float(inference_h)

        # Run face, gender, and object detection only once every detect_interval frames
        if loop_count % args.detect_interval == 0:
            last_detected_faces_small = gender_detector.process_frame(frame_small)
            
            # Scale face boxes back to display coordinates
            last_detected_faces = []
            for face in last_detected_faces_small:
                fx1, fy1, fx2, fy2 = face["box"]
                last_detected_faces.append({
                    "box": (int(fx1 * scale_x), int(fy1 * scale_y), int(fx2 * scale_x), int(fy2 * scale_y)),
                    "gender": face["gender"],
                    "confidence": face["confidence"],
                })

            # Run object detection on small frame
            last_boxes_small, last_scores, last_classes, num = obj_detector.processFrame(frame_small)

            # Scale object boxes back to display coordinates
            last_boxes = []
            for box in last_boxes_small:
                ymin, xmin, ymax, xmax = box
                last_boxes.append((
                    int(ymin * scale_y),
                    int(xmin * scale_x),
                    int(ymax * scale_y),
                    int(xmax * scale_x)
                ))

            last_detected_person_bounding_boxes = []
            last_detected_chair_bounding_boxes = []
            for i, box in enumerate(last_boxes):
                if last_classes[i] == 1 and last_scores[i] > OBJ_DETECTION_THRESHOLD:
                    last_detected_person_bounding_boxes += [(box[1], box[0], box[3], box[2])]
                elif last_classes[i] == 62 and last_scores[i] > OBJ_DETECTION_THRESHOLD:
                    last_detected_chair_bounding_boxes += [(box[1], box[0], box[3], box[2])]

        detected_faces = last_detected_faces
        detected_person_bounding_boxes = last_detected_person_bounding_boxes
        detected_chair_bounding_boxes = last_detected_chair_bounding_boxes

        # Draw detected boxes from the last processed frame
        for i, box in enumerate(last_boxes):
            if last_classes[i] == 1 and last_scores[i] > OBJ_DETECTION_THRESHOLD:
                # Match face gender with this person box
                ymin, xmin, ymax, xmax = box
                human_gender = "Unknown"
                for face in detected_faces:
                    fx1, fy1, fx2, fy2 = face["box"]
                    # Calculate overlap between human box and face box
                    overlap_w = max(0, min(xmax, fx2) - max(xmin, fx1))
                    overlap_h = max(0, min(ymax, fy2) - max(ymin, fy1))
                    if overlap_w > 0 and overlap_h > 0:
                        human_gender = face["gender"]
                        break
                
                label = "human: {:.2f} ({})".format(last_scores[i], human_gender)
                seat_utils.draw_box_and_text(draw_frame, label, box, CvColor.BLUE)
            elif last_classes[i] == 62 and last_scores[i] > OBJ_DETECTION_THRESHOLD:
                seat_utils.draw_box_and_text(draw_frame, "chair: {:.2f}".format(last_scores[i]), box, CvColor.YELLOW)

        # Store the seat status for comparison with ground truth
        this_frame_seat_labels = np.full(num_seats, -1, dtype=int)
        for seat_id, this_seat in enumerate(seats):
            this_seat_img = this_seat.get_seat_image(frame)  # Crop the image to seat bounding box

            # Calculate overlap of the seat with each person bounding box
            # Use ratio of overlap area to the seat area (instead of IoU)
            person_detected = False
            for person_bb in detected_person_bounding_boxes:
                overlap_area, _ = rectangle_overlap(this_seat.bb_coordinates, person_bb)
                overlap_ratio = overlap_area / this_seat.bb_area
                if overlap_ratio > SEAT_OVERLAP_THRESHOLD:
                    person_detected = True  # Enough overlap, mark as person detected in the seat
                    break  # Person detected in the seat, no need to check other boxes

            for chair_bb in detected_chair_bounding_boxes:
                relative_bb = get_overlap_rectangle(this_seat.bb_coordinates, chair_bb, relative=True)
                if relative_bb is not None:
                    this_seat.update_chair_bb(relative_bb)

            # Update the seat status
            if person_detected:
                this_seat.person_detected()
            else:
                this_seat.no_person_detected(this_seat_img)

            # Store status for this seat
            this_frame_seat_labels[seat_id] = this_seat.status.value

            # Draw clean status overlay directly on the frame
            x0, y0, x1, y1 = this_seat.bb_coordinates
            if this_seat.status == SeatStatus.EMPTY:
                color = CvColor.GREEN
            elif this_seat.status == SeatStatus.OCCUPIED:
                color = CvColor.RED
            else:
                color = CvColor.YELLOW

            # Draw seat box
            cv2.rectangle(draw_frame, (x0, y0), (x1, y1), color, 2)

            # Extract apparent gender if the seat is occupied
            seat_gender = "Unknown"
            if this_seat.status == SeatStatus.OCCUPIED:
                for face in detected_faces:
                    fx1, fy1, fx2, fy2 = face["box"]
                    overlap_area, _ = rectangle_overlap(this_seat.bb_coordinates, (fx1, fy1, fx2, fy2))
                    if overlap_area > 0:
                        seat_gender = face["gender"]
                        break

            # Draw text label with solid background just above the seat box
            if this_seat.status == SeatStatus.OCCUPIED:
                label = "Seat {}: {} ({})".format(seat_id, this_seat.status.name, seat_gender)
            else:
                label = "Seat {}: {}".format(seat_id, this_seat.status.name)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            thickness = 1
            
            # Get text size
            (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            
            # Draw filled background rectangle for label
            label_y0 = max(y0 - text_h - 10, 0)
            label_y1 = label_y0 + text_h + 10
            cv2.rectangle(draw_frame, (x0, label_y0), (x0 + text_w + 10, label_y1), color, -1)
            
            # Draw text on top (black text for maximum readability)
            cv2.putText(draw_frame, label, (x0 + 5, label_y1 - 5 - baseline // 2), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
        
        frame_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)

        if is_live_camera:
            seat_labels.append(this_frame_seat_labels)
            frame_count += 1
        elif frame_pos > VIDEO_1_FRAME_COUNT:
            seat_labels[frame_count] = this_frame_seat_labels
            frame_count += 1

        if args.output:
            out.write(draw_frame)
        cv2.imshow("Preview", draw_frame)
        key = cv2.waitKey(1)
        if key & 0xFF == ord('q'):
            break

        # Save frames if directory exists
        if os.path.exists("img"):
            save_name = frame_count if is_live_camera else frame_pos
            cv2.imwrite("img/frame_{}.jpg".format(save_name), draw_frame)

        loop_count += 1

    # Video playback ended. Clean up
    progress_bar.close()
    obj_detector.close()
    cap.release()
    if args.output:
        out.release()
    cv2.destroyAllWindows()

    # Store the labels for seats
    if len(seat_labels) > 0:
        header_str = ",".join(["seat{}".format(i) for i in range(num_seats)])
        np.savetxt("labels.csv", np.array(seat_labels), fmt="%s", delimiter=',', header=header_str)


if __name__ == "__main__":
    args = _parse_args()
    main(args)
