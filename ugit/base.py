import os
import itertools
import operator
from collections import namedtuple

from . import data


def write_tree(directory="."):
    entries = []
    with os.scandir(directory) as it:
        for entry in it:
            fullPath = f"{directory}/{entry.name}"

            oid = 0
            type_ = "blob"
            if is_ignored(fullPath):
                continue

            if entry.is_file(follow_symlinks=False):
                type_ = "blob"
                with open(entry.path, "rb") as f:
                    oid = data.hash_objects(f.read(), type_)

            elif entry.is_dir(follow_symlinks=False):
                type_ = "tree"
                oid = write_tree(fullPath)

            entries.append((entry.name, oid, type_))

    tree = "".join(f"{type_} {oid} {name}\n" for name, oid, type_ in entries)

    return data.hash_objects(tree.encode(), "tree")


def is_ignored(path) -> bool:
    return ".ugit" in path.split("/") or ".git" in path.split("/")


def commit(message) -> str:
    commit = f"tree {write_tree()}\n"

    HEAD = data.get_HEAD()
    if HEAD:
        commit += f"parent {HEAD}\n"

    commit += "\n"
    commit += f"message {message}\n"

    oid = data.hash_objects(commit.encode(), type_="commit")

    data.set_HEAD(oid)

    return oid


Commit = namedtuple("Commit", ["tree", "parent", "message"])


def get_commit(oid):
    parent = None
    tree = None
    commit = data.get_object(oid, "commit").decode()

    lines = iter(commit.splitlines())

    for line in itertools.takewhile(operator.truth, lines):
        key, value = line.split(" ", 1)
        if key == "tree":
            tree = value

        elif key == "parent":
            parent = value

        else:
            assert False, f"unknown field {key}"

    message = "\n".join(lines)
    return Commit(tree=tree, parent=parent, message=message)


def _iter_tree_entries(oid):
    if not oid:
        return
    tree = data.get_object(oid, "tree")
    for entry in tree.decode().splitlines():
        type_, oid, name = entry.split(" ", 2)
        yield type_, oid, name


def get_tree(oid, base_path=""):
    result = {}
    for type_, oid, name in _iter_tree_entries(oid):
        assert "/" not in name
        assert name not in ("..", ".")
        path = base_path + name
        if type_ == "blob":
            result[path] = oid
        elif type_ == "tree":
            result.update(get_tree(oid, f"{path}/"))
        else:
            assert False, f"Unknown tree entry {type_}"
    return result


def read_tree(tree_oid):
    _empty_current_directory()
    for path, oid in get_tree(tree_oid, base_path="./").items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data.get_object(oid))


def _empty_current_directory():
    for root, dirnames, filenames in os.walk(".", topdown=False):
        for filename in filenames:
            path = os.path.realpath(f"{root}/{filename}")
            if is_ignored(path) or not os.path.isfile(path):
                continue
            os.remove(path)

        for dirname in dirnames:
            path = os.path.relpath(f"{root}/{dirname}")
            if is_ignored(path):
                continue
            try:
                os.rmdir(path)
            except (FileNotFoundError, OSError):
                pass
