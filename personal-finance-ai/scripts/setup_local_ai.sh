#!/usr/bin/env bash
set -euo pipefail

if ! command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract is missing. On macOS run:"
  echo "  brew install tesseract tesseract-lang"
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is missing. Install it from https://ollama.com/download"
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Start Ollama in another terminal:"
  echo "  ollama serve"
  exit 1
fi

ollama pull qwen2.5:3b

echo "OCR languages:"
tesseract --list-langs
echo "Local AI models:"
ollama list
