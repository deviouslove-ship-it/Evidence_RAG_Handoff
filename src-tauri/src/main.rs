// Release builds use the GUI subsystem so no console window is ever shown.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    evidence_desktop_lib::run();
}
