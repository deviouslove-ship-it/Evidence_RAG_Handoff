//! Persisted shell preferences (Orb position, always-on-top). Only window
//! geometry / a boolean preference is stored - never conversation content.

use serde::{Deserialize, Serialize};
use std::path::Path;

pub const CONFIG_FILE_NAME: &str = "shell-state.json";

/// Orb top-left corner in physical pixels of the virtual desktop.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct SavedPoint {
    pub x: i32,
    pub y: i32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct ShellConfig {
    pub orb_position: Option<SavedPoint>,
    /// User preference for the panel window; default OFF.
    pub always_on_top: bool,
}

impl ShellConfig {
    /// Lenient parse: a corrupt or foreign file yields the defaults.
    pub fn from_json_str(text: &str) -> Self {
        serde_json::from_str(text).unwrap_or_default()
    }

    pub fn to_json_string(&self) -> String {
        serde_json::to_string_pretty(self).unwrap_or_else(|_| "{}".to_owned())
    }

    pub fn load(dir: &Path) -> Self {
        std::fs::read_to_string(dir.join(CONFIG_FILE_NAME))
            .map(|text| Self::from_json_str(&text))
            .unwrap_or_default()
    }

    /// Atomic-ish write: temp file in the same directory, then rename.
    pub fn save(&self, dir: &Path) -> std::io::Result<()> {
        std::fs::create_dir_all(dir)?;
        let target = dir.join(CONFIG_FILE_NAME);
        let tmp = dir.join(format!("{CONFIG_FILE_NAME}.tmp"));
        std::fs::write(&tmp, self.to_json_string())?;
        if target.exists() {
            let _ = std::fs::remove_file(&target);
        }
        std::fs::rename(&tmp, &target)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_when_missing_or_corrupt() {
        assert_eq!(ShellConfig::from_json_str(""), ShellConfig::default());
        assert_eq!(ShellConfig::from_json_str("{not json"), ShellConfig::default());
        let cfg = ShellConfig::from_json_str("{}");
        assert!(!cfg.always_on_top);
        assert!(cfg.orb_position.is_none());
    }

    #[test]
    fn roundtrip_with_negative_coordinates() {
        let cfg = ShellConfig {
            orb_position: Some(SavedPoint { x: -1900, y: 320 }),
            always_on_top: true,
        };
        assert_eq!(ShellConfig::from_json_str(&cfg.to_json_string()), cfg);
    }

    #[test]
    fn save_and_load_from_directory() {
        let dir = std::env::temp_dir().join(format!("evidence-shell-test-{}", std::process::id()));
        let cfg = ShellConfig {
            orb_position: Some(SavedPoint { x: 10, y: 20 }),
            always_on_top: false,
        };
        cfg.save(&dir).unwrap();
        cfg.save(&dir).unwrap(); // overwrite path
        assert_eq!(ShellConfig::load(&dir), cfg);
        let _ = std::fs::remove_dir_all(&dir);
        assert_eq!(ShellConfig::load(&dir), ShellConfig::default());
    }
}
