"""Default training entry point for the calibrated, session-grouped v2 dataset.

The former script is preserved in train_legacy.py for explicit legacy experiments.
"""
if __package__:
    from .train_v2 import main
else:
    from train_v2 import main

if __name__ == "__main__":
    raise SystemExit(main())
