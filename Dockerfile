FROM python:3.11-slim

# libgl1/libglib2.0-0: dependências nativas do OpenCV mesmo na variante headless.
# libgomp1: usado por scipy/scikit-image/torch para paralelismo.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# torch é instalado separado, a partir do índice CPU-only do PyTorch: o pacote
# padrão do PyPI traz dependências CUDA que não servem para um container sem
# GPU e inflam a imagem em ~1-2GB à toa.
RUN grep -v "^torch" requirements.txt > requirements-notorch.txt \
    && pip install --no-cache-dir -r requirements-notorch.txt \
    && pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

COPY . .

EXPOSE 8000

CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
