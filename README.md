install uv<br />
install python version 3.11 (powershell/terminal: uv python install 3.11)<br />
create virtual environment (uv venv --python 3.11)<br />
activate the environment (windows: .venv\Scripts\activate mac: source .venv/bin/activate)<br />
install libraries (uv pip install mediapipe opencv-python numpy python-osc)(mediapipe, opencv, numpy, python-osc)<br />

test:
cd handtracker
python tracker.py


running each time:

windows:
.venv\Scripts\activate
cd handtracker
python tracker.py

macOs:
source .venv/bin/activate
cd handtracker
python tracker.py
