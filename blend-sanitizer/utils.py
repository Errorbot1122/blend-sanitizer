from pathlib import Path
from typing import (
    Literal,
    Sequence,
    Sized,
    Iterable,
    Generator,
    Callable,
    TypeVar,
    TypeVarTuple,
    cast,
)
import shutil
import sys
import os

import bpy
import bpy.types as bpt

from mathutils import Color

T = TypeVar("T")
TT = TypeVarTuple("TT")

Coord2d = tuple[float, float]
CoordInt2d = tuple[int, int]
Color4 = tuple[float, float, float, float]
ColorInt4 = tuple[int, int, int, int]

ADDON_ID_NAME = "blend-sanitizer"
BLENDER_PATH = Path(bpy.utils.resource_path("LOCAL")).resolve().absolute()
DATATYPES_WITH_FILEPATHS = [
    "images",
    "movieclips",
    "sounds",
    "fonts",
    "libraries",
    "texts",
]


class temp_add_global_path:
    def __init__(self, path: Path):
        self.path = str(path.absolute().resolve())

    def __enter__(self):
        sys.path.insert(0, self.path)

    def __exit__(self, _0, _1, _2):
        try:
            sys.path.remove(self.path)
        except ValueError:
            pass


def UNSANITIZEABLE_ID_FUNCTION(id: bpt.ID) -> bool:
    try:
        if id.filepath == "":
            return True
    except KeyError:
        return True

    return id.users == 0


def indexInList(x: Sized, index: int) -> bool:
    return 0 <= index < len(x)


def normalize_path(path: Path) -> Path:
    return Path(os.path.normpath(path))


def get_relative_path(start: Path, path: Path) -> Path:
    return Path(os.path.relpath(str(path), str(start)))


def clamp(x: float, min_x: float, max_x: float) -> float:
    return max(min(x, max_x), min_x)


def color_to_tuple(color: Color, alpha: float = 1.0) -> Color4:
    return (color.r, color.g, color.b, alpha)


def register_classes(classes: Sequence):
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister_classes(classes: Sequence):
    for cls in classes:
        bpy.utils.unregister_class(cls)


def to_color_tuple(color: Iterable[float]) -> Color4:
    color_iter = iter(color)
    r, g, b = next(color_iter), next(color_iter), next(color_iter)

    a = 1
    try:
        a = next(color_iter)
    except StopAsyncIteration:
        pass

    return (r, g, b, a)


def indexWithCallback(
    arr: Iterable[T],
    callback: Callable[[T, int, *TT], bool],
    *callback_args: *TT,
) -> int | None:
    for index, x in enumerate(arr):
        if callback(x, index, *callback_args):
            return index


def alpha_over(bottom: Color4, top: Color4) -> Color4:
    bot_r, bot_g, bot_b, bot_a = bottom
    top_r, top_g, top_b, top_a = top

    out_a = top_a + bot_a * (1 - top_a)
    if out_a == 0.0:
        return (0.0, 0.0, 0.0, 0.0)

    one_minus_top_a = 1 - top_a
    out_r = (top_r * top_a + bot_r * bot_a * one_minus_top_a) / out_a
    out_g = (top_g * top_a + bot_g * bot_a * one_minus_top_a) / out_a
    out_b = (top_b * top_a + bot_b * bot_a * one_minus_top_a) / out_a

    return (out_r, out_g, out_b, out_a)


def concat_list(original: list[T], new: list[T]):
    """Concatenate 2 lists without creating a new one"""

    for item in new:
        original.append(item)


def get_copy_directory(context: bpt.Context):
    preferences = context.preferences.addons[ADDON_ID_NAME].preferences
    assert preferences, "No preferences found..."

    return normalize_path(
        Path(bpy.data.filepath).parent
        / Path(preferences.copy_location.removeprefix("//"))
    )


def get_id_path(
    id: bpt.ID, path_type: Literal["absolute", "relative"] = "absolute"
) -> Path:
    raw_path = ""
    if path_type == "absolute":
        raw_path = bpy.path.abspath(id.filepath)
    if path_type == "relative":
        raw_path = bpy.path.relpath(id.filepath)

    return normalize_path(Path(raw_path.removeprefix("//")))


def iter_ids_in_datatypes(
    id_types: list[str],
) -> Generator[bpt.ID, None, None]:
    for id_type in id_types:
        assert hasattr(bpy.data, id_type), f"'{id_type}' not found in blender data"

        data = getattr(bpy.data, id_type)
        for id in data:
            yield cast(bpt.ID, id)


def should_sanitize_id(id: bpt.ID, copy_directory: Path) -> bool:
    if UNSANITIZEABLE_ID_FUNCTION(id):
        return False

    relative_path = get_id_path(id, "relative")
    if not relative_path.is_file:
        return False

    # Skip if already inside `copy_directory`
    absolute_path = get_id_path(id, "absolute")
    if absolute_path.is_relative_to(copy_directory):
        return False

    copy_relative_path = get_relative_path(copy_directory, absolute_path)
    if ".." not in copy_relative_path.parts:
        return False

    return True


def get_ids_to_sanitize(copy_directory: Path) -> list[bpt.ID]:
    final = []
    for id in iter_ids_in_datatypes(DATATYPES_WITH_FILEPATHS):
        if should_sanitize_id(id, copy_directory):
            final.append(id)

    return final


def fix_id(ids_to_sanitize: Sequence[bpt.ID], copy_directory: Path):
    for id in ids_to_sanitize:
        try:
            data_path = get_id_path(id, "absolute")
        except ValueError as e:
            print("ERROR:", e)
            continue

        try:
            copy_directory.mkdir(parents=True, exist_ok=True)
            new_data_path = Path(shutil.copy2(data_path, copy_directory))

            id["filepath"] = bpy.path.relpath(str(new_data_path.absolute()))
        except shutil.SameFileError:
            pass

        id["sanitizer_moved"] = True
