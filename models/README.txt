Neural network models for NeuroWings v2.0

Required models (place in this folder):
  - yolo_detect_best.pt     YOLO Detection model (~6 MB)
  - yolo_pose_best.pt       YOLO Pose estimation model (~6 MB)
  - stage2_best.pth         Stage2 Refinement model (~85 MB)
  - stage2_portable.pth     Stage2 Portable model (~85 MB)
  - subpixel_best.pth       SubPixel Refinement model (~10 MB)

Total size: ~190 MB

Without these models the application will start but neural network
processing will not be available. You can still open and edit TPS files.

Models are not included in the portable distribution to reduce download size.
Contact the author or download from the project releases page.
