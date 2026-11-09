"""Guided mixed-label five-second collection; preserves all older sessions."""
if __package__:
    from .collect_sequence import main as collect_main
else:
    from collect_sequence import main as collect_main


def main(argv=None):
    return collect_main(argv, v2=True)


if __name__ == "__main__":
    raise SystemExit(main())
