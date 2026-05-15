install uv<br />
install python version 3.11 (powershell/terminal: uv python install 3.11)<br />
create virtual environment (uv venv --python 3.11)<br />
activate the environment (windows: .venv\Scripts\activate mac: source .venv/bin/activate)<br />
install libraries (uv pip install mediapipe opencv-python numpy python-osc)(mediapipe, opencv, numpy, python-osc)<br />

test:<br />
cd handtracker<br />
python tracker.py<br />


running each time:

windows:<br />
.venv\Scripts\activate<br />
cd handtracker<br />
python tracker.py<br />

macOs:<br />
source .venv/bin/activate<br />
cd handtracker<br />
python tracker.py<br />
