import os


def is_safe_path(path, allowed_dir):
    # strip trailing slash so both "/dir" and "/dir/" work correctly
    allowed_dir = allowed_dir.rstrip("/")
    # realpath resolves symlinks and .. traversal before comparing,
    # preventing attacks like /safe/dir/../../../etc/passwd
    return os.path.realpath(path).startswith(os.path.realpath(allowed_dir))
