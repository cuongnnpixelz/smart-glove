"""Train a separate model using all five flex sensors and MPU features."""
if __package__:
    from . import sequence_model_5
    from .train_sequence import main as train_main
else:
    import sequence_model_5
    from train_sequence import main as train_main


def main(argv=None):
    return train_main(argv, backend=sequence_model_5)


if __name__ == "__main__":
    raise SystemExit(main())
