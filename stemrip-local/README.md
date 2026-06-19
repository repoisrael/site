# StemRip Local

A local web app for splitting audio into stems with Demucs.

It supports:

- 4 stems: vocals, drums, bass, other
- 2 stems: vocals + instrumental / no-vocals
- Experimental 6 stems: vocals, drums, bass, guitar, piano, other
- ZIP download for all stems
- Individual stem downloads
- Job status polling and process logs

Use this only on audio you own or have permission to process.

## Requirements

- Python 3.10 or 3.11 recommended
- FFmpeg installed and available in your PATH
- For GPU acceleration: a CUDA-capable PyTorch install matching your system

## Install

```bash
cd stemrip-local
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## GitHub / Codespaces

This is a Python backend app, not a static GitHub Pages app. For GitHub-hosted development, use Codespaces.

In the Codespaces terminal:

```bash
cd stemrip-local
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open the forwarded port 8000 preview.

The first separation may take longer because Demucs downloads its model weights.

## Docker CPU-only option

```bash
docker build -t stemrip-local .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" stemrip-local
```

## Notes

Stem separation is approximate and may include bleed or artifacts. This starter app keeps jobs in memory, so it is a local/dev tool, not production-ready SaaS yet.
