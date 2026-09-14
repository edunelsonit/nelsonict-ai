"""Explicit online helper. Application runtime never downloads embedding models."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("model", help="Sentence Transformers model identifier")
parser.add_argument("destination", type=Path)
args = parser.parse_args()
if args.destination.exists() and any(args.destination.iterdir()):
    raise SystemExit("Destination must be empty; existing model files will not be replaced.")
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(args.model, trust_remote_code=False, device="cpu")
model.save(str(args.destination))
print(f"Embedding model saved to {args.destination.resolve()}")
