"""Train five-second sequences without changing legacy three-second models."""
if __package__:
    from . import sequence_model_v2
    from .train_sequence import main as train_main
else:
    import sequence_model_v2
    from train_sequence import main as train_main


def main(argv=None):
    return train_main(argv, backend=sequence_model_v2)


if __name__ == "__main__":
    raise SystemExit(main())
