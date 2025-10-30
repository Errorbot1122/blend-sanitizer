from typing import Container, Iterable, TypeVar, Literal, Generator, Optional, cast
from pathlib import Path
from collections import OrderedDict
import math

if "bpy" in locals():
    import importlib

    importlib.reload(report_popup)  # type: ignore  # noqa: F821
    importlib.reload(utils)  # type: ignore  # noqa: F821
else:
    from . import report_popup
    from . import utils

import bpy
import bpy.types as bpt
from bpy.props import StringProperty, BoolProperty

import blf
import gpu
from gpu_extras.batch import batch_for_shader

T = TypeVar("T")

FlatColorVert = dict[
    Literal["pos", "color"], list[utils.CoordInt2d] | list[utils.Color4]
]
ImageVert = dict[
    Literal["pos", "texCoord"], list[utils.CoordInt2d] | list[utils.CoordInt2d]
]
TriangleIndices = tuple[int, int, int]
VertData = tuple[T, list[TriangleIndices]]

RowDict = dict[
    Literal["text", "is_header", "icon", "moved"], str | bool | Optional[bpt.Image]
]

HEADER_HEIGHT_PIXELS = 25
FILTER_HIDDEN_FUNCTION = lambda x: not x[1]["moved"]

ORIGINAL_VIEW3D_DRAW_HEADER = bpt.VIEW3D_HT_header.draw


row_items: OrderedDict[str, RowDict] = OrderedDict()

ui_font_id = 0

report_view3d_draw_handle = None
report_view3d_space: bpt.SpaceView3D | type[bpt.SpaceView3D] | None = None
report_view3d_area: bpt.Area | None = None

scroll_pixels = 0
mouse_pos = (0, 0)
mouse_left_click = False
mouse_right_click = False
mouse_scroll_amount = 0
pause_input = False

selecting_mode: Literal["selecting", "deselecting"] | None = None
hover_row_index: int | None = None
selected_rows_hashes: set[str] = set()
active_row_hash: str | None = None


def get_id_type_name(id_data: bpy.types.ID) -> str:
    id_type = id_data.id_type

    enum_items = bpy.types.ID.bl_rna.properties["id_type"].enum_items
    return enum_items[id_type].name


def get_blender_font_id(font_type: Literal["regular", "mono"] = "regular") -> int:
    DEFAULT_REGULAR_FONT_FILE = Path("Inter.woff2")
    DEFAULT_MONO_FONT_FILE = Path("DejaVuSansMono.woff2")
    BLENDER_FONTS_PATH = utils.BLENDER_PATH / Path("datafiles", "fonts")

    view_preferences = bpy.context.preferences.view

    font_file = BLENDER_FONTS_PATH / DEFAULT_REGULAR_FONT_FILE
    if font_type == "regular" and view_preferences.font_path_ui:
        font_file = view_preferences.font_path_ui
    elif font_type == "mono" and view_preferences.font_path_ui_mono:
        font_file = view_preferences.font_path_ui_mono
    else:
        if font_type == "mono":
            font_file = BLENDER_FONTS_PATH / DEFAULT_MONO_FONT_FILE

    load_id = blf.load(str(font_file))
    if load_id == -1:
        print(
            f"[WARNING]: COULD NOT LOAD FONT AT {str(font_file)}! Using default font."
        )
        load_id = 0

    return load_id


def convert_pointers_to_ids(pointers: Container[str]) -> list[bpt.ID]:
    final = []
    for id in utils.iter_ids_in_datatypes(utils.DATATYPES_WITH_FILEPATHS):
        if str(id.as_pointer()) in pointers:
            final.append(id)

    return final


def append_verts(verts: T, indices: list[TriangleIndices], verts_new: VertData[T]):
    utils.concat_list(verts["pos"], verts_new[0]["pos"])  # type: ignore
    utils.concat_list(verts["color"], verts_new[0]["color"])  # type: ignore

    utils.concat_list(indices, verts_new[1])


def next_available_index(indices: list[tuple[int, ...]]) -> int:
    greatest_index = -1
    for indexTuple in indices:
        for index in indexTuple:
            if index > greatest_index:
                greatest_index = index

    return greatest_index + 1


def add_rect(
    verts: FlatColorVert,
    indices: list[TriangleIndices],
    x: int,
    y: int,
    width: int,
    height: int,
    color: utils.Color4,
):
    positions: FlatColorVert = {
        "pos": [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        "color": [color] * 4,
    }

    startIndex = next_available_index(indices)
    new_indices: list[TriangleIndices] = [
        (startIndex, startIndex + 1, startIndex + 2),
        (startIndex + 2, startIndex + 3, startIndex),
    ]

    append_verts(verts, indices, (positions, new_indices))


def add_image(
    verts: ImageVert,
    indices: list[TriangleIndices],
    x: int,
    y: int,
    width: int,
    height: int,
):
    positions: ImageVert = {
        "pos": [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        "texCoord": [(0, 0), (1, 0), (1, 1), (0, 1)],
    }

    startIndex = next_available_index(indices)
    new_indices: list[TriangleIndices] = [
        (startIndex, startIndex + 1, startIndex + 2),
        (startIndex + 2, startIndex + 3, startIndex),
    ]

    append_verts(verts, indices, (positions, new_indices))


def parse_ids_to_sanitize(
    ids_to_sanitize: Iterable[bpt.ID],
) -> OrderedDict[str, RowDict]:
    if not ids_to_sanitize:
        return OrderedDict()

    organized: dict[str, list[bpt.ID]] = dict()
    for id_item in ids_to_sanitize:
        id_type = id_item.id_type
        if id_type not in organized:
            organized[id_type] = []

        organized[id_type].append(id_item)

    # TODO: ADD ICONS
    final = OrderedDict()
    for id_type, ids in organized.items():
        header_text = get_id_type_name(ids[0])
        header_hash = (
            header_text  # NOTE: This shouldn't cause hash collisions... right?
        )
        final[header_hash] = {
            "text": get_id_type_name(ids[0]),
            "is_header": True,
            "icon": None,
            "moved": False,
        }

        for id in ids:
            header_hash = str(id.as_pointer())
            final[header_hash] = {
                "text": id.name,
                "is_header": False,
                "icon": None,
                "moved": id["sanitizer_moved"] if "sanitizer_moved" in id else False,
            }

    return final


def get_row_items_list(context: bpt.Context) -> list[tuple[str, RowDict]]:
    wm = context.window_manager
    filter_func = (
        (lambda _: True) if wm.sanitizer_report_show_hidden else FILTER_HIDDEN_FUNCTION
    )

    return list(filter(filter_func, row_items.items()))


def _row_iter(
    workable_height: int, scroll_pixels: float, ROW_HEIGHT_PIXELS: int
) -> Generator[tuple[int, int, int], None, None]:
    DRAW_END_OFFSET = 1

    draw_row_offset = int(scroll_pixels % (ROW_HEIGHT_PIXELS * 2))
    row_index_offset = int((scroll_pixels // (ROW_HEIGHT_PIXELS * 2)) * 2)

    draw_row_count = workable_height // ROW_HEIGHT_PIXELS
    for draw_row_index in range(draw_row_count + 1 + DRAW_END_OFFSET):
        row_index = row_index_offset + draw_row_index

        row_y = (
            (workable_height - ROW_HEIGHT_PIXELS)
            - (draw_row_index * ROW_HEIGHT_PIXELS)
            + draw_row_offset
        )

        yield draw_row_index, row_index, row_y


def view3d_draw_callback():
    global report_view3d_area
    global mouse_scroll_amount

    global scroll_pixels
    global hover_row_index

    TEXT_SIZE = 12
    TEXT_Y_OFFSET = 4
    TEXT_OUTER_OFFSET = 30
    TEXT_INNER_OFFSET = 60

    ROW_HEIGHT_PIXELS = 20

    SCROLL_BAR_WIDTH = 10
    SCROLL_FACTOR = -10

    # Only in the new window
    if not report_view3d_area or bpy.context.area != report_view3d_area:
        return

    row_items_list = get_row_items_list(bpy.context)
    total_rows = len(row_items_list)

    theme = bpy.context.preferences.themes[0]
    outliner_theme = theme.outliner
    ui_theme = theme.user_interface

    area_width = report_view3d_area.width
    area_height = report_view3d_area.height
    workable_height = area_height - HEADER_HEIGHT_PIXELS

    scroll_pixels += mouse_scroll_amount * SCROLL_FACTOR
    mouse_scroll_amount = 0

    content_height = total_rows * ROW_HEIGHT_PIXELS
    max_scroll_pixels = max(0, content_height - workable_height)
    scroll_pixels = utils.clamp(scroll_pixels, 0, max_scroll_pixels)

    scroll_percent = scroll_pixels / (
        max_scroll_pixels if max_scroll_pixels != 0 else 1
    )

    draw_row_offset = int(scroll_pixels % (ROW_HEIGHT_PIXELS * 2))
    draw_row_count = workable_height // ROW_HEIGHT_PIXELS
    hover_row = (
        (workable_height - (mouse_pos[1] - draw_row_offset)) / workable_height
    ) * draw_row_count
    hover_row_index = math.floor(hover_row) if mouse_pos[1] != -1 else None

    ## Render the Background ##
    background_shader = gpu.shader.from_builtin("FLAT_COLOR")
    verts, indices = cast(FlatColorVert, {"pos": [], "color": []}), []

    # Main Background
    background_color = utils.color_to_tuple(outliner_theme.space.back)
    add_rect(verts, indices, 0, 0, area_width, workable_height, background_color)

    # Row Background
    hover_color = (1, 1, 1, 0.09411764705)
    alternate_color = utils.alpha_over(
        background_color, utils.to_color_tuple(outliner_theme.row_alternate)
    )
    selected_color = utils.color_to_tuple(outliner_theme.selected_highlight)
    active_color = (
        utils.color_to_tuple(outliner_theme.active)
        if outliner_theme.active is not None
        else (0.2, 0.3, 0.5, 1)
    )

    for draw_row_index, row_index, row_y in _row_iter(
        workable_height, scroll_pixels, ROW_HEIGHT_PIXELS
    ):
        row_color = alternate_color if draw_row_index % 2 == 0 else background_color
        if utils.indexInList(row_items_list, row_index):
            row_item_hash, row_item = row_items_list[row_index]
            if mouse_pos[1] != -1 and math.floor(hover_row) == draw_row_index:
                row_color = utils.alpha_over(row_color, hover_color)

            if row_item_hash in selected_rows_hashes:
                row_color = utils.alpha_over(row_color, selected_color)

            if row_item_hash == active_row_hash:
                row_color = utils.alpha_over(row_color, active_color)

        add_rect(verts, indices, 0, row_y, area_width, ROW_HEIGHT_PIXELS, row_color)

    # TODO: Make intractable (Make as similar to blender as possible)
    # TODO: Round Edges (using ui_theme.wcol_scroll.roundness)
    # Scrollbar
    scroll_bar_height = min(
        (workable_height / (content_height if content_height != 0 else 1))
        * workable_height,
        workable_height,
    )
    scroll_bar_scroll_length = workable_height - scroll_bar_height
    add_rect(
        verts,
        indices,
        area_width - SCROLL_BAR_WIDTH,
        int(scroll_bar_scroll_length) - int(scroll_percent * scroll_bar_scroll_length),
        SCROLL_BAR_WIDTH,
        int(scroll_bar_height),
        utils.to_color_tuple(ui_theme.wcol_scroll.item),
    )

    batch = batch_for_shader(background_shader, "TRIS", verts, indices=indices)
    background_shader.bind()
    batch.draw(background_shader)

    # RENDER THE TEXT & ICONS ##
    icon_shader = gpu.shader.from_builtin("IMAGE")
    verts, indices = cast(FlatColorVert, {"pos": [], "texCoord": []}), []

    normal_text_color = utils.color_to_tuple(outliner_theme.space.text)
    hidden_text_color = utils.alpha_over(
        normal_text_color,
        (background_color[0], background_color[1], background_color[2], 0.3),
    )
    blf.size(ui_font_id, TEXT_SIZE)

    # FIXME: Turn this "iter" into a function for DRY? maybe
    for draw_row_index, row_index, row_y in _row_iter(
        workable_height, scroll_pixels, ROW_HEIGHT_PIXELS
    ):
        if not utils.indexInList(row_items_list, row_index):
            continue

        _, row_item = row_items_list[row_index]

        text_color = (
            hidden_text_color
            if not (
                FILTER_HIDDEN_FUNCTION(row_items_list[row_index])
                or row_item["is_header"]
            )
            else normal_text_color
        )
        blf.color(ui_font_id, *text_color)
        blf.position(
            ui_font_id,
            (TEXT_OUTER_OFFSET if bool(row_item["is_header"]) else TEXT_INNER_OFFSET),
            row_y + TEXT_Y_OFFSET,
            0,
        )
        blf.draw(ui_font_id, str(row_item["text"]))

    batch = batch_for_shader(icon_shader, "TRIS", verts, indices=indices)
    icon_shader.bind()
    batch.draw(icon_shader)

    ## Render Overlays ##
    overlay_shader = gpu.shader.from_builtin("FLAT_COLOR")
    verts, indices = cast(FlatColorVert, {"pos": [], "color": []}), []

    # Header "Cover"
    add_rect(
        verts,
        indices,
        0,
        workable_height,
        area_width,
        HEADER_HEIGHT_PIXELS,
        utils.to_color_tuple(outliner_theme.space.header),
    )

    batch = batch_for_shader(overlay_shader, "TRIS", verts, indices=indices)
    overlay_shader.bind()
    batch.draw(overlay_shader)

    # blf.size(0, 20)
    # blf.position(0, 50, 50, 0)
    # blf.draw(0 {len(row_items_list)}")f"{wm.sanitizer_report_show_hidden}, ,
    # blf.draw(0, f"{str(mouse_pos)}, {hover_row}, {draw_row_offset}")


def detect_datablocks_changes(*_):
    global row_items
    row_items = parse_ids_to_sanitize(
        filter(
            lambda x: not utils.UNSANITIZEABLE_ID_FUNCTION(x),
            utils.iter_ids_in_datatypes(utils.DATATYPES_WITH_FILEPATHS),
        )
    )


def draw_header(self, context: bpt.Context):
    """READ TO TEST IF ORIGINAL FUNCTION INCORRECT"""
    wm = context.window_manager

    layout = cast(bpt.UILayout, self.layout)

    # Only draw on new window
    if context.area != report_view3d_area:
        assert not ORIGINAL_VIEW3D_DRAW_HEADER.__doc__, "Got Incorrect Original Header!"
        ORIGINAL_VIEW3D_DRAW_HEADER(self, context)  # type: ignore
        return

    # TODO: Add custom header
    layout.label(text='Review "Dirty" Datablocks')

    layout.separator_spacer()

    row = layout.row(align=True)
    row.prop(wm, "sanitizer_report_show_hidden")

    row = layout.row(align=True)
    row.operator("view3d.sanitizer_report_delete", icon="X")
    row.operator("view3d.sanitizer_report_fix", icon="COPYDOWN")
    row.separator(factor=0.1)


class WM_OT_sanitizer_report_fix_choose_folder(bpy.types.Operator):
    bl_idname = "wm.sanitizer_report_choose_folder"
    bl_label = "Choose a Folder"

    directory: StringProperty(name="Folder Path", subtype="DIR_PATH")

    def execute(self, _):
        global pause_input

        global selecting_mode
        global hover_row_index
        global selected_rows_hashes
        global active_row_hash

        chosen_directory = Path(bpy.path.abspath(self.directory))

        selected_ids = convert_pointers_to_ids(selected_rows_hashes)
        assert len(selected_ids) > 0, "selected_ids is empty!"

        utils.fix_id(selected_ids, copy_directory=chosen_directory)

        detect_datablocks_changes()

        selecting_mode = None
        hover_row_index = None
        selected_rows_hashes = set()
        active_row_hash = None
        pause_input = False
        return {"FINISHED"}

    def invoke(self, context, _):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class VIEW3D_OT_sanitizer_report_mouse_interact(bpt.Operator):
    bl_idname = "view3d.sanitizer_report_mouse_interact"
    bl_label = "sanitizer_report_mouse_interact"

    # NOTE: Maybe use PointerProperty?
    invoke_area: StringProperty(name="Invoke Area Pointer", default="")

    def modal(self, context: bpt.Context, event: bpt.Event):
        global mouse_pos
        global mouse_left_click
        global mouse_right_click
        global mouse_scroll_amount
        global pause_input

        global selecting_mode
        global selected_rows_hashes
        global active_row_hash

        # Check if area still exists
        invoke_area: bpt.Area | None = None
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if str(area.as_pointer()) == self.invoke_area:
                    invoke_area = area
                    break

        if not invoke_area:
            return {"CANCELLED"}

        if pause_input:
            return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE":
            if (event.mouse_x > 0 and event.mouse_y > 0) and (
                event.mouse_x < invoke_area.width and event.mouse_y < invoke_area.height
            ):
                mouse_pos = (event.mouse_x, event.mouse_y)
            else:
                mouse_pos = (-1, -1)
        elif event.type == "WHEELUPMOUSE":
            mouse_scroll_amount += 1
        elif event.type == "WHEELDOWNMOUSE":
            mouse_scroll_amount -= 1
        elif event.type == "LEFTMOUSE":
            mouse_left_click = event.value == "PRESS"
        elif event.type == "RIGHTMOUSE":
            mouse_right_click = event.value == "PRESS"
        else:  # Return early on unknown event
            return {"PASS_THROUGH"}

        # Pass to blender when on header area
        if event.mouse_y > invoke_area.height - HEADER_HEIGHT_PIXELS:
            return {"PASS_THROUGH"}

        selecting_type: Literal["single", "individual", "group"] | None = None
        if mouse_left_click:
            selecting_type = "single"
            if event.ctrl:
                selecting_type = "individual"
            elif event.shift:
                selecting_type = "group"

        # Force update menu
        invoke_area.tag_redraw()

        # HANDLE INTERACTIONS
        row_items_list = get_row_items_list(bpy.context)
        if not (hover_row_index and utils.indexInList(row_items_list, hover_row_index)):
            return {"RUNNING_MODAL"}

        hover_row_hash, hover_row_item = row_items_list[hover_row_index]
        if not hover_row_item["is_header"]:
            if selecting_type == "single":
                active_row_hash = hover_row_hash
                selected_rows_hashes = set([active_row_hash])
            elif (
                selecting_type == "individual"
            ):  # FIXME: Fix bug where this runs twice, causing 2-frame deletion
                if hover_row_hash == active_row_hash:
                    active_row_hash = None
                    selected_rows_hashes.remove(hover_row_hash)
                else:
                    active_row_hash = hover_row_hash
                    selected_rows_hashes.add(hover_row_hash)

            elif selecting_type == "group":
                if active_row_hash:
                    active_row_index = utils.indexWithCallback(
                        row_items_list, lambda x, _: x[0] == active_row_hash
                    )
                    assert (
                        active_row_index is not None
                    ), "active_row_hash could not be found!"

                    max_selected_row_index = max(active_row_index, hover_row_index)
                    min_selected_row_index = min(active_row_index, hover_row_index)

                    selected_rows_hashes = set()
                    for row_item_hash, row_item in row_items_list[
                        min_selected_row_index : max_selected_row_index + 1
                    ]:
                        if row_item["is_header"]:
                            continue

                        selected_rows_hashes.add(row_item_hash)

                else:
                    active_row_hash = hover_row_hash
                    selected_rows_hashes = set(hover_row_hash)

        return {"RUNNING_MODAL"}

    def invoke(self, context: bpt.Context, _):
        global mouse_scroll_amount
        mouse_scroll_amount = 0

        if self.invoke_area == "":
            self.invoke_area = str(context.area.as_pointer())

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}


class VIEW3D_OT_sanitizer_report_fix(bpt.Operator):
    bl_idname = "view3d.sanitizer_report_fix"
    bl_label = "Fix"

    @classmethod
    def poll(cls, _) -> bool:
        return len(selected_rows_hashes) > 0

    def execute(self, _):
        global pause_input

        bpy.ops.file.make_paths_relative()

        pause_input = True
        bpy.ops.wm.sanitizer_report_choose_folder("INVOKE_DEFAULT")
        return {"FINISHED"}


class VIEW3D_OT_sanitizer_report_delete(bpt.Operator):
    bl_idname = "view3d.sanitizer_report_delete"
    bl_label = "Delete"

    @classmethod
    def poll(cls, _) -> bool:
        return len(selected_rows_hashes) > 0

    def execute(self, _):
        global selected_rows_hashes
        global active_row_hash

        selected_ids = convert_pointers_to_ids(selected_rows_hashes)
        assert len(selected_ids) > 0, "selected_ids is empty!"

        for id in selected_ids:
            datatype = id.id_type.lower() + "s"
            getattr(bpy.data, datatype).remove(id)

        selected_rows_hashes = set()
        active_row_hash = None

        detect_datablocks_changes()

        return {"FINISHED"}


def register_draw(
    view_3d_space: bpt.SpaceView3D | type[bpt.SpaceView3D],
    parent_area: bpt.Area,
):
    global ORIGINAL_VIEW3D_DRAW_HEADER

    global report_view3d_area
    global report_view3d_space
    global report_view3d_draw_handle

    if report_view3d_space is not None:
        unregister_draw()

    detect_datablocks_changes()

    report_view3d_area = parent_area
    report_view3d_space = view_3d_space
    report_view3d_draw_handle = bpt.SpaceView3D.draw_handler_add(
        view3d_draw_callback, (), "WINDOW", "POST_PIXEL"
    )

    ORIGINAL_VIEW3D_DRAW_HEADER = bpt.VIEW3D_HT_header.draw
    bpt.VIEW3D_HT_header.draw = draw_header

    bpy.ops.view3d.sanitizer_report_mouse_interact(
        "INVOKE_DEFAULT", invoke_area=str(parent_area.as_pointer())
    )

    print("Draw handler added!")


def unregister_draw():
    global report_view3d_area
    global report_view3d_space
    global report_view3d_draw_handle

    global scroll_pixels
    global mouse_pos
    global mouse_left_click
    global mouse_right_click
    global mouse_scroll_amount
    global pause_input

    global selecting_mode
    global hover_row_index
    global selected_rows_hashes
    global active_row_hash

    bpt.VIEW3D_HT_header.draw = ORIGINAL_VIEW3D_DRAW_HEADER

    if (report_view3d_space is not None) and (report_view3d_draw_handle is not None):
        bpt.SpaceView3D.draw_handler_remove(report_view3d_draw_handle, "WINDOW")

        report_view3d_draw_handle = None
        report_view3d_space = None
        report_view3d_area = None

        scroll_pixels = 0
        mouse_pos = (0, 0)
        mouse_left_click = False
        mouse_right_click = False
        mouse_scroll_amount = 0
        pause_input = False

        selecting_mode = None
        hover_row_index = None
        selected_rows_hashes = set()
        active_row_hash = None

        print("Draw handler removed!")


classes = (
    WM_OT_sanitizer_report_fix_choose_folder,
    VIEW3D_OT_sanitizer_report_mouse_interact,
    VIEW3D_OT_sanitizer_report_delete,
    VIEW3D_OT_sanitizer_report_fix,
)


def register():
    global ui_font_id

    utils.register_classes(classes)

    bpy.app.handlers.depsgraph_update_post.append(detect_datablocks_changes)

    ui_font_id = get_blender_font_id()

    bpt.WindowManager.sanitizer_report_show_hidden = BoolProperty(
        name="Show Hidden", description="Show all hidden IDs", default=False
    )


def unregister():
    try:
        bpy.app.handlers.depsgraph_update_post.remove(detect_datablocks_changes)
    except ValueError:
        pass

    utils.unregister_classes(classes)
    unregister_draw()
