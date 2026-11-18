if __package__:
    from . import phrase_model
    from .train_sequence import main as train
else:
    import phrase_model
    from train_sequence import main as train

if __name__ == '__main__':
    raise SystemExit(train(backend=phrase_model))
