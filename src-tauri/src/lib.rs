pub mod geometry;
pub mod shell_config;

use geometry::{
    best_area_index, clamp_into, panel_rect_next_to_orb, to_physical, Rect,
};
use shell_config::ShellConfig;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, PhysicalPosition, PhysicalSize, Position, Size, WebviewWindow, WindowEvent,
};

const ORB_COLLAPSED_SIZE: f64 = 84.0;
const ORB_EXPANDED_WIDTH: f64 = 420.0;
const ORB_EXPANDED_HEIGHT: f64 = 580.0;
const ORB_BOTTOM_RIGHT_MARGIN: f64 = 16.0;

pub struct ShellState {
    pub session_active: AtomicBool,
    pub orb_expanded: AtomicBool,
}

impl Default for ShellState {
    fn default() -> Self {
        Self {
            session_active: AtomicBool::new(false),
            orb_expanded: AtomicBool::new(false),
        }
    }
}

fn config_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok()
}

fn monitor_work_areas(window: &WebviewWindow) -> Vec<(Rect, f64)> {
    let Ok(monitors) = window.available_monitors() else {
        return Vec::new();
    };
    monitors
        .into_iter()
        .map(|m| {
            let pos = m.position();
            let size = m.size();
            let taskbar_pad = (48.0 * m.scale_factor()).round() as u32;
            let usable_h = size.height.saturating_sub(taskbar_pad).max(320);
            (
                Rect::new(pos.x, pos.y, size.width, usable_h),
                m.scale_factor(),
            )
        })
        .collect()
}

fn window_rect(window: &WebviewWindow) -> Option<Rect> {
    let pos = window.outer_position().ok()?;
    let size = window.outer_size().ok()?;
    Some(Rect::new(pos.x, pos.y, size.width, size.height))
}

fn apply_orb_placement_sized(app: &tauri::AppHandle, logical_w: f64, logical_h: f64) {
    let Some(orb) = app.get_webview_window("orb") else {
        return;
    };
    let reference = app.get_webview_window("main").unwrap_or_else(|| orb.clone());
    let monitors = monitor_work_areas(&reference);
    if monitors.is_empty() {
        return;
    }
    let (area, scale) = monitors[0];
    let w = to_physical(logical_w, scale);
    let h = to_physical(logical_h, scale);
    let margin = to_physical(ORB_BOTTOM_RIGHT_MARGIN, scale) as i32;
    let x = (area.x + area.w as i32) - (w as i32) - margin;
    let y = (area.y + area.h as i32) - (h as i32) - margin;
    let target = clamp_into(Rect::new(x, y, w, h), &area);

    let _ = orb.set_size(Size::Physical(PhysicalSize::new(target.w, target.h)));
    let _ = orb.set_position(Position::Physical(PhysicalPosition::new(target.x, target.y)));
    let _ = orb.set_always_on_top(true);
}

fn apply_orb_placement(app: &tauri::AppHandle) {
    let expanded = app
        .try_state::<ShellState>()
        .map(|s| s.orb_expanded.load(Ordering::SeqCst))
        .unwrap_or(false);
    if expanded {
        apply_orb_placement_sized(app, ORB_EXPANDED_WIDTH, ORB_EXPANDED_HEIGHT);
    } else {
        apply_orb_placement_sized(app, ORB_COLLAPSED_SIZE, ORB_COLLAPSED_SIZE);
    }
}

fn place_panel_near_orb(app: &tauri::AppHandle) {
    let (Some(main), Some(orb)) = (
        app.get_webview_window("main"),
        app.get_webview_window("orb"),
    ) else {
        return;
    };
    let monitors = monitor_work_areas(&main);
    if monitors.is_empty() {
        return;
    }
    let areas: Vec<Rect> = monitors.iter().map(|(r, _)| *r).collect();
    let Some(orb_rect) = window_rect(&orb) else {
        return;
    };
    let idx = best_area_index(&orb_rect, &areas).unwrap_or(0);
    let (area, scale) = monitors[idx];
    let panel_size = main
        .outer_size()
        .unwrap_or_else(|_| PhysicalSize::new(to_physical(1180.0, scale), to_physical(780.0, scale)));
    let target = panel_rect_next_to_orb(
        &orb_rect,
        panel_size.width,
        panel_size.height,
        &area,
        scale,
    );
    let _ = main.set_position(Position::Physical(PhysicalPosition::new(target.x, target.y)));
}

#[tauri::command]
fn set_orb_expanded(
    app: tauri::AppHandle,
    state: tauri::State<'_, ShellState>,
    expanded: bool,
) -> Result<(), String> {
    if !state.session_active.load(Ordering::SeqCst) {
        return Err("SESSION_REQUIRED".to_owned());
    }
    state.orb_expanded.store(expanded, Ordering::SeqCst);
    apply_orb_placement(&app);
    if let Some(orb) = app.get_webview_window("orb") {
        let _ = orb.show();
        if expanded {
            let _ = orb.set_focus();
        }
    }
    Ok(())
}

#[tauri::command]
fn open_workspace_from_orb(
    app: tauri::AppHandle,
    state: tauri::State<'_, ShellState>,
    payload: serde_json::Value,
) -> Result<(), String> {
    if !state.session_active.load(Ordering::SeqCst) {
        return Err("SESSION_REQUIRED".to_owned());
    }
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.show();
        let _ = main.set_focus();
        let _ = app.emit_to("main", "evidence-sync-from-orb", payload);
    }
    Ok(())
}

#[tauri::command]
fn session_started(app: tauri::AppHandle, state: tauri::State<'_, ShellState>) {
    state.session_active.store(true, Ordering::SeqCst);
    apply_orb_placement(&app);
    if let Some(orb) = app.get_webview_window("orb") {
        let _ = orb.show();
    }
    if let Some(main) = app.get_webview_window("main") {
        if let Some(dir) = config_dir(&app) {
            let cfg = ShellConfig::load(&dir);
            let _ = main.set_always_on_top(cfg.always_on_top);
        }
    }
}

#[tauri::command]
fn session_ended(app: tauri::AppHandle, state: tauri::State<'_, ShellState>) {
    state.session_active.store(false, Ordering::SeqCst);
    state.orb_expanded.store(false, Ordering::SeqCst);
    let _ = app.emit_to("orb", "evidence-logout-requested", ());
    apply_orb_placement(&app);
    if let Some(orb) = app.get_webview_window("orb") {
        let _ = orb.hide();
    }
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.set_always_on_top(false);
        let _ = main.show();
        let _ = main.set_focus();
    }
}

#[tauri::command]
fn session_active(state: tauri::State<'_, ShellState>) -> bool {
    state.session_active.load(Ordering::SeqCst)
}

#[tauri::command]
fn toggle_panel(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            place_panel_near_orb(&app);
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

#[tauri::command]
fn set_always_on_top(app: tauri::AppHandle, always_on_top: bool) {
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.set_always_on_top(always_on_top);
    }
    if let Some(dir) = config_dir(&app) {
        let mut cfg = ShellConfig::load(&dir);
        cfg.always_on_top = always_on_top;
        let _ = cfg.save(&dir);
    }
}

pub fn run() {
    tauri::Builder::default()
        .manage(ShellState::default())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            apply_orb_placement(app);
            let session_active = app
                .state::<ShellState>()
                .session_active
                .load(Ordering::SeqCst);
            if session_active {
                if let Some(orb) = app.get_webview_window("orb") {
                    let _ = orb.show();
                }
            }
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .invoke_handler(tauri::generate_handler![
            set_orb_expanded,
            open_workspace_from_orb,
            session_started,
            session_ended,
            session_active,
            toggle_panel,
            set_always_on_top
        ])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                    apply_orb_placement(&window.app_handle());
                    let active = window
                        .app_handle()
                        .state::<ShellState>()
                        .session_active
                        .load(Ordering::SeqCst);
                    if active {
                        if let Some(orb) = window.app_handle().get_webview_window("orb") {
                            let _ = orb.show();
                        }
                    }
                } else if window.label() == "orb" {
                    api.prevent_close();
                    let active = window
                        .app_handle()
                        .state::<ShellState>()
                        .session_active
                        .load(Ordering::SeqCst);
                    if active {
                        let _ = window.show();
                    } else {
                        let _ = window.hide();
                    }
                }
            }
        })
        .setup(|app| {
            apply_orb_placement(&app.handle());
            if let Some(orb) = app.get_webview_window("orb") {
                let _ = orb.hide();
            }
            let show = MenuItem::with_id(app, "show", "Mở/Thu trợ lý", true, None::<&str>)?;
            let logout = MenuItem::with_id(app, "logout", "Đăng xuất", true, None::<&str>)?;
            let exit = MenuItem::with_id(app, "exit", "Thoát", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &logout, &exit])?;
            let mut tray_builder = TrayIconBuilder::with_id("evidence-tray").menu(&menu);
            if let Some(icon) = app.default_window_icon().cloned() {
                tray_builder = tray_builder.icon(icon);
            }
            tray_builder
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_panel(tray.app_handle().clone());
                    }
                })
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => toggle_panel(app.clone()),
                    "logout" => {
                        let state = app.state::<ShellState>();
                        state.session_active.store(false, Ordering::SeqCst);
                        state.orb_expanded.store(false, Ordering::SeqCst);
                        let _ = app.emit_to("orb", "evidence-logout-requested", ());
                        apply_orb_placement(&app);
                        if let Some(orb) = app.get_webview_window("orb") {
                            let _ = orb.hide();
                        }
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = app.emit_to("main", "evidence-logout-requested", ());
                            let _ = window.eval(
                                "window.dispatchEvent(new CustomEvent('evidence:logout'))",
                            );
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "exit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Evidence RAG desktop shell");
}
