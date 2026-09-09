"""Explicit opt-in download for the optional local reference embedding model."""
import argparse
import re


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', default='sentence-transformers/all-MiniLM-L6-v2')
    p.add_argument('--revision', default='1110a243fdf4706b3f48f1d95db1a4f5529b4d41')
    p.add_argument('--cache-folder', required=True)
    args = p.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.revision):
        p.error('revision must be a pinned commit SHA')
    from huggingface_hub import snapshot_download
    print(snapshot_download(repo_id=args.model, revision=args.revision, cache_dir=args.cache_folder,
        allow_patterns=['*.json', '*.safetensors', 'vocab.txt', '*.model'], token=False))


if __name__ == '__main__':
    main()
