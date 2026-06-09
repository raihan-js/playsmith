"""Tests for the establishing-shot preview scripts (script generation). No Unreal needed."""

from __future__ import annotations

from playsmith.engines.unreal import render


def test_place_camera_script_frames_the_level() -> None:
    s = render.place_camera_script("/Game/X/Lvl")
    assert "CameraActor" in s and "auto_activate_for_player" in s  # the render captures this camera
    assert "find_look_at_rotation" in s  # aimed at the playfield centre
    assert "PS_PREVIEWCAM" in s and "/Game/X/Lvl" in s
    assert "save_dirty_packages" in s  # persists so the -game render can stream it in
    assert "PLAYSMITH_ASSERT preview_cam" in s


def test_cleanup_camera_script_removes_only_the_preview_cam() -> None:
    s = render.cleanup_camera_script("/Game/X/Lvl")
    assert "PS_PREVIEWCAM" in s and "destroy_actor" in s
    assert "PLAYSMITH_ASSERT preview_cam_removed" in s
