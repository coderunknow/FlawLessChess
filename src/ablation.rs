//! Optional ablation switch used to measure each heuristic's contribution independently.
//!
//! The switch is a **diagnostic** mechanism for CI benchmarking only: the environment variable
//! `FLAWLESS_ABLATE` holds a comma-separated list of term names. Every listed term is disabled
//! in the running process, so a single binary can be measured with and without one heuristic.
//!
//! Design constraints:
//! * The default (variable unset) disables nothing — shipped behaviour is unchanged.
//! * The specification is read **once** per process, so a running search cannot change behaviour
//!   halfway through a game.
//! * Unknown names are ignored (a typo must never silently disable something else).
//! * The check is a single bit test on a process-wide mask, so the hot search path pays one
//!   atomic load per evaluation and nothing per move.
//! * A pinned baseline build predates this module and ignores the variable entirely, so the same
//!   environment can be handed to both engines of a benchmark without affecting the baseline.

use std::sync::OnceLock;

/// Term names understood by the switch. Keep in sync with `docs/ABLATIONS.md`.
pub const TERMS: [&str; 3] = ["space", "counter_move", "outpost"];

/// Mask bit for the `space` evaluation term.
pub const SPACE: u32 = 1 << 0;
/// Mask bit for the `counter_move` move-ordering heuristic.
pub const COUNTER_MOVE: u32 = 1 << 1;
/// Mask bit for the `outpost` evaluation term.
pub const OUTPOST: u32 = 1 << 2;

/// Maps a term name to its mask bit. Unknown names map to `0`, i.e. they disable nothing.
pub fn term_bit(name: &str) -> u32 {
    match name {
        "space" => SPACE,
        "counter_move" => COUNTER_MOVE,
        "outpost" => OUTPOST,
        _ => 0,
    }
}

/// Normalized, de-duplicated term names from a comma-separated specification.
///
/// Unknown and empty entries are dropped; known terms keep the order of [`TERMS`].
pub fn parse_spec(spec: &str) -> Vec<&'static str> {
    let mut selected: Vec<&'static str> = Vec::new();
    for raw in spec.split(',') {
        let name = raw.trim();
        if name.is_empty() {
            continue;
        }
        if let Some(term) = TERMS.iter().find(|t| **t == name) {
            if !selected.contains(term) {
                selected.push(*term);
            }
        }
    }
    selected
}

/// The mask of the terms disabled by the given specification.
pub fn mask_from_spec(spec: &str) -> u32 {
    parse_spec(spec)
        .iter()
        .fold(0u32, |acc, term| acc | term_bit(term))
}

/// True when `name` is disabled by the given specification.
pub fn disabled_in(spec: &str, name: &str) -> bool {
    mask_from_spec(spec) & term_bit(name) != 0
}

/// The process-wide specification, read once from the environment.
pub fn spec() -> &'static str {
    static SPEC: OnceLock<String> = OnceLock::new();
    SPEC.get_or_init(|| std::env::var("FLAWLESS_ABLATE").unwrap_or_default())
}

/// The process-wide ablation mask, computed once from the environment.
///
/// This is the value the evaluation and the search consult. It is a plain `u32` bit mask so the
/// hot path costs one relaxed atomic load plus one bit test.
pub fn mask() -> u32 {
    static MASK: OnceLock<u32> = OnceLock::new();
    *MASK.get_or_init(|| mask_from_spec(spec()))
}

/// True when the given term bit is disabled in this process.
pub fn is_disabled(bit: u32) -> bool {
    mask() & bit != 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_specification_disables_nothing() {
        assert!(parse_spec("").is_empty());
        assert!(!disabled_in("", "space"));
        assert!(!disabled_in("   ", "space"));
        assert_eq!(mask_from_spec(""), 0);
    }

    #[test]
    fn known_terms_are_selected_and_unknown_terms_ignored() {
        assert_eq!(parse_spec("space"), vec!["space"]);
        assert_eq!(parse_spec(" space , outpost "), vec!["space", "outpost"]);
        assert!(parse_spec("nonexistent").is_empty());
        assert_eq!(parse_spec("space,nonexistent"), vec!["space"]);
    }

    #[test]
    fn duplicate_terms_are_collapsed() {
        assert_eq!(parse_spec("space,space"), vec!["space"]);
        assert_eq!(
            parse_spec("space, counter_move,space"),
            vec!["space", "counter_move"]
        );
    }

    #[test]
    fn disabled_in_matches_the_selected_terms() {
        assert!(disabled_in("space,counter_move", "space"));
        assert!(disabled_in("space,counter_move", "counter_move"));
        assert!(!disabled_in("space,counter_move", "outpost"));
    }

    #[test]
    fn mask_bits_are_distinct_and_unknown_terms_map_to_zero() {
        assert_ne!(SPACE, COUNTER_MOVE);
        assert_ne!(SPACE, OUTPOST);
        assert_ne!(COUNTER_MOVE, OUTPOST);
        assert_eq!(term_bit("nonexistent"), 0);
        assert_eq!(term_bit("space"), SPACE);
    }

    #[test]
    fn mask_from_spec_enables_exactly_the_selected_terms() {
        assert_eq!(mask_from_spec("space"), SPACE);
        assert_eq!(mask_from_spec("space,outpost"), SPACE | OUTPOST);
        assert_eq!(mask_from_spec("space,space"), SPACE);
        assert_eq!(mask_from_spec("space,bogus"), SPACE);
        assert_eq!(mask_from_spec("bogus"), 0);
    }
}
