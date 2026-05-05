FROM python:3.11-slim

WORKDIR /srv

# Install Python deps first for build cache friendliness.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code.
COPY app ./app
COPY pupil_capture_bridge.py ./pupil_capture_bridge.py

# Mount or COPY the trained model into /models and point MODEL_PATH at it
# at deploy time, e.g.:
#   docker run -e MODEL_PATH=/models/v1_hgb_weak.joblib \
#              -v /path/to/ML\ Algorithm/models:/models:ro ...
ENV MODEL_PATH=/models/v1_hgb_weak.joblib

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
