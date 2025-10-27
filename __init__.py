bl_info = {
    "name": "Blend Sanitizer",
    "author": "Errorbot1122",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "File > External Data",
    "description": (
        'A tool for reporting and "fixing" hidden data (file paths) that may reveal'
        " sensitive information"
    ),
    "category": "System",
}

from pathlib import Path
from typing import cast

if "bpy" in locals():
    import importlib

    importlib.reload(report_popup)  # type: ignore  # noqa: F821
    importlib.reload(utils)  # type: ignore  # noqa: F821
else:
    from . import report_popup
    from . import utils

import bpy
import bpy.types as bpt
from bpy.props import (
    StringProperty,
)

COPY_LOCATION_DEFAULT = "//assets"


def show_message(message: str, /, context=bpy.context, title="Info", icon="INFO"):
    def draw(self, _):
        self.layout.label(text=message)

    context.window_manager.popup_menu(draw, title=title, icon=icon)


def get_copy_location(self) -> str:
    if not self.get("copy_location"):
        return COPY_LOCATION_DEFAULT

    return self["copy_location"]


def set_copy_location(self, value: str):
    if value.startswith("//"):
        self["copy_location"] = value
    elif value.startswith("./"):
        self["copy_location"] = "//" + value[2:]
    elif value.startswith("/") or value[1:].startswith(":\\"):  # Handle Home Dirs
        self["copy_location"] = bpy.path.relpath(value)
    else:
        self["copy_location"] = "//" + value


def external_data_menu_draw(self, _):
    layout: bpt.UILayout = self.layout

    layout.separator()
    layout.operator("file.sanitizer_execute", icon="COPYDOWN")
    layout.operator("file.sanitizer_report", icon="ZOOM_ALL")


class BlendSanitizerAddonPreferences(bpt.AddonPreferences):
    bl_idname = utils.ADDON_ID_NAME

    # TODO: Add to scene so it can grab it per file when loading
    copy_location: StringProperty(
        name="Copy Path",
        default="./assets",
        description=(
            "The path (relative to the blend file) to automatically copy outside"
            " external files to"
        ),
        subtype="DIR_PATH",
        # options={"PATH_SUPPORTS_BLEND_RELATIVE"}, # TODO: Add when update a latest blender version
        get=get_copy_location,
        set=set_copy_location,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = True
        layout.use_property_split = True

        layout.prop(self, "copy_location")


class FILE_OT_sanitizer_execute(bpt.Operator):
    bl_idname = "file.sanitizer_execute"
    bl_label = "Sanitize File"
    bl_description = "Sanitize most possible personally identifiable information"

    @classmethod
    def poll(cls, _) -> bool:
        return bool(bpy.data.filepath)  # File must be saved

    def execute(self, context):
        bpy.ops.file.make_paths_relative()

        preferences = cast(
            BlendSanitizerAddonPreferences,
            context.preferences.addons[utils.ADDON_ID_NAME].preferences,
        )
        assert preferences, "No preferences found..."

        copy_directory = utils.get_copy_directory(context)
        ids_to_sanitize = utils.get_ids_to_sanitize(copy_directory)
        if len(ids_to_sanitize) == 0:
            show_message("Your blend file is already clean! :)", context=context)
            return {"CANCELLED"}

        utils.fix_id(ids_to_sanitize, copy_directory)

        show_message(
            f"Sanitizer was able to move {len(ids_to_sanitize)} file(s) to"
            f' "{preferences.copy_location}".',
            context=context,
        )

        return {"FINISHED"}


class FILE_OT_sanitizer_report(bpt.Operator):
    bl_idname = "file.sanitizer_report"
    bl_label = "Manage Sanitize-able Data"
    bl_description = (
        "Display's datablocks with possible personally identifiable information"
    )

    def execute(self, context):
        ids_to_sanitize = utils.get_ids_to_sanitize(utils.get_copy_directory(context))
        if len(ids_to_sanitize) == 0:
            show_message(
                "No files to report. Your blend file is already clean! :)",
                context=context,
            )
            return {"CANCELLED"}

        # Show popup
        # TODO: Spawn window at smaller size! (Maybe Use: https://github.com/schroef/Custom-Preferences-Size/blob/master/__init__.py)
        bpy.ops.wm.window_new()
        new_window = bpy.context.window_manager.windows[-1]
        assert len(new_window.screen.areas) == 1, "Invalid new window!"

        window_area = new_window.screen.areas[0]
        window_area.type = "VIEW_3D"

        window_space = window_area.spaces[0]
        assert isinstance(
            window_space, bpt.SpaceView3D
        ), "Failed to change new window to outline"

        report_popup.register_draw(window_space, window_area)

        return {"FINISHED"}


classes = (
    BlendSanitizerAddonPreferences,
    FILE_OT_sanitizer_execute,
    FILE_OT_sanitizer_report,
)


def register():
    utils.register_classes(classes)

    bpy.types.TOPBAR_MT_file_external_data.append(external_data_menu_draw)
    report_popup.register()


def unregister():
    report_popup.unregister()
    bpy.types.TOPBAR_MT_file_external_data.remove(external_data_menu_draw)

    utils.unregister_classes(classes)
