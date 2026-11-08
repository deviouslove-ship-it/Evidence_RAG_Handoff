//! Pure geometry helpers (physical pixels) for placing the Orb and the panel.
//!
//! Everything here is free of Tauri types so it can be unit-tested headlessly,
//! including monitors with negative coordinates and several DPI scale factors.

/// Axis-aligned rectangle in physical pixels. `x`/`y` may be negative (monitor
/// left of / above the primary one).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: u32,
    pub h: u32,
}

impl Rect {
    pub const fn new(x: i32, y: i32, w: u32, h: u32) -> Self {
        Self { x, y, w, h }
    }

    fn right(&self) -> i64 {
        self.x as i64 + self.w as i64
    }

    fn bottom(&self) -> i64 {
        self.y as i64 + self.h as i64
    }

    fn center(&self) -> (i64, i64) {
        (
            self.x as i64 + (self.w as i64) / 2,
            self.y as i64 + (self.h as i64) / 2,
        )
    }
}

/// Distance from the Orb to the right edge of the work area (logical px).
pub const ORB_EDGE_MARGIN_LOGICAL: f64 = 12.0;
/// Gap between Orb and panel (logical px).
pub const PANEL_GAP_LOGICAL: f64 = 8.0;
/// Default vertical anchor of the Orb centre in the work area (percent).
pub const ORB_VERTICAL_PERCENT: i64 = 40;

/// Convert logical to physical pixels with a monitor scale factor.
pub fn to_physical(logical: f64, scale: f64) -> u32 {
    let scale = if scale.is_finite() && scale > 0.0 { scale } else { 1.0 };
    (logical * scale).round().max(1.0) as u32
}

fn intersection_area(a: &Rect, b: &Rect) -> i64 {
    let w = a.right().min(b.right()) - (a.x as i64).max(b.x as i64);
    let h = a.bottom().min(b.bottom()) - (a.y as i64).max(b.y as i64);
    if w > 0 && h > 0 {
        w * h
    } else {
        0
    }
}

/// Index of the work area that best matches `rect`: the one with the largest
/// overlap, or - if the rectangle lies on no attached monitor (e.g. the monitor
/// was unplugged) - the one whose centre is nearest. `None` when no monitors.
pub fn best_area_index(rect: &Rect, areas: &[Rect]) -> Option<usize> {
    let mut best: Option<(usize, i64)> = None;
    for (i, area) in areas.iter().enumerate() {
        let overlap = intersection_area(rect, area);
        if overlap > 0 && best.map_or(true, |(_, b)| overlap > b) {
            best = Some((i, overlap));
        }
    }
    if let Some((i, _)) = best {
        return Some(i);
    }
    let (cx, cy) = rect.center();
    areas
        .iter()
        .enumerate()
        .min_by_key(|(_, a)| {
            let (ax, ay) = a.center();
            let (dx, dy) = (ax - cx, ay - cy);
            dx * dx + dy * dy
        })
        .map(|(i, _)| i)
}

/// Move (and if necessary shrink) `rect` so it is fully inside `area`.
pub fn clamp_into(rect: Rect, area: &Rect) -> Rect {
    let w = rect.w.min(area.w);
    let h = rect.h.min(area.h);
    let max_x = area.right() - w as i64;
    let max_y = area.bottom() - h as i64;
    let x = (rect.x as i64).clamp(area.x as i64, max_x.max(area.x as i64));
    let y = (rect.y as i64).clamp(area.y as i64, max_y.max(area.y as i64));
    Rect::new(x as i32, y as i32, w, h)
}

/// Default Orb rectangle: flush with the right edge of the work area (with a
/// small margin) and vertically centred at ~40% of the work area height.
pub fn default_orb_rect(area: &Rect, orb_logical: f64, scale: f64) -> Rect {
    let size = to_physical(orb_logical, scale);
    let margin = to_physical(ORB_EDGE_MARGIN_LOGICAL, scale) as i64;
    let x = area.right() - size as i64 - margin;
    let y = area.y as i64 + (area.h as i64 * ORB_VERTICAL_PERCENT) / 100 - size as i64 / 2;
    clamp_into(Rect::new(x as i32, y as i32, size, size), area)
}

/// Panel rectangle adjacent to the Orb: on the side with more room (left when
/// the Orb sits in the right half of the work area), vertically centred on the
/// Orb, then clamped to the work area so it is never off-screen.
pub fn panel_rect_next_to_orb(orb: &Rect, panel_w: u32, panel_h: u32, area: &Rect, scale: f64) -> Rect {
    let gap = to_physical(PANEL_GAP_LOGICAL, scale) as i64;
    let (ocx, ocy) = orb.center();
    let (acx, _) = area.center();
    let x = if ocx >= acx {
        orb.x as i64 - gap - panel_w as i64
    } else {
        orb.right() + gap
    };
    let y = ocy - panel_h as i64 / 2;
    let clamp32 = |v: i64| v.clamp(i32::MIN as i64, i32::MAX as i64) as i32;
    clamp_into(Rect::new(clamp32(x), clamp32(y), panel_w, panel_h), area)
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCALES: [f64; 4] = [1.0, 1.25, 1.5, 2.0];

    fn inside(r: &Rect, a: &Rect) -> bool {
        r.x as i64 >= a.x as i64
            && r.y as i64 >= a.y as i64
            && r.right() <= a.right()
            && r.bottom() <= a.bottom()
    }

    #[test]
    fn physical_size_follows_scale() {
        assert_eq!(to_physical(72.0, 1.0), 72);
        assert_eq!(to_physical(72.0, 1.25), 90);
        assert_eq!(to_physical(72.0, 1.5), 108);
        assert_eq!(to_physical(72.0, 2.0), 144);
        assert_eq!(to_physical(72.0, 0.0), 72);
        assert_eq!(to_physical(72.0, f64::NAN), 72);
    }

    #[test]
    fn clamp_moves_rect_inside_primary() {
        let area = Rect::new(0, 0, 1920, 1032);
        assert_eq!(clamp_into(Rect::new(-50, -10, 100, 100), &area), Rect::new(0, 0, 100, 100));
        assert_eq!(
            clamp_into(Rect::new(1900, 1000, 100, 100), &area),
            Rect::new(1820, 932, 100, 100)
        );
        let ok = Rect::new(500, 400, 100, 100);
        assert_eq!(clamp_into(ok, &area), ok);
    }

    #[test]
    fn clamp_shrinks_oversized_rect() {
        let area = Rect::new(0, 0, 800, 600);
        assert_eq!(clamp_into(Rect::new(-100, -100, 2000, 2000), &area), area);
    }

    #[test]
    fn clamp_in_negative_coordinate_monitor() {
        // Secondary monitor to the left of and above the primary one.
        let area = Rect::new(-1920, -200, 1920, 1040);
        assert_eq!(
            clamp_into(Rect::new(-2500, -900, 90, 90), &area),
            Rect::new(-1920, -200, 90, 90)
        );
        assert_eq!(
            clamp_into(Rect::new(10, 900, 90, 90), &area),
            Rect::new(-90, 750, 90, 90)
        );
    }

    #[test]
    fn best_area_prefers_largest_overlap() {
        let areas = [Rect::new(0, 0, 1920, 1032), Rect::new(-1920, 0, 1920, 1080)];
        // 80% on the secondary monitor.
        let r = Rect::new(-80, 100, 100, 100);
        assert_eq!(best_area_index(&r, &areas), Some(1));
        let r = Rect::new(-20, 100, 100, 100);
        assert_eq!(best_area_index(&r, &areas), Some(0));
    }

    #[test]
    fn best_area_falls_back_to_nearest_when_monitor_unplugged() {
        // Saved position was on a monitor at x=-1920 which is no longer attached.
        let areas = [Rect::new(0, 0, 1920, 1032)];
        let saved = Rect::new(-1800, 300, 90, 90);
        assert_eq!(best_area_index(&saved, &areas), Some(0));
        let moved = clamp_into(saved, &areas[0]);
        assert!(inside(&moved, &areas[0]));
        assert_eq!(best_area_index(&saved, &[]), None);
    }

    #[test]
    fn nearest_picks_closest_of_two() {
        let areas = [Rect::new(0, 0, 1000, 1000), Rect::new(5000, 0, 1000, 1000)];
        assert_eq!(best_area_index(&Rect::new(4000, 0, 50, 50), &areas), Some(1));
        assert_eq!(best_area_index(&Rect::new(1200, 0, 50, 50), &areas), Some(0));
    }

    #[test]
    fn default_orb_is_at_right_edge_and_40_percent_for_all_scales() {
        for scale in SCALES {
            let area = Rect::new(0, 0, (1920.0 * scale) as u32 / 1, (1032.0 * scale) as u32);
            let orb = default_orb_rect(&area, 72.0, scale);
            let size = to_physical(72.0, scale);
            let margin = to_physical(ORB_EDGE_MARGIN_LOGICAL, scale);
            assert_eq!(orb.w, size);
            assert_eq!(orb.h, size);
            assert_eq!(orb.right(), area.right() - margin as i64, "scale {scale}");
            let expected_center = area.y as i64 + area.h as i64 * 40 / 100;
            assert!(
                (orb.center().1 - expected_center).abs() <= 1,
                "scale {scale}: centre {} vs {}",
                orb.center().1,
                expected_center
            );
            assert!(inside(&orb, &area));
        }
    }

    #[test]
    fn default_orb_on_negative_secondary_monitor() {
        for scale in SCALES {
            let w = (1920.0 * scale) as u32;
            let h = (1080.0 * scale) as u32;
            let area = Rect::new(-(w as i32), -150, w, h);
            let orb = default_orb_rect(&area, 72.0, scale);
            assert!(inside(&orb, &area), "scale {scale}: {orb:?}");
            assert!(orb.x < 0 && orb.right() <= 0, "orb must stay left of origin");
            assert_eq!(best_area_index(&orb, &[Rect::new(0, 0, 1920, 1032), area]), Some(1));
        }
    }

    #[test]
    fn default_orb_tiny_work_area_is_clamped() {
        let area = Rect::new(100, 100, 60, 50);
        let orb = default_orb_rect(&area, 72.0, 1.0);
        assert!(inside(&orb, &area));
    }

    #[test]
    fn panel_goes_left_of_orb_on_right_edge() {
        for scale in SCALES {
            let area = Rect::new(0, 0, (1920.0 * scale) as u32, (1032.0 * scale) as u32);
            let orb = default_orb_rect(&area, 72.0, scale);
            let (pw, ph) = (to_physical(420.0, scale), to_physical(720.0, scale));
            let panel = panel_rect_next_to_orb(&orb, pw, ph, &area, scale);
            assert!(inside(&panel, &area), "scale {scale}");
            assert!(panel.right() <= orb.x as i64, "panel must not overlap orb (scale {scale})");
            assert_eq!(panel.w, pw);
            assert_eq!(panel.h, ph);
        }
    }

    #[test]
    fn panel_goes_right_of_orb_on_left_half() {
        let area = Rect::new(0, 0, 1920, 1032);
        let orb = Rect::new(20, 400, 72, 72);
        let panel = panel_rect_next_to_orb(&orb, 420, 720, &area, 1.0);
        assert_eq!(panel.x as i64, orb.right() + 8);
        assert!(inside(&panel, &area));
    }

    #[test]
    fn panel_never_leaves_work_area_even_when_orb_near_bottom_or_secondary_monitor() {
        for scale in SCALES {
            let w = (1600.0 * scale) as u32;
            let h = (900.0 * scale) as u32;
            let area = Rect::new(-(w as i32), -300, w, h);
            let orb = Rect::new(area.right() as i32 - 200, area.bottom() as i32 - 120, 90, 90);
            let (pw, ph) = (to_physical(420.0, scale), to_physical(720.0, scale));
            let panel = panel_rect_next_to_orb(&orb, pw, ph, &area, scale);
            assert!(inside(&panel, &area), "scale {scale}: {panel:?} not in {area:?}");
        }
    }

    #[test]
    fn panel_larger_than_area_is_shrunk() {
        let area = Rect::new(0, 0, 360, 520);
        let orb = Rect::new(280, 200, 72, 72);
        let panel = panel_rect_next_to_orb(&orb, 1180, 780, &area, 1.0);
        assert_eq!(panel, area);
    }
}
