# Running StemRip Local on GitHub

This app needs a Python backend, FFmpeg, and Demucs model execution. It is not a static GitHub Pages app.

## Best GitHub option: Codespaces

1. Open the repository branch that contains this folder.
2. Click **Code** → **Codespaces** → **Create codespace**.
3. In the terminal, run:

```bash
cd stemrip-local
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. Open the forwarded port 8000 preview.

The first separation may take longer because Demucs downloads its model weights.

## GitHub Actions

The workflows included inside this folder are templates. For Actions to run automatically, move `.github/workflows/*.yml` to the repository root or create a dedicated repository for this app.

## Dedicated repository commands

```bash
git init
git add .
git commit -m "Initial StemRip Local app"
gh repo create stemrip-local --private --source=. --remote=origin --push
```

To make it public:

```bash
gh repo edit stemrip-local --visibility public
```
