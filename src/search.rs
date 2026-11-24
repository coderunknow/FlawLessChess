//! Search: iterative deepening + alpha-beta (PVS) + aspiration windows + quiescence
//! + transposition table + null-move pruning + LMR + move ordering.
//!
//! Single-threaded by design. `Threads` is capped at 1 in v1; search state lives entirely
//! in [`Searcher`] so a future parallel search can instance per thread.
//!
//! Draws honored inside search: repetition (2-fold along the search path), fifty-move rule,
//! insufficient material; checkmate/stalemate handled by the no-legal-moves branch, which is
//! checked BEFORE any pruning heuristic so a terminal node can never be pruned or mis-scored.
//! Mate takes precedence over claimable draw rules when the side to move is in check. The
//! fifty-move claim includes announcing a quiet move from halfmove clock 99.

use crate::attack;
use crate::eval::{
    ClassicalEvaluator, Evaluator, DRAW_SCORE, INF_SCORE, MATE_SCORE, PIECE_VALUE_MG,
};
use crate::movegen::{generate_legal, in_check};
use crate::position::Position;
use crate::tt::{TranspositionTable, BOUND_EXACT, BOUND_LOWER, BOUND_UPPER};
use crate::types::*;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

pub const MAX_PLY: i32 = 128;
const MATE_BOUND: i32 = MATE_SCORE - 100;
#[allow(dead_code)]
const SOFT_GROWTH_FACTOR: u64 = 6;

#[derive(Clone)]
pub struct SearchLimits {
    pub max_depth: i32,
    pub max_nodes: u64,
    pub soft_ms: u64,
    pub hard_ms: u64,
    pub infinite: bool,
    pub ponder: bool,
    /// True for `go movetime N`: the budget is a fixed per-move time, not a clock slice.
    /// Such a search runs iterative deepening until the hard deadline instead of stopping
    /// early on the growth prediction (which is meant only to protect clock budgets).
    pub fixed_time: bool,
    /// Start of the clock budget. `None` means the start of the search. `ponderhit` sets it to
    /// the time of the hit: the clock slice then counts from the hit, not from `go` (F-24).
    /// Only the budgets (`soft_ms`/`hard_ms`) use it; `info time` keeps the search start.
    pub clock_origin: Option<Instant>,
    /// Set by `ponderhit` on a node-capped `go ponder`: the cap counts from the hit, so the search
    /// rebases its node cap to (nodes at the hit + `max_nodes`) on the next node (F-52). The
    /// search thread does the rebase because only it knows its node count.
    pub rebase_nodes_on_hit: bool,
}

impl Default for SearchLimits {
    fn default() -> Self {
        SearchLimits {
            max_depth: 64,
            max_nodes: u64::MAX,
            soft_ms: u64::MAX,
            hard_ms: u64::MAX,
            infinite: false,
            ponder: false,
            fixed_time: false,
            clock_origin: None,
            rebase_nodes_on_hit: false,
        }
    }
}

#[derive(Clone, Debug)]
pub struct SearchResult {
    pub best_move: Move,
    pub ponder_move: Option<Move>,
    pub score_cp: i32,
    pub depth: i32,
    pub seldepth: i32,
    pub nodes: u64,
    pub pv: Vec<Move>,
}

#[derive(Clone, Debug)]
pub struct SearchProgress {
    pub depth: i32,
    pub multipv: i32,
    pub score_cp: i32,
    pub nodes: u64,
    pub seldepth: i32,
    pub pv: Vec<Move>,
}

pub struct Searcher<'a> {
    pub tt: &'a mut TranspositionTable,
    stop: &'a AtomicBool,
    limits: Arc<Mutex<SearchLimits>>,
    eval: ClassicalEvaluator,
    killers: [[Option<Move>; 2]; MAX_PLY as usize],
    /// Counter move heuristic: counters[side][opponent_from * 64 + opponent_to] stores the move
    /// that most recently caused a fail-high in reply to the opponent's move from/to.
    /// A counter move is ordered just above killers and below good captures.
    counters: [[Option<Move>; 64 * 64]; 2],
    /// Ablation mask captured at construction time (see `crate::ablation`). The counter-move
    /// heuristic is switched off completely when its bit is set: nothing is recorded and nothing
    /// is ordered above the killers.
    ablate: u32,
    history: [[i32; 64 * 64]; 2],
    lmr: [[i32; 256]; MAX_PLY as usize + 1],
    nodes: u64,
    /// `max_nodes` from the limits at construction. Enforced exactly, per node, by
    /// `node_cap_reached`; `go ponder` ignores it until `ponderhit`.
    node_cap: u64,
    seldepth: i32,
    start: Instant,
    /// Legal moves allowed at the root (from `go searchmoves`). Applied at ply 0 only.
    root_moves: Option<Vec<Move>>,
    /// Best move found at ply 0 in the most recent completed search call. Used for
    /// restricted-root PV construction instead of stale TT entries.
    root_best: Option<Move>,
    /// Null-move descendants are hypothetical positions, not a legal game path. Repetition
    /// adjudication must not use the game/search history while this flag is set (F-53).
    null_move_search: bool,
}

impl<'a> Searcher<'a> {
    pub fn new(
        tt: &'a mut TranspositionTable,
        stop: &'a AtomicBool,
        limits: Arc<Mutex<SearchLimits>>,
    ) -> Self {
        let node_cap = match limits.lock() {
            Ok(l) => l.max_nodes,
            Err(e) => e.into_inner().max_nodes,
        };
        Searcher {
            tt,
            stop,
            limits,
            eval: ClassicalEvaluator,
            killers: [[None; 2]; MAX_PLY as usize],
            counters: [[None; 64 * 64]; 2],
            ablate: crate::ablation::mask(),
            history: [[0; 64 * 64]; 2],
            lmr: build_lmr_table(),
            nodes: 0,
            node_cap,
            seldepth: 0,
            start: Instant::now(),
            root_moves: None,
            root_best: None,
            null_move_search: false,
        }
    }

    fn lim(&self) -> SearchLimits {
        match self.limits.lock() {
            Ok(l) => l.clone(),
            Err(e) => e.into_inner().clone(),
        }
    }

    pub fn nodes(&self) -> u64 {
        self.nodes
    }

    /// Null-move search is a selective-search heuristic, not a legal path from the game's
    /// history. A matching historical hash under it does not constitute a real repetition.
    #[inline]
    fn is_repetition(&self, pos: &Position, ply: i32) -> bool {
        ply > 0 && !self.null_move_search && pos.is_repetition()
    }

    /// Clock check cadence: every 128 nodes (F-49). At the 1 ms floor budget a 1024-node
    /// cadence let a single move overrun by up to ~5 ms; 128 nodes bounds the overrun to about
    /// 2.5 ms at a negligible cost (one `Instant` read per 128 nodes).
    #[inline]
    fn check_time(&mut self) {
        if self.nodes & 127 != 127 {
            return;
        }
        self.rebase_node_cap_on_hit();
        if self.should_stop_now() {
            self.stop.store(true, Ordering::Relaxed);
        }
    }

    #[inline]
    fn should_stop_now(&self) -> bool {
        let l = self.lim();
        // go infinite / go ponder / bare go: clocks are inert until an external stop (or
        // ponderhit, which flips infinite) arrives.
        if l.infinite {
            return false;
        }
        self.budget_ms(&l) >= l.hard_ms
    }

    /// Milliseconds spent against the clock budget: since `clock_origin` if set (ponderhit),
    /// otherwise since the search started.
    #[inline]
    fn budget_ms(&self, l: &SearchLimits) -> u64 {
        l.clock_origin.unwrap_or(self.start).elapsed().as_millis() as u64
    }

    /// Exact node cap, checked at every node before the node is counted, so a search never
    /// visits more than `max_nodes` nodes (S-08: the previous check ran every 1024 nodes and
    /// overshot small caps, e.g. `go nodes 1` searched 1024). While `go ponder` is waiting for
    /// `ponderhit` the cap is inert, as for any infinite search; it applies after the hit.
    #[inline]
    fn node_cap_reached(&mut self) -> bool {
        if self.nodes < self.node_cap {
            return false;
        }
        self.rebase_node_cap_on_hit();
        if self.nodes < self.node_cap {
            return false;
        }
        if self.lim().infinite {
            return false;
        }
        self.stop.store(true, Ordering::Relaxed);
        true
    }

    /// F-52: a node-capped `go ponder` counts its `max_nodes` from `ponderhit`, not from `go`
    /// (S-07). `ponderhit` sets `rebase_nodes_on_hit`; the search thread, which alone knows its
    /// node count, rebases here once. Called every 128 nodes and whenever the cap is reached, so
    /// the rebase lags the hit by at most 127 nodes.
    fn rebase_node_cap_on_hit(&mut self) {
        let l = self.lim();
        if !l.rebase_nodes_on_hit {
            return;
        }
        self.node_cap = self.nodes.saturating_add(l.max_nodes);
        if let Ok(mut shared) = self.limits.lock() {
            shared.rebase_nodes_on_hit = false;
        }
    }

    #[inline]
    fn soft_ms_reached(&self) -> bool {
        let l = self.lim();
        self.budget_ms(&l) >= l.soft_ms
    }

    #[inline]
    fn static_eval(&mut self, pos: &Position) -> i32 {
        self.eval.evaluate(pos)
    }

    fn move_order_score(
        &self,
        pos: &Position,
        m: Move,
        tt_move: Option<Move>,
        ply: usize,
        prev_move: Option<Move>,
    ) -> i32 {
        if let Some(tm) = tt_move {
            if m == tm {
                return 1_000_000;
            }
        }
        let us = pos.side;
        // Counter move: our best response to the opponent's last move. Ordered just above
        // killers, below good captures. Switched off entirely when ablated.
        if (self.ablate & crate::ablation::COUNTER_MOVE) == 0 {
            if let Some(pm) = prev_move {
                if let Some(counter) = self.counters[us][pm.from as usize * 64 + pm.to as usize] {
                    if m == counter {
                        return 92_000;
                    }
                }
            }
        }
        let is_cap = is_capture(pos, m);
        if is_cap {
            let see = static_exchange_eval(pos, m);
            // Sound captures outrank killers; losing captures are deliberately
            // demoted below ordinary quiet moves. Promotions retain a bonus.
            let mut score = if see >= 0 {
                110_000 + see.min(10_000)
            } else {
                40_000 + see.max(-10_000)
            };
            if m.promo != PROMO_NONE {
                score += 20_000 + PIECE_VALUE_MG[promo_piece_type(m.promo)] / 4;
            }
            return score;
        }
        if m.promo != PROMO_NONE {
            return 100_000 + PIECE_VALUE_MG[promo_piece_type(m.promo)] / 4;
        }
        if let Some(killer) = self.killers[ply][0] {
            if m == killer {
                return 90_000;
            }
        }
        if let Some(killer) = self.killers[ply][1] {
            if m == killer {
                return 80_000;
            }
        }
        50_000 + self.history[us][(m.from as usize) * 64 + m.to as usize]
    }

    fn order_and_score(
        &self,
        pos: &Position,
        moves: &mut MoveList,
        tt_move: Option<Move>,
        ply: usize,
        prev_move: Option<Move>,
    ) {
        for i in 0..moves.len {
            moves.scores[i] = self.move_order_score(pos, moves.moves[i], tt_move, ply, prev_move);
        }
        // Stable insertion sort by descending score (lists are short; branch-friendly). Equal
        // scores are ordered by a colour-relative key (S-14), not by generation order: generation
        // is by absolute square, a colour mirror reverses it, and LMR reduces by move index, so
        // generation order made a position and its mirror search differently.
        for i in 1..moves.len {
            let s = moves.scores[i];
            let m = moves.moves[i];
            let mut j = i;
            while j > 0
                && (moves.scores[j - 1] < s
                    || (moves.scores[j - 1] == s
                        && relative_move_key(pos.side, moves.moves[j - 1])
                            > relative_move_key(pos.side, m)))
            {
                moves.scores[j] = moves.scores[j - 1];
                moves.moves[j] = moves.moves[j - 1];
                j -= 1;
            }
            moves.scores[j] = s;
            moves.moves[j] = m;
        }
    }

    /// Root search with iterative deepening. Invokes `cb` after each completed iteration.
    pub fn search_root(
        &mut self,
        pos: &mut Position,
        root_moves: Option<Vec<Move>>,
        multi_pv: usize,
        cb: &mut dyn FnMut(&SearchProgress),
    ) -> SearchResult {
        self.tt.new_search();
        self.killers = [[None; 2]; MAX_PLY as usize];
        self.counters = [[None; 64 * 64]; 2];
        self.root_best = None;
        for side in 0..2 {
            for v in self.history[side].iter_mut() {
                *v /= 2;
            }
        }

        let legal = generate_legal(pos);
        let root_fifty_claim = legal.len > 0
            && (pos.is_fifty_move() || (pos.halfmove == 99 && has_claiming_move(pos, &legal)));
        let mut roots: Vec<Move> = legal.iter().copied().collect();
        // Root order is the tie-break order for equal scores (S-14): use the colour-relative key.
        roots.sort_by_key(|&m| relative_move_key(pos.side, m));
        if let Some(ref only) = root_moves {
            // `searchmoves` is strict (owner decision, 2026-11-22): the root set is exactly the legal
            // moves that the list names. If that intersection is empty, the root set is empty and
            // the search returns `Move::NULL` below. It never widens to all legal moves.
            roots.retain(|m| only.contains(m));
        }
        self.root_moves = if root_moves.is_some() {
            Some(roots.clone())
        } else {
            None
        };
        if roots.is_empty() {
            return SearchResult {
                best_move: Move::NULL,
                ponder_move: None,
                score_cp: if in_check(pos) {
                    -MATE_SCORE
                } else {
                    DRAW_SCORE
                },
                depth: 0,
                seldepth: 0,
                nodes: 0,
                pv: vec![],
            };
        }

        let mut best = SearchResult {
            best_move: roots[0],
            ponder_move: None,
            score_cp: DRAW_SCORE,
            depth: 0,
            seldepth: 0,
            nodes: 0,
            pv: vec![roots[0]],
        };

        let mut prev_score = 0i32;
        let mut depth = 1i32;
        loop {
            let max_depth = self.lim().max_depth;
            if depth > max_depth {
                break;
            }
            // aspiration window after depth 5
            let (mut alpha, mut beta) = if depth >= 6 {
                (prev_score - 25, prev_score + 25)
            } else {
                (-INF_SCORE, INF_SCORE)
            };
            let mut completed = false;

            if multi_pv > 1 {
                let lines =
                    self.multipv_iteration(pos, depth, &roots, multi_pv, root_fifty_claim, cb);
                if self.stop.load(Ordering::Relaxed) && depth > 1 {
                    break;
                }
                if let Some(first) = lines.first() {
                    prev_score = first.1;
                    best = SearchResult {
                        best_move: first.0,
                        ponder_move: None,
                        score_cp: first.1,
                        depth,
                        seldepth: self.seldepth,
                        nodes: self.nodes,
                        pv: vec![first.0],
                    };
                }
                completed = true;
            } else {
                loop {
                    let score = self.search(pos, depth, alpha, beta, 0, None);
                    if self.stop.load(Ordering::Relaxed) {
                        break;
                    }
                    if score <= alpha {
                        alpha = (alpha - (beta - alpha) * 3 - 20).max(-INF_SCORE);
                        continue;
                    }
                    if score >= beta {
                        beta = (beta + (beta - alpha) * 3 + 20).min(INF_SCORE);
                        continue;
                    }
                    let pv = self.extract_pv(pos, depth, true);
                    let best_move = pv.first().copied().unwrap_or(roots[0]);
                    let ponder_move = pv.get(1).copied();
                    best = SearchResult {
                        best_move,
                        ponder_move,
                        score_cp: score,
                        depth,
                        seldepth: self.seldepth,
                        nodes: self.nodes,
                        pv,
                    };
                    prev_score = score;
                    cb(&SearchProgress {
                        depth,
                        multipv: 1,
                        score_cp: score,
                        nodes: self.nodes,
                        seldepth: self.seldepth,
                        pv: best.pv.clone(),
                    });
                    completed = true;
                    break;
                }
            }
            if !completed {
                break;
            }
            // An exact mate in one is the maximum possible root score, so deeper iterations
            // cannot improve the move and can waste enormous effort (notably after retaining
            // full-depth searches for quiet checks, F-56).
            if multi_pv == 1 && !self.lim().infinite && best.score_cp >= MATE_SCORE - 1 {
                break;
            }
            // Soft budget (R-08): stop once the soft budget is reached. Completed iterations
            // are always kept; the hard limit still caps worst-case overspend inside the tree.
            // The former predictive stop (next-iteration time * growth factor) left most of the
            // clock unused on short time controls — e.g. only 116 ms of a 234 ms soft budget at
            // 10 s. Removing it lets the search use closer to its full allocation.
            let l = self.lim();
            if !l.infinite && self.soft_ms_reached() {
                break;
            }
            depth += 1;
        }
        self.root_moves = None;
        best.seldepth = self.seldepth;
        best.nodes = self.nodes;
        best
    }

    /// One ID iteration for MultiPV > 1: search every root move with a full window.
    fn multipv_iteration(
        &mut self,
        pos: &mut Position,
        depth: i32,
        roots: &[Move],
        multi_pv: usize,
        root_fifty_claim: bool,
        cb: &mut dyn FnMut(&SearchProgress),
    ) -> Vec<(Move, i32)> {
        let mut results: Vec<(Move, i32)> = Vec::with_capacity(roots.len());
        for &rm in roots {
            if self.stop.load(Ordering::Relaxed) {
                break;
            }
            let undo = pos.make_move(rm);
            let mut score = -self.search(pos, depth - 1, -INF_SCORE, INF_SCORE, 1, Some(rm));
            pos.unmake_move(rm, &undo);
            if root_fifty_claim && score < DRAW_SCORE {
                score = DRAW_SCORE;
            }
            if self.stop.load(Ordering::Relaxed) {
                // aborted mid-search: the returned score is garbage; discard it
                break;
            }
            results.push((rm, score));
        }
        results.sort_by_key(|r| std::cmp::Reverse(r.1));
        for (i, (mv, score)) in results.iter().take(multi_pv).enumerate() {
            let mut pv = vec![*mv];
            let mut child = pos.clone();
            child.make_move(*mv);
            let tail = self.extract_pv(&child, depth.saturating_sub(1), false);
            pv.extend_from_slice(&tail);
            cb(&SearchProgress {
                depth,
                multipv: (i + 1) as i32,
                score_cp: *score,
                nodes: self.nodes,
                seldepth: self.seldepth,
                pv,
            });
        }
        results
    }

    /// Walk the TT to recover a principal variation. Does not mutate `pos`.
    /// `from_root` marks the PV head extraction for the actual root position; for child
    /// continuations (MultiPV tails) the restricted-root override must not apply.
    fn extract_pv(&self, pos: &Position, max_len: i32, from_root: bool) -> Vec<Move> {
        let mut pos = pos.clone();
        let mut pv = Vec::with_capacity(16);
        for i in 0..max_len.clamp(0, MAX_PLY) {
            if i == 0 && from_root {
                if let Some(ref only) = self.root_moves {
                    // Root PV head must come from the restricted set, never a stale TT hit.
                    match self.root_best {
                        Some(m) if only.contains(&m) => {
                            pv.push(m);
                            pos.make_move(m);
                            continue;
                        }
                        _ => break,
                    }
                }
            }
            let key = pos.hash;
            match self.tt.probe_move(key, pos.halfmove) {
                Some(m) => {
                    let legal = generate_legal(&mut pos);
                    if !legal.iter().any(|&x| x == m) {
                        break;
                    }
                    pv.push(m);
                    pos.make_move(m);
                }
                None => break,
            }
        }
        pv
    }

    fn search(
        &mut self,
        pos: &mut Position,
        depth: i32,
        alpha: i32,
        beta: i32,
        ply: i32,
        prev_move: Option<Move>,
    ) -> i32 {
        if self.node_cap_reached() {
            return alpha;
        }
        self.nodes += 1;
        if ply as usize >= self.seldepth as usize {
            self.seldepth = ply;
        }
        self.check_time();
        if self.stop.load(Ordering::Relaxed) {
            return alpha;
        }
        if ply >= MAX_PLY {
            return self.static_eval(pos);
        }
        // Draw rules (FIDE 5.2.2 / 9.2 / 9.3), applied in the order the rules require:
        //  * insufficient material: a certain draw at every node below the root. The root
        //    searches its moves like the repetition rule below, so it always yields a PV and a
        //    bestmove that come from the search (audit finding F-14: single-PV search returned
        //    at the root with an empty PV, while MultiPV searched it);
        //  * in-tree repetition (2-fold along the search path) is scored as a draw at every
        //    ply EXCEPT the root, so the root always searches its moves (R-02a). A checked node
        //    with no legal reply is still checkmate (mate precedence, R-02b);
        //  * fifty-move is a CLAIMABLE draw, not a forced one: the side to move may claim it or
        //    play on, including by announcing a quiet move at clock 99; a mate takes precedence
        //    (R-02b). Such a node is searched normally, its value is clamped to >= DRAW, and TT
        //    score cutoffs and pruning are skipped there (R-12).
        let in_chk = in_check(pos);
        if ply > 0 && pos.insufficient_material() {
            return DRAW_SCORE;
        }
        if self.is_repetition(pos, ply) {
            if in_chk && generate_legal(pos).len == 0 {
                return -MATE_SCORE + ply;
            }
            return DRAW_SCORE;
        }
        // A player may claim on the 100th halfmove by announcing a quiet, non-pawn move
        // while the current clock is 99. Generate once at this boundary so the claim option
        // is included in score handling and unsafe TT cutoffs/pruning are disabled. At 100,
        // terminal detection below still gives checkmate precedence.
        let mut horizon_moves = (pos.halfmove >= 99).then(|| generate_legal(pos));
        let fifty_claim = pos.is_fifty_move()
            || horizon_moves
                .as_ref()
                .is_some_and(|moves| pos.halfmove == 99 && has_claiming_move(pos, moves));
        let mut alpha = alpha;
        let alpha_entry = alpha;
        let is_pv = beta - alpha > 1;

        // Transposition table probe first: terminal nodes are deterministic, so a
        // sufficient-depth entry is equally valid there — and this keeps TT-cutoff
        // nodes off the movegen path.
        // Position::hash excludes the halfmove clock because it is also the repetition key.
        // The TT adds the clock to its own contextual key, so only matching clock contexts can
        // reuse a score or move; this avoids bounding extensions and quiescence by nominal depth.
        let key = pos.hash;
        let probe = self.tt.probe(key, ply, pos.halfmove);
        let tt_move = probe.best_move;
        if let Some(score) = probe.score {
            if probe.depth >= depth && !is_pv && !fifty_claim {
                match probe.bound {
                    BOUND_EXACT => return score,
                    BOUND_LOWER if score >= beta => return score,
                    BOUND_UPPER if score <= alpha => return score,
                    _ => {}
                }
            }
        }

        // Terminal (no legal moves) BEFORE any pruning/fail-soft heuristic:
        // mate takes precedence over draw rules; stalemate is a draw.
        let mut moves = horizon_moves.take().unwrap_or_else(|| generate_legal(pos));
        if ply == 0 {
            if let Some(ref only) = self.root_moves {
                let mut j = 0usize;
                for i in 0..moves.len {
                    if only.contains(&moves.moves[i]) {
                        moves.moves[j] = moves.moves[i];
                        moves.scores[j] = moves.scores[i];
                        j += 1;
                    }
                }
                moves.len = j;
            }
        }
        if moves.len == 0 {
            return if in_chk {
                -MATE_SCORE + ply
            } else {
                DRAW_SCORE
            };
        }
        if depth <= 0 {
            return self.quiesce_with_moves(pos, alpha, beta, ply, Some(moves));
        }

        // Null-move pruning (not in check, not PV, non-trivial material). Skip it in positions
        // with at most thirteen pieces (F-63/F-65): false fail-highs hid forced mates in two in
        // low-material positions, despite the side to move having non-pawn material.
        if depth >= 3
            && pos.occ_all.count_ones() > 13
            && !in_chk
            && !fifty_claim
            && beta < MATE_BOUND
            && beta > -MATE_BOUND
            && pos.has_non_pawn_material(pos.side)
            && !is_pv
        {
            let prev_ep = pos.ep;
            let prev_ep_included = pos.ep_included;
            pos.make_null_move();
            let reduction = 2 + depth / 4;
            let was_null_move_search = self.null_move_search;
            self.null_move_search = true;
            let score = -self.search(
                pos,
                depth - 1 - reduction,
                -beta,
                -beta + 1,
                ply + 1,
                None, // null move is not a real opponent move
            );
            self.null_move_search = was_null_move_search;
            pos.unmake_null_move(prev_ep, prev_ep_included);
            if self.stop.load(Ordering::Relaxed) {
                return alpha;
            }
            if score >= beta {
                return beta;
            }
        }

        // Futility pruning at low depths. Not while alpha is a mate score (F-41): with alpha at a
        // mate-in-N value every ordinary line looks futile, and the quiet mating move that would
        // beat it was pruned before it was searched (mate-in-2 reported as mate-in-3).
        // Sparse positions (kings plus at most four other pieces): no static prunes and no LMR.
        // With these on, the depth-6 search missed quiet mates in three (F-44); the node cost is
        // small here, and the rule is off in ordinary middlegames, so the bench signature is kept.
        let sparse = pos.occ_all.count_ones() <= 6;
        if depth <= 2 && !in_chk && !is_pv && !fifty_claim && alpha.abs() < MATE_BOUND && !sparse {
            let s = self.static_eval(pos);
            if s + 150 * depth <= alpha {
                return self.quiesce_with_moves(pos, alpha, beta, ply, Some(moves));
            }
        }

        // Reverse futility pruning (static null-move): far-above-beta quiet
        // positions fail high without searching. Non-PV, not in check, mate-bound safe.
        if depth <= 3 && !in_chk && !is_pv && !fifty_claim && beta.abs() < MATE_BOUND && !sparse {
            let s = self.static_eval(pos);
            if s - 150 * depth >= beta {
                return beta;
            }
        }

        self.order_and_score(pos, &mut moves, tt_move, ply as usize, prev_move);

        let mut best_score = -INF_SCORE;
        let mut best_move: Option<Move> = None;

        let extension = if in_chk { 1 } else { 0 };

        let mut quiet_tried: [Move; 32] = [Move::NULL; 32];

        for (searched_count_usize, i) in (0..moves.len).enumerate() {
            let m = moves.moves[i];
            let capture = is_capture(pos, m);
            let undo = pos.make_move(m);

            // Late move reductions (quiet moves, not in check, late in the list). Do not reduce a
            // quiet move that gives check: it is a forcing move, and a reduced child can stop
            // before proving a forced mate (F-56); quiescence does not search quiet checks.
            let searched_count = searched_count_usize as i32;
            let mut reduction = 0i32;
            if depth >= 3
                && searched_count >= 3
                && !capture
                && m.promo == PROMO_NONE
                && !in_chk
                && !in_check(pos)
                && !sparse
            {
                reduction = self.lmr[(depth as usize).min(MAX_PLY as usize)]
                    [(searched_count as usize).min(255)];
                // A late quiet root move that leaves few legal replies can be a forcing threat
                // without giving check (F-59/F-60/F-61). Root LMR hid proven mate-in-two moves in
                // legal positions. Bound this correction to low-material root candidates: the
                // extra movegen is cheap there, and limiting it to ply 0 avoids tree-wide cost.
                if reduction > 0
                    && ply == 0
                    && pos.occ_all.count_ones() <= 14
                    && generate_legal(pos).len <= 11
                {
                    reduction = 0;
                }
            }

            let score = if searched_count == 0 {
                -self.search(pos, depth - 1 + extension, -beta, -alpha, ply + 1, Some(m))
            } else {
                let mut s = -self.search(
                    pos,
                    depth - 1 - reduction + extension,
                    -alpha - 1,
                    -alpha,
                    ply + 1,
                    Some(m),
                );
                if reduction > 0 && s > alpha {
                    s = -self.search(
                        pos,
                        depth - 1 + extension,
                        -alpha - 1,
                        -alpha,
                        ply + 1,
                        Some(m),
                    );
                }
                if s > alpha && s < beta {
                    s = -self.search(pos, depth - 1 + extension, -beta, -alpha, ply + 1, Some(m));
                }
                s
            };
            pos.unmake_move(m, &undo);
            if self.stop.load(Ordering::Relaxed) {
                return alpha;
            }

            if score > best_score {
                best_score = score;
                best_move = Some(m);
            }
            if score > alpha {
                alpha = score;
            }
            if alpha >= beta {
                if !capture {
                    let ply_idx = ply as usize;
                    self.killers[ply_idx][1] = self.killers[ply_idx][0];
                    self.killers[ply_idx][0] = Some(m);
                    // Counter move: our move m caused a fail-high in reply to the opponent's
                    // previous move. Store it so we can try it first next time we face that move.
                    if (self.ablate & crate::ablation::COUNTER_MOVE) == 0 {
                        if let Some(pm) = prev_move {
                            self.counters[pos.side][pm.from as usize * 64 + pm.to as usize] =
                                Some(m);
                        }
                    }
                    let h = &mut self.history[pos.side][(m.from as usize) * 64 + m.to as usize];
                    *h = (*h + depth * depth).min(100_000);
                    for q in quiet_tried.iter() {
                        if *q == Move::NULL {
                            break;
                        }
                        let h = &mut self.history[pos.side][(q.from as usize) * 64 + q.to as usize];
                        *h = (*h - depth * depth).max(0);
                    }
                }
                break;
            }
            if !capture {
                for slot in quiet_tried.iter_mut() {
                    if *slot == Move::NULL {
                        *slot = m;
                        break;
                    }
                }
            }
        }

        if fifty_claim && best_score < DRAW_SCORE {
            best_score = DRAW_SCORE;
        }
        if ply == 0 {
            self.root_best = best_move;
        }
        let flag = if best_score >= beta {
            BOUND_LOWER
        } else if best_score > alpha_entry {
            BOUND_EXACT
        } else {
            // best-score did not raise alpha: fail-low (upper bound)
            BOUND_UPPER
        };
        // Restricted root search (`go searchmoves`) yields scores only valid within the
        // restriction — never store them as unrestricted bounds. The TT move itself may
        // still be recorded for ordering, but extract_pv bypasses it at ply 0.
        if !(ply == 0 && self.root_moves.is_some()) {
            self.tt.store(crate::tt::StoreRequest {
                key,
                best_move,
                score: best_score,
                depth,
                bound: flag,
                ply,
                halfmove: pos.halfmove,
            });
        }
        best_score
    }

    fn quiesce(&mut self, pos: &mut Position, alpha: i32, beta: i32, ply: i32) -> i32 {
        self.quiesce_with_moves(pos, alpha, beta, ply, None)
    }

    /// Reuse legal moves already generated by the main search when it descends into quiescence.
    /// `initial_moves` is from the unchanged `pos` and has already passed terminal detection.
    fn quiesce_with_moves(
        &mut self,
        pos: &mut Position,
        alpha: i32,
        beta: i32,
        ply: i32,
        initial_moves: Option<MoveList>,
    ) -> i32 {
        // At halfmove 99, a claim is available if the player can announce a quiet,
        // non-pawn move that reaches 100. At/after 100, the player can claim immediately.
        // Reuse the main-search move list when present; only boundary qnodes without one
        // generate a list here. An empty legal list is terminal, so checkmate takes priority.
        let mut boundary_moves = initial_moves;
        let claim = if pos.halfmove >= 99 {
            if boundary_moves.is_none() {
                boundary_moves = Some(generate_legal(pos));
            }
            // A restricted root list is a search constraint, not a restriction on the player's
            // legal right to claim. In that uncommon boundary case, inspect the full legal list
            // without replacing the restricted list consumed by qsearch itself.
            let unrestricted_root_moves =
                (ply == 0 && self.root_moves.is_some()).then(|| generate_legal(pos));
            let moves = unrestricted_root_moves
                .as_ref()
                .or(boundary_moves.as_ref())
                .expect("boundary moves were generated");
            moves.len > 0
                && (pos.is_fifty_move() || (pos.halfmove == 99 && has_claiming_move(pos, moves)))
        } else {
            false
        };
        let v = self.quiesce_core(pos, alpha, beta, ply, boundary_moves);
        if claim && v < DRAW_SCORE {
            DRAW_SCORE
        } else {
            v
        }
    }

    fn quiesce_core(
        &mut self,
        pos: &mut Position,
        alpha: i32,
        beta: i32,
        ply: i32,
        initial_moves: Option<MoveList>,
    ) -> i32 {
        if self.node_cap_reached() {
            return alpha;
        }
        self.nodes += 1;
        if ply as usize >= self.seldepth as usize {
            self.seldepth = ply;
        }
        self.check_time();
        if self.stop.load(Ordering::Relaxed) {
            return alpha;
        }
        if ply >= MAX_PLY {
            return self.static_eval(pos);
        }
        let in_chk = in_check(pos);
        let mut alpha = alpha;

        // Terminal BEFORE the stand-pat cutoffs: stand-pat is only valid when the side
        // to move has at least one legal move. Stalemate is a draw; mate is scored.
        let mut moves = initial_moves.unwrap_or_else(|| generate_legal(pos));
        if moves.len == 0 {
            return if in_chk {
                -MATE_SCORE + ply
            } else {
                DRAW_SCORE
            };
        }
        // Certain draws and in-tree repetition (terminal check ran first, so mate cannot be
        // masked here). Fifty-move is a claim handled by the `quiesce` wrapper.
        if pos.insufficient_material() || self.is_repetition(pos, ply) {
            return DRAW_SCORE;
        }

        let stand_pat = if !in_chk {
            let sp = self.static_eval(pos);
            if sp >= beta {
                return beta;
            }
            if sp > alpha {
                alpha = sp;
            }
            Some(sp)
        } else {
            None
        };
        if !in_chk {
            let mut j = 0;
            for i in 0..moves.len {
                let m = moves.moves[i];
                if is_capture(pos, m) || m.promo != PROMO_NONE {
                    moves.moves[j] = moves.moves[i];
                    moves.scores[j] = moves.scores[i];
                    j += 1;
                }
            }
            moves.len = j;
        }
        self.order_and_score(pos, &mut moves, None, ply as usize, None);

        for i in 0..moves.len {
            let m = moves.moves[i];
            // SEE is ordering-only; its approximate exchange model never prunes tactical captures.
            if let Some(sp) = stand_pat {
                let capture_gain = captured_piece(pos, m)
                    .map(|p| PIECE_VALUE_MG[p])
                    .unwrap_or(0);
                let promo_gain = if m.promo != PROMO_NONE {
                    PIECE_VALUE_MG[promo_piece_type(m.promo)].saturating_sub(PIECE_VALUE_MG[PAWN])
                } else {
                    0
                };
                // Not while alpha is a mate score (F-42): a capture that mates is worth MATE, and
                // the margin test would prune it against a mate-in-N alpha.
                if alpha.abs() < MATE_BOUND && sp + capture_gain + promo_gain + 200 < alpha {
                    continue;
                }
            }
            let undo = pos.make_move(m);
            let score = -self.quiesce(pos, -beta, -alpha, ply + 1);
            pos.unmake_move(m, &undo);
            if self.stop.load(Ordering::Relaxed) {
                return alpha;
            }
            if score >= beta {
                return beta;
            }
            if score > alpha {
                alpha = score;
            }
        }
        alpha
    }
}

/// Colour-relative sort key of a move: squares are read from the side to move (black squares are
/// mirrored with `^ 56`), so a move and its colour mirror get the same key. Used only to order
/// equal move scores (S-14); see `order_and_score`.
#[inline]
fn relative_move_key(side: usize, m: Move) -> u32 {
    let rel = |sq: Square| -> u32 { (if side == WHITE { sq } else { sq ^ 56 }) as u32 };
    (rel(m.from) << 6) | rel(m.to)
}

fn captured_piece(pos: &Position, m: Move) -> Option<usize> {
    if let Some((_, p)) = pos.piece_on(m.to) {
        return Some(p);
    }
    let us = pos.side;
    let moved_pawn = pos.pieces[us * 6 + PAWN] & (1u64 << m.from) != 0;
    if moved_pawn && file_of(m.from) != file_of(m.to) && pos.ep >= 0 && m.to as i8 == pos.ep {
        return Some(PAWN);
    }
    None
}

/// Static exchange evaluation for a capture, in centipawns.
///
/// This is a material-only, least-valuable-attacker swap sequence. It accounts for
/// en-passant removal, x-rays, promotions, and defended king recaptures. As with
/// conventional SEE, pinned-piece legality is approximated; it is used only as a
/// move-ordering/pruning heuristic, never as a legality test.
fn static_exchange_eval(pos: &Position, m: Move) -> i32 {
    let Some((us, mover)) = pos.piece_on(m.from) else {
        return 0;
    };
    let Some(victim) = captured_piece(pos, m) else {
        return 0;
    };
    let them = 1 - us;
    let captured_sq = if pos.piece_on(m.to).is_some() {
        m.to
    } else if mover == PAWN && file_of(m.from) != file_of(m.to) && pos.ep >= 0 {
        if us == WHITE {
            m.to.saturating_sub(8)
        } else {
            m.to.saturating_add(8)
        }
    } else {
        return 0;
    };
    let captured_bit = 1u64 << captured_sq;
    if pos.pieces[them * 6 + victim] & captured_bit == 0 {
        return 0;
    }

    let mut pieces = pos.pieces;
    let from_bit = 1u64 << m.from;
    let target_bit = 1u64 << m.to;
    let mut occupied = pos.occ_all & !from_bit & !captured_bit;
    pieces[us * 6 + mover] &= !from_bit;
    pieces[them * 6 + victim] &= !captured_bit;

    let first_piece = if m.promo != PROMO_NONE {
        promo_piece_type(m.promo)
    } else {
        mover
    };
    let first_promo_gain = if m.promo != PROMO_NONE {
        PIECE_VALUE_MG[first_piece] - PIECE_VALUE_MG[PAWN]
    } else {
        0
    };
    pieces[us * 6 + first_piece] |= target_bit;
    occupied |= target_bit;

    let mut gain = [0i32; 32];
    gain[0] = PIECE_VALUE_MG[victim] + first_promo_gain;
    let mut depth = 0usize;
    let mut side = them;
    let mut occupant = first_piece;

    while depth + 1 < gain.len() {
        let Some((attacker, from)) = see_least_attacker(&pieces, occupied, side, m.to) else {
            break;
        };
        let from_mask = 1u64 << from;
        let promotion = attacker == PAWN
            && ((side == WHITE && rank_of(m.to) == 7) || (side == BLACK && rank_of(m.to) == 0));
        let next_occupant = if promotion { QUEEN } else { attacker };
        let promotion_gain = if promotion {
            PIECE_VALUE_MG[QUEEN] - PIECE_VALUE_MG[PAWN]
        } else {
            0
        };

        // A king may not recapture onto a defended square. Test after removing
        // its source square and the current target occupant so x-rays are visible.
        if attacker == KING {
            let mut king_pieces = pieces;
            king_pieces[(1 - side) * 6 + occupant] &= !target_bit;
            king_pieces[side * 6 + KING] &= !from_mask;
            king_pieces[side * 6 + KING] |= target_bit;
            let king_occupancy = occupied & !from_mask;
            if see_square_attacked(&king_pieces, king_occupancy, 1 - side, m.to) {
                break;
            }
        }

        depth += 1;
        gain[depth] = PIECE_VALUE_MG[occupant] + promotion_gain - gain[depth - 1];

        pieces[(1 - side) * 6 + occupant] &= !target_bit;
        pieces[side * 6 + attacker] &= !from_mask;
        pieces[side * 6 + next_occupant] |= target_bit;
        occupied &= !from_mask;
        occupant = next_occupant;
        side = 1 - side;
    }

    while depth > 0 {
        gain[depth - 1] = -(-gain[depth - 1]).max(gain[depth]);
        depth -= 1;
    }
    gain[0]
}

fn see_least_attacker(
    pieces: &[u64; 12],
    occupied: u64,
    side: usize,
    target: Square,
) -> Option<(usize, Square)> {
    let reverse_pawns = attack::pawn_attacks_lookup(1 - side, target) & pieces[side * 6 + PAWN];
    let attackers = reverse_pawns
        | (attack::KNIGHT_ATTACKS[target as usize] & pieces[side * 6 + KNIGHT])
        | (attack::bishop_attacks(target, occupied)
            & (pieces[side * 6 + BISHOP] | pieces[side * 6 + QUEEN]))
        | (attack::rook_attacks(target, occupied)
            & (pieces[side * 6 + ROOK] | pieces[side * 6 + QUEEN]))
        | (attack::KING_ATTACKS[target as usize] & pieces[side * 6 + KING]);
    for piece in [PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING] {
        let candidates = attackers & pieces[side * 6 + piece];
        if candidates != 0 {
            return Some((piece, candidates.trailing_zeros() as Square));
        }
    }
    None
}

fn see_square_attacked(pieces: &[u64; 12], occupied: u64, by_side: usize, square: Square) -> bool {
    let pawns = attack::pawn_attacks_lookup(1 - by_side, square) & pieces[by_side * 6 + PAWN];
    let knights = attack::KNIGHT_ATTACKS[square as usize] & pieces[by_side * 6 + KNIGHT];
    let bishops = attack::bishop_attacks(square, occupied)
        & (pieces[by_side * 6 + BISHOP] | pieces[by_side * 6 + QUEEN]);
    let rooks = attack::rook_attacks(square, occupied)
        & (pieces[by_side * 6 + ROOK] | pieces[by_side * 6 + QUEEN]);
    let kings = attack::KING_ATTACKS[square as usize] & pieces[by_side * 6 + KING];
    (pawns | knights | bishops | rooks | kings) != 0
}

/// Whether `moves` contains a legal move that can be announced for a fifty-move claim
/// from halfmove clock 99. Pawn moves and captures reset the clock instead of reaching 100.
fn has_claiming_move(pos: &Position, moves: &MoveList) -> bool {
    (0..moves.len).any(|i| {
        let m = moves.moves[i];
        !is_capture(pos, m) && pos.piece_on(m.from).is_some_and(|(_, piece)| piece != PAWN)
    })
}

#[inline]
pub fn is_capture(pos: &Position, m: Move) -> bool {
    captured_piece(pos, m).is_some()
}

fn build_lmr_table() -> [[i32; 256]; MAX_PLY as usize + 1] {
    let mut t = [[0i32; 256]; MAX_PLY as usize + 1];
    for (depth, row) in t.iter_mut().enumerate().skip(3) {
        for (count, cell) in row.iter_mut().enumerate().skip(3) {
            let d = depth as f64;
            let c = count as f64;
            let r = (d.ln() * c.ln() * 0.6) as i32;
            *cell = r.clamp(0, depth as i32 - 1);
        }
    }
    t
}

#[cfg(test)]
mod see_tests {
    use super::*;

    fn position(fen: &str) -> Position {
        Position::from_fen(fen).expect("test FEN")
    }

    #[test]
    fn see_free_queen_capture() {
        let pos = position("4k3/8/8/4q3/4R3/8/8/4K3 w - - 0 1");
        assert_eq!(static_exchange_eval(&pos, Move::new(28, 36)), 900);
    }

    #[test]
    fn see_losing_capture_accounts_for_recapture() {
        let pos = position("4k3/3p4/4p3/8/2B5/8/8/4K3 w - - 0 1");
        assert_eq!(static_exchange_eval(&pos, Move::new(26, 44)), -230);
    }

    #[test]
    fn see_xray_recapture_is_discovered() {
        let pos = position("4k3/3p4/4p3/8/2B5/8/8/4R1K1 w - - 0 1");
        assert_eq!(static_exchange_eval(&pos, Move::new(26, 44)), -130);
    }

    #[test]
    fn see_en_passant_removes_the_bypassed_pawn() {
        let pos = position("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1");
        assert_eq!(static_exchange_eval(&pos, Move::new(36, 43)), 100);
    }

    #[test]
    fn see_capture_promotion_adds_promotion_material() {
        let pos = position("7r/6P1/5k2/8/8/8/8/4K3 w - - 0 1");
        assert_eq!(
            static_exchange_eval(&pos, Move::with_promo(54, 63, PROMO_QUEEN)),
            1_300
        );
    }
}

#[cfg(test)]
mod draw_rule_tests {
    use super::*;
    use crate::movegen::generate_legal;
    use std::sync::atomic::AtomicBool;

    fn play(pos: &mut Position, uci: &str) {
        let legal = generate_legal(pos);
        let m = legal
            .iter()
            .copied()
            .find(|m| m.to_string() == uci)
            .expect("legal test move");
        pos.make_move(m);
    }

    fn run(pos: &mut Position, depth: i32) -> SearchResult {
        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: depth,
            ..SearchLimits::default()
        }));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        s.search_root(pos, None, 1, &mut |_| {})
    }

    /// Regression (owner decision, 2026-11-22, strict `searchmoves`): a list that names only illegal
    /// moves has an empty intersection with the legal moves. The search must not widen to the legal
    /// moves; it returns `Move::NULL` and searches nothing. The previous widening (2026-11-20) is
    /// superseded.
    #[test]
    fn searchmoves_with_no_legal_move_searches_nothing() {
        let mut pos = Position::startpos();
        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: 2,
            ..SearchLimits::default()
        }));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let illegal = Move::from_uci("e2e5").expect("parse");
        let r = s.search_root(&mut pos, Some(vec![illegal]), 1, &mut |_| {});
        assert_eq!(
            r.best_move,
            Move::NULL,
            "an empty legal intersection must give no move, not a widened search"
        );
        assert_eq!(
            r.nodes, 0,
            "no node may be searched outside the requested root set"
        );
    }

    /// Strict `searchmoves`: the returned move always lies in the requested set (never outside it).
    #[test]
    fn searchmoves_result_is_always_inside_the_requested_set() {
        let mut pos = Position::startpos();
        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: 3,
            ..SearchLimits::default()
        }));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let named = vec![
            Move::from_uci("a2a3").expect("parse"),
            Move::from_uci("h2h4").expect("parse"),
        ];
        let r = s.search_root(&mut pos, Some(named.clone()), 1, &mut |_| {});
        assert!(
            named.contains(&r.best_move),
            "bestmove {:?} is outside searchmoves",
            r.best_move
        );
    }

    /// A TT score stored away from the fifty-move horizon must not cut off a search of the same
    /// board at halfmove 98: the clock is absent from the Zobrist key, but the searched subtree
    /// can now reach a claim. The cached move remains usable; only the score is withheld.
    #[test]
    fn tt_score_from_low_clock_context_does_not_cut_off_near_fifty_move_horizon() {
        let mut pos =
            Position::from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 98 1")
                .expect("fen");
        assert_eq!(
            pos.hash,
            Position::startpos().hash,
            "clock must be unhashed"
        );
        let mut tt = TranspositionTable::new(4);
        tt.store(crate::tt::StoreRequest {
            key: pos.hash,
            best_move: None,
            score: 500,
            depth: 5,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        });
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits::default()));
        let mut searcher = Searcher::new(&mut tt, &stop, limits);
        let _ = searcher.search(&mut pos, 2, -100, -99, 1, None);
        assert!(
            searcher.nodes() > 1,
            "probe-clock-dependent TT score caused an unsafe cutoff"
        );
    }

    /// A null move is not a real game move, so a position reached by a null-search branch must
    /// not be treated as repeated merely because that hash exists in the game's history. This
    /// legal four-ply sequence makes the distinction concrete: after black's two king moves and
    /// white's rook manoeuvre, a hypothetical null followed by Ra8-f8 recreates the initial hash.
    #[test]
    fn null_move_search_does_not_claim_game_history_repetition() {
        let mut pos = Position::from_fen("5R2/8/8/8/7K/3p4/4P3/6k1 b - - 0 1").expect("fen");
        for m in ["g1h1", "f8e8", "h1g1", "e8a8"] {
            play(&mut pos, m);
        }
        assert!(!pos.is_repetition());

        pos.make_null_move();
        play(&mut pos, "a8f8");
        assert!(
            pos.is_repetition(),
            "setup must match the historical position"
        );

        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits::default()));
        let mut searcher = Searcher::new(&mut tt, &stop, limits);
        searcher.null_move_search = true;
        let _ = searcher.search(&mut pos, 0, -INF_SCORE, INF_SCORE, 1, None);
        assert!(
            searcher.nodes() > 2,
            "search and quiescence must both ignore historical repetitions under a null move"
        );
    }

    /// R-02a: a repeated ROOT must still be searched (not scored as an instant draw).
    #[test]
    fn root_repetition_is_searched() {
        let mut pos = Position::startpos();
        for m in [
            "b1c3", "b8c6", "c3b1", "c6b8", "g1f3", "g8f6", "f3g1", "f6g8",
        ] {
            play(&mut pos, m);
        }
        assert!(pos.is_repetition());
        let r = run(&mut pos, 4);
        assert!(r.nodes > 100, "root was not searched: {} nodes", r.nodes);
        assert!(!r.pv.is_empty());
    }

    /// R-02b: mate-in-1 takes precedence over the fifty-move claim.
    #[test]
    fn mate_beats_fifty_move_claim() {
        let mut pos = Position::from_fen("k7/8/1K6/8/8/8/8/7R w - - 100 60").expect("fen");
        let r = run(&mut pos, 3);
        assert!(
            r.score_cp > MATE_SCORE - 100,
            "expected mate, got {}",
            r.score_cp
        );
    }

    /// F-67: a claim can be made by announcing a quiet move that reaches 100 halfmoves.
    /// The checking move reaches clock 99 and leaves White only the quiet king evasion g3h3;
    /// White may claim before playing it, so the restricted checking move cannot score as a win.
    #[test]
    fn intended_fifty_move_claim_is_honored_after_quiet_check_evasion() {
        let mut pos =
            Position::from_fen("8/6p1/6p1/6B1/1r5P/1k4K1/4q3/8 b - - 98 40").expect("fen");
        let check = Move::from_uci("b4g4").expect("move");
        let r = {
            let mut tt = TranspositionTable::new(4);
            let stop = AtomicBool::new(false);
            let limits = Arc::new(Mutex::new(SearchLimits {
                max_depth: 1,
                ..SearchLimits::default()
            }));
            let mut s = Searcher::new(&mut tt, &stop, limits);
            s.search_root(&mut pos, Some(vec![check]), 1, &mut |_| {})
        };
        assert_eq!(r.best_move, check);
        assert_eq!(r.score_cp, DRAW_SCORE, "missed intended fifty-move claim");
    }

    /// MultiPV searches each root move separately, so it must carry the unchanged root's
    /// claim option into the displayed line score even when the selected search move resets
    /// the clock. `searchmoves a2a3` must not hide White's claim by announcing a quiet king move.
    #[test]
    fn multipv_root_claim_survives_restricted_clock_resetting_move() {
        let mut pos = Position::from_fen("7k/8/8/8/5K2/8/P7/q7 w - - 99 74").expect("fen");
        let pawn_move = Move::from_uci("a2a3").expect("move");
        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: 2,
            ..SearchLimits::default()
        }));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let mut progress = Vec::new();
        let r = s.search_root(&mut pos, Some(vec![pawn_move]), 2, &mut |p| {
            progress.push(p.clone());
        });
        assert_eq!(r.best_move, pawn_move);
        assert_eq!(r.score_cp, DRAW_SCORE);
        assert!(!progress.is_empty());
        assert!(progress.iter().all(|p| p.score_cp >= DRAW_SCORE));
    }

    #[test]
    fn multipv_root_claim_does_not_clamp_a_positive_score_to_draw() {
        let mut pos = Position::from_fen("r6k/8/2Q5/8/8/8/8/6K1 w - - 99 1").expect("fen");
        let legal = generate_legal(&mut pos);
        assert!(has_claiming_move(&pos, &legal));

        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: 1,
            ..SearchLimits::default()
        }));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let r = s.search_root(&mut pos, None, 2, &mut |_| {});
        assert!(r.score_cp > DRAW_SCORE, "positive score was lost: {r:?}");
    }

    /// Halfmove 99 is claimable only when a legal quiet non-pawn move can be announced.
    /// In this checked position all four legal moves capture the checking-side queen, so the
    /// clock advances only if the claim condition were incorrectly applied to captures.
    #[test]
    fn clock_99_without_eligible_quiet_move_is_not_claimable_in_multipv() {
        let fen = "rnbq1b1r/2pQk2p/5ppn/pp2P3/1P6/P1P1PP2/6PP/RNB1KBNR b KQ - {clock} 40";
        let mut scores = Vec::new();
        for clock in [98, 99] {
            let mut pos =
                Position::from_fen(&fen.replace("{clock}", &clock.to_string())).expect("fen");
            let legal = generate_legal(&mut pos);
            assert_eq!(legal.len, 4);
            assert!(!has_claiming_move(&pos, &legal));
            let mut tt = TranspositionTable::new(4);
            let stop = AtomicBool::new(false);
            let limits = Arc::new(Mutex::new(SearchLimits {
                max_depth: 1,
                ..SearchLimits::default()
            }));
            let mut s = Searcher::new(&mut tt, &stop, limits);
            let capture = Move::from_uci("e7d7").expect("capture");
            let r = s.search_root(&mut pos, Some(vec![capture]), 2, &mut |_| {});
            assert_eq!(r.best_move, capture);
            scores.push(r.score_cp);
        }
        assert_eq!(scores[0], scores[1]);
        assert!(scores[1] > DRAW_SCORE);
    }

    /// A clock-0 depth-1 TT bound cannot cut off the same position at clock 97. The non-PV
    /// mate-bound window disables shallow static pruning while still allowing a TT cutoff; the
    /// `b4g4` checking line plus quiet evasion reaches the claim boundary through extensions/qsearch.
    #[test]
    fn tt_score_does_not_cross_clock_before_extended_quiescence_claim() {
        let mut pos =
            Position::from_fen("8/6p1/6p1/6B1/1r5P/1k4K1/4q3/8 b - - 97 40").expect("fen");
        let mut tt = TranspositionTable::new(4);
        tt.store(crate::tt::StoreRequest {
            key: pos.hash,
            best_move: Some(Move::from_uci("b4g4").expect("move")),
            score: -500,
            depth: 1,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        });
        assert_eq!(tt.probe(pos.hash, 0, 97).score, None);

        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits::default()));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let _ = s.search(&mut pos, 1, MATE_BOUND, MATE_BOUND + 1, 0, None);
        assert!(
            s.nodes() > 1,
            "search did not explore beyond the root: nodes={}, stop={}",
            s.nodes(),
            stop.load(Ordering::Relaxed)
        );
    }

    /// The qsearch boundary must honor intended claims too, without replacing a checkmate
    /// at the 100-halfmove position with a draw.
    #[test]
    fn qsearch_honors_intended_claim_and_keeps_mate_precedence() {
        let mut tt = TranspositionTable::new(4);
        let stop = AtomicBool::new(false);
        let limits = Arc::new(Mutex::new(SearchLimits::default()));
        let mut s = Searcher::new(&mut tt, &stop, limits);
        let mut claim =
            Position::from_fen("8/6p1/6p1/6B1/6rP/1k4K1/4q3/8 w - - 99 40").expect("claim fen");
        assert_eq!(s.quiesce(&mut claim, -INF_SCORE, INF_SCORE, 1), DRAW_SCORE);

        let mut mate = Position::from_fen("7k/6Q1/6K1/8/8/8/8/8 b - - 100 1").expect("mate fen");
        assert_eq!(
            s.quiesce(&mut mate, -INF_SCORE, INF_SCORE, 1),
            -MATE_SCORE + 1
        );
    }

    /// R-02b/R-12: at a claimable fifty-move node the value is never below DRAW.
    #[test]
    fn fifty_move_claim_value_is_at_least_draw() {
        let mut pos = Position::from_fen("7k/8/8/8/5K2/8/8/q7 b - - 100 74").expect("fen");
        let r = run(&mut pos, 6);
        assert!(
            r.score_cp >= DRAW_SCORE,
            "claim value below draw: {}",
            r.score_cp
        );
    }
}
