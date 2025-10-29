#!/usr/bin/env python3
# basler_focus_check_multi_rois.py

import sys
import cv2
import numpy as np
import argparse
import json

try:
    from pypylon import pylon
except ImportError:
    print("pypylon not found. Install with: pip install pypylon")
    sys.exit(1)

WINDOW_NAME = "Basler USB - Focus Check (multi-ROI)"
lens = 50
FOCUS_THRESHOLD = {35:{10:70,20:90,40:0},50:{10:0,20:70,40:90}}
SINGLE_CLICK_BOX = (200, 200)  # w, h

# ArUco detection parameters
ARUCO_DICT = cv2.aruco.DICT_4X4_250
ARUCO_PARAMS = cv2.aruco.DetectorParameters()

# --- Global UI state ---
mouse_down = False
pt_start = None
pt_end = None
rois = {10:[],20:[],40:[]}

def clamp_roi(x1, y1, x2, y2, w, h):
    x1, x2 = max(0, min(x1, x2)), min(w - 1, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(h - 1, max(y1, y2))
    return x1, y1, x2, y2

def focus_score(img_bgr, roi=None):
    if roi is not None:
        x1, y1, x2, y2 = roi
        if x2 - x1 < 5 or y2 - y1 < 5:
            return None
        crop = img_bgr[y1:y2, x1:x2]
    else:
        crop = img_bgr
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())

def classify(score, threshold=FOCUS_THRESHOLD):
    return "sharp" if score is not None and score >= threshold else "blurry"

def detect_and_draw_aruco_markers(image):
    global rois, lens
    """
    Detect ArUco markers in the image and draw them with IDs and corners.
    Returns the image with markers drawn and the number of markers detected.
    """
    # Convert to grayscale for ArUco detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Get ArUco dictionary
    aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    
    # Create detector
    detector = cv2.aruco.ArucoDetector(aruco_dict, ARUCO_PARAMS)
    
    # Detect markers
    corners, ids, rejected = detector.detectMarkers(gray)
    # Draw detected markers
    if ids is not None:
            
        corners_locations = {}
        marker_ids_at = {10:[0,1,2,3,4,5,6,7], 20:[18,19,20,21], 40:[8,9,10,11]}
        

        corners_locations = {40:[], 20:[], 10:[]}
        for i, marker_id in enumerate(ids):
            for dis in corners_locations.keys():
                if marker_id[0] in marker_ids_at[dis]:
                    corners_locations[dis].append(corners[i][0])
        
        means = {}
        rois_temp = {}
        for dis in corners_locations:
            corners_locations[dis] = np.asarray(corners_locations[dis])
            
            try:
                means[dis] = np.mean(np.mean(corners_locations[dis],axis=1), axis=0)
                mn = np.min(np.min(corners_locations[dis],axis=1),axis=0)
                mx = np.max(np.max(corners_locations[dis],axis=1),axis=0)
                if lens == 50 and dis == 40:
                    rois_temp[dis] = [int(mn[0]-60),int(mn[1]-60),int(mx[0]+10),int(mx[1]+10)]
                else:
                    rois_temp[dis] = [int(mn[0]-10),int(mn[1]-10),int(mx[0]+10),int(mx[1]+10)]
            except Exception as e:
                pass
        try:
            if means[10][1] - means[20][1] > 1200:
                lens = 50
            else:
                lens = 35
        except:
            pass
        try:
            if lens == 50:
                rois_temp.pop(10)
            else:
                rois_temp.pop(40)
        except:
            pass
        rois = rois_temp
    return image, len(ids) if ids is not None else 0

def find_single_usb_camera_or_die():
    tl = pylon.TlFactory.GetInstance()
    devs = tl.EnumerateDevices()
    usb_devs = [d for d in devs if d.GetDeviceClass() == "BaslerUsb"]

    if len(usb_devs) == 0:
        print("No Basler USB cameras found.")
        sys.exit(2)
    if len(usb_devs) > 1:
        print("Multiple Basler USB cameras found. Please connect exactly one.")
        for d in usb_devs:
            try:
                print(f" - {d.GetModelName()} SN:{d.GetSerialNumber()}")
            except Exception:
                pass
        sys.exit(3)
    return usb_devs[0]

def set_exposure_and_gain(cam, exposure_time_us=100.0, gain_val=10):
    """Robustly set Exposure=2000µs and Gain=10 with node fallbacks."""
    # Turn autos off first
    for node, val in [("ExposureAuto", "Off"), ("GainAuto", "Off")]:
        try:
            getattr(cam, node).SetValue(val)
        except Exception:
            pass

    # Exposure time nodes vary by model: ExposureTime or ExposureTimeAbs
    set_ok = False
    for node in ("ExposureTime", "ExposureTimeAbs"):
        try:
            n = getattr(cam, node)
            mn, mx = n.GetMin(), n.GetMax()
            n.SetValue(float(np.clip(exposure_time_us, mn, mx)))
            set_ok = True
            break
        except Exception:
            continue
    if not set_ok:
        print("[Warn] Could not set exposure time; node not available?")

    # Gain nodes vary: Gain, GainRaw
    set_ok = False
    for node in ("Gain", "GainRaw"):
        try:
            n = getattr(cam, node)
            # Some Gain nodes use integer range
            try:
                mn, mx = n.GetMin(), n.GetMax()
                val = int(np.clip(gain_val, mn, mx)) if "Raw" in node else float(np.clip(gain_val, mn, mx))
                n.SetValue(val)
            except Exception:
                n.SetValue(gain_val)
            set_ok = True
            break
        except Exception:
            continue
    if not set_ok:
        print("[Warn] Could not set gain; node not available?")

message = "Make sure to move the lens to the correct position and lock the screws and press 's' to save the image."

def main():
    global message
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Camera Calibration Tool')
    parser.add_argument('output_filename', nargs='?', default='Output.jpg', 
                       help='Output filename for the calibrated image (default: Output.jpg)')
    args = parser.parse_args()
    
    output_filename = args.output_filename
    dev_info = find_single_usb_camera_or_die()
    tl = pylon.TlFactory.GetInstance()
    cam = pylon.InstantCamera(tl.CreateDevice(dev_info))

    # Converter to BGR8 for OpenCV
    converter = pylon.ImageFormatConverter()
    converter.OutputPixelFormat = pylon.PixelType_BGR8packed
    converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

    cam.Open()

    # Continuous free-run
    for node, val in [("AcquisitionMode", "Continuous"), ("TriggerMode", "Off")]:
        try:
            getattr(cam, node).SetValue(val)
        except Exception:
            pass

    # Set exposure/gain as requested
    set_exposure_and_gain(cam, exposure_time_us=20000.0, gain_val=10)

    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    # cv2.setMouseCallback(WINDOW_NAME, on_mouse)

    print("[Instructions]")
    print(" - LEFT drag to add a rectangle ROI; LEFT single-click adds a 200x200 box.")
    print(" - RIGHT click removes the LAST ROI.")
    print(" - Press 'c' to clear all ROIs; 'q' or ESC to quit.")
    print(" - ArUco markers (4x4_250 dictionary) are automatically detected and displayed.")
    print(" - Exposure=2000µs, Gain=10 (autos disabled if possible).")

    try:
        while cam.IsGrabbing():
            grab = cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if not grab.GrabSucceeded():
                grab.Release()
                continue

            img = converter.Convert(grab).GetArray()
            grab.Release()

            h, w = img.shape[:2]
            overlay = img.copy()
            # Detect and draw ArUco markers
            overlay, num_markers = detect_and_draw_aruco_markers(overlay)

            # Draw and score all committed ROIs
            classifications = []
            for r in rois.keys():
                if len(rois[r]) == 4:
                    x1, y1, x2, y2 = clamp_roi(*rois[r], w, h)
                    score = focus_score(img, (x1, y1, x2, y2))
                    label = classify(score, FOCUS_THRESHOLD[lens][r])
                    classifications.append(label)
                    color = (0, 0, 255) if label == "blurry" else (0, 255, 0)
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 7)
                    txt = f"{r}:{score:.1f} {label}" if score is not None else f"{r}:n/a"
                    txt = f"{score:.0f}" if score is not None else f"{r}:n/a"
                    cv2.putText(overlay, txt, (x1, max(30, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 3,  (0, 0, 255), 10, cv2.LINE_AA)
                    cv2.putText(overlay, txt, (x1, max(30, y1 - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 3, color, 4, cv2.LINE_AA)

            # Full-frame score
            full_score = focus_score(img, None)
            full_label = classify(full_score, 100)
            cv2.putText(overlay, f"Full {full_score:.1f} : {full_label}",
                        (15, 100), cv2.FONT_HERSHEY_SIMPLEX, 3,
                        (0, 0, 255) if full_label == "blurry" else (0, 255, 0), 10, cv2.LINE_AA)
            
            # Display ArUco marker count
            cv2.putText(overlay, f"Detected Lens: {lens} mm",
                        (15, 200), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 0), 10, cv2.LINE_AA)
            cv2.putText(overlay, message,
                        (15, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 255), 10, cv2.LINE_AA)
            cv2.putText(overlay, message,
                        (15, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 5, cv2.LINE_AA)

            cv2.imshow(WINDOW_NAME, overlay)
            key = cv2.waitKey(1) & 0xFF

            if key in (27, ord('q')):   # ESC or q
                break
            elif key == ord('s') and 'blurry' not in classifications:
                cv2.imwrite(output_filename, overlay)
                
                # Save sharpness data to JSON file
                sharpness_data = {
                    'lens_mm': lens,
                    'sharpness_10m': None,
                    'sharpness_20m': None,
                    'sharpness_40m': None,
                    'rois_detected': list(rois.keys()),
                    'timestamp': None
                }
                
                # Extract sharpness scores for each distance
                for distance in rois.keys():
                    if len(rois[distance]) == 4:
                        x1, y1, x2, y2 = clamp_roi(*rois[distance], w, h)
                        score = focus_score(img, (x1, y1, x2, y2))
                        if distance == 10:
                            sharpness_data['sharpness_10m'] = float(score) if score is not None else None
                        elif distance == 20:
                            sharpness_data['sharpness_20m'] = float(score) if score is not None else None
                        elif distance == 40:
                            sharpness_data['sharpness_40m'] = float(score) if score is not None else None
                
                # Save sharpness data to JSON file
                sharpness_filename = output_filename.replace('.jpg', '_sharpness.json')
                with open(sharpness_filename, 'w') as f:
                    json.dump(sharpness_data, f, indent=2)
                
                print(f"Calibration successful! Image saved as: {output_filename}")
                print(f"Sharpness data saved as: {sharpness_filename}")
                break
            elif key == ord('s') and 'blurry' in classifications:
                message = "One of the ROIs is blurry. Please move the lens to the correct position and lock the screws and press 's' to save the image."
            elif key == ord('c'):
                rois.clear()

    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.StopGrabbing()
        except Exception:
            pass
        try:
            cam.Close()
        except Exception:
            pass
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
