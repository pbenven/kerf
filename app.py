from flask import Flask, render_template, request, jsonify
import random
from dataclasses import dataclass, asdict
from typing import List

app = Flask(__name__)

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Rect:
    x: float; y: float; w: float; h: float
    def area(self): return self.w * self.h
    def can_fit(self, pw, ph): return pw <= self.w and ph <= self.h

@dataclass
class PlacedPart:
    part_id: str; name: str
    x: float; y: float; length: float; width: float; rotated: bool

@dataclass
class StockResult:
    stock_id: str; stock_length: float; stock_width: float; stock_label: str
    placed: list; waste_area: float; utilization: float


# ─── Maximal Rectangles packer ────────────────────────────────────────────────
#
# After placing each piece, splits ALL free rectangles that overlap the placed
# area (up to 4 sub-rects per overlap), then prunes rects fully contained
# inside a larger one.  Keeps the full irregular free space available.
#
# Heuristic: BSSF (Best Short Side Fit) — place the piece whose placement
# minimises the shorter leftover side of the chosen free rectangle.
# Tie-break: prefer no rotation, then larger free rect area (keeps big
# contiguous space for later pieces).

def max_rects_pack(stock_l, stock_w, parts, kerf, allow_rotate):
    """Returns (placed_list, unplaced_list)."""
    free = [Rect(0, 0, stock_l, stock_w)]
    placed = []
    remaining = list(parts)

    while remaining:
        best = None  # (bssf_score, -rect_area, rotated_int, ri, pi, pl, pw)

        for ri, rect in enumerate(free):
            for pi, part in enumerate(remaining):
                for rotated in ([False, True] if allow_rotate else [False]):
                    pl = part['width'] if rotated else part['length']
                    pw = part['length'] if rotated else part['width']
                    if not rect.can_fit(pl, pw):
                        continue
                    bssf  = min(rect.w - pl, rect.h - pw)
                    # Tie-break: prefer no rotation, then prefer larger rect
                    # (negative area so smaller tuple value = larger rect)
                    candidate = (bssf, -rect.area(), int(rotated), ri, pi, pl, pw)
                    if best is None or candidate < best:
                        best = candidate

        if best is None:
            break

        _, _, _, ri, pi, pl, pw = best[3], best[4], best[5], best[3], best[4], best[5], best[6]
        # unpack cleanly
        _bssf, _neg_area, _rot_int, ri, pi, pl, pw = best
        rotated = bool(_rot_int)

        rect = free[ri]
        part = remaining.pop(pi)

        px, py = rect.x, rect.y
        placed.append(PlacedPart(
            part_id=part['id'], name=part.get('name', ''),
            x=px, y=py, length=pl, width=pw, rotated=rotated
        ))

        # Split all free rects that overlap the newly placed area
        placed_rect = Rect(px, py, pl + kerf, pw + kerf)
        new_free = []
        for fr in free:
            if _overlaps(fr, placed_rect):
                if px > fr.x:                              # left strip
                    new_free.append(Rect(fr.x, fr.y, px - fr.x, fr.h))
                right_x = px + pl + kerf
                if right_x < fr.x + fr.w:                 # right strip
                    new_free.append(Rect(right_x, fr.y, fr.x + fr.w - right_x, fr.h))
                if py > fr.y:                              # bottom strip
                    new_free.append(Rect(fr.x, fr.y, fr.w, py - fr.y))
                top_y = py + pw + kerf
                if top_y < fr.y + fr.h:                   # top strip
                    new_free.append(Rect(fr.x, top_y, fr.w, fr.y + fr.h - top_y))
            else:
                new_free.append(fr)

        free = _prune(new_free, kerf)

    return placed, remaining


def _overlaps(a: Rect, b: Rect) -> bool:
    return (a.x < b.x + b.w and a.x + a.w > b.x and
            a.y < b.y + b.h and a.y + a.h > b.y)


def _prune(rects, kerf):
    """Remove rects too small to be useful or fully inside a larger rect."""
    out = []
    for i, r in enumerate(rects):
        if r.w < kerf or r.h < kerf:
            continue
        dominated = any(
            j != i
            and s.x <= r.x and s.y <= r.y
            and s.x + s.w >= r.x + r.w
            and s.y + s.h >= r.y + r.h
            and s.area() > r.area()
            for j, s in enumerate(rects)
        )
        if not dominated:
            out.append(r)
    return out


# ─── Helpers ──────────────────────────────────────────────────────────────────

def expand_parts(parts):
    out = []
    for p in parts:
        for _ in range(p['qty']):
            out.append({'id': p['id'], 'name': p.get('name', ''),
                        'length': p['length'], 'width': p['width']})
    return out


def score_solution(results, unplaced):
    """Lower is better. Priority: fewest unplaced → fewest boards → highest util."""
    avg_util = (sum(r.utilization for r in results) / len(results)) if results else 0
    return (len(unplaced), len(results), -avg_util)


# ─── Solver ───────────────────────────────────────────────────────────────────

def solve(stocks, parts, kerf, allow_rotate, strategy, min_waste=0):
    all_parts = expand_parts(parts)
    if not all_parts or not stocks:
        return [], all_parts

    stock_list = list(stocks)

    # ── Part orderings ────────────────────────────────────────────────────────
    def _sort(key, rev=True): return sorted(all_parts, key=key, reverse=rev)

    if strategy == 'crosscut_first':
        # Favour long pieces (maximise crosscut opportunities)
        base_orders = [
            _sort(lambda p: p['length']),
            _sort(lambda p: p['length'] / max(p['width'], 0.001)),
            _sort(lambda p: p['length'] * p['width']),
        ]
        n_random = 20
    elif strategy == 'ripcut_first':
        # Favour wide pieces (maximise rip opportunities)
        base_orders = [
            _sort(lambda p: p['width']),
            _sort(lambda p: p['width'] / max(p['length'], 0.001)),
            _sort(lambda p: p['length'] * p['width']),
        ]
        n_random = 20
    else:  # combination
        base_orders = [
            _sort(lambda p: p['length'] * p['width']),                        # largest area first
            _sort(lambda p: p['length'] * p['width'], rev=False),             # smallest area first
            _sort(lambda p: p['length']),                                      # longest first
            _sort(lambda p: p['width']),                                       # widest first
            _sort(lambda p: p['length'] + p['width']),                        # largest perimeter first
            _sort(lambda p: max(p['length'], p['width'])),                    # largest dimension first
            _sort(lambda p: min(p['length'], p['width'])),                    # largest min-side first
        ]
        n_random = 50

    random_orders = [random.sample(all_parts, len(all_parts)) for _ in range(n_random)]
    all_orders = base_orders + random_orders

    # ── Stock orderings ───────────────────────────────────────────────────────
    stock_orders = [
        sorted(stock_list, key=lambda s: s['length'] * s['width']),           # smallest first
        sorted(stock_list, key=lambda s: s['length'] * s['width'], reverse=True),
        stock_list,
    ]

    # ── Rotation modes ────────────────────────────────────────────────────────
    # When the user allows rotation, we try BOTH rotation=True and rotation=False
    # so the solver can pick whichever produces the better overall layout.
    # This prevents the packer's local heuristic from choosing a rotated
    # placement that looks good locally but strands pieces later.
    if allow_rotate:
        rotate_modes = [True, False]
    else:
        rotate_modes = [False]

    # ── Trial runner ──────────────────────────────────────────────────────────
    def run_trial(part_order, stock_order, rotate):
        remaining = list(part_order)
        results = []
        for stock in stock_order:
            if not remaining:
                break
            placed, remaining = max_rects_pack(
                stock['length'], stock['width'], remaining, kerf, rotate
            )
            if placed:
                used_area = sum(p.length * p.width for p in placed)
                total_area = stock['length'] * stock['width']
                results.append(StockResult(
                    stock_id=stock['id'],
                    stock_length=stock['length'],
                    stock_width=stock['width'],
                    stock_label=stock.get('label', ''),
                    placed=[asdict(p) for p in placed],
                    waste_area=total_area - used_area,
                    utilization=used_area / total_area * 100,
                ))
        return results, remaining

    # ── Search ────────────────────────────────────────────────────────────────
    best_results  = None
    best_unplaced = all_parts
    best_score    = None
    streak        = 0
    MAX_STREAK    = 15

    for part_order in all_orders:
        for stock_order in stock_orders:
            for rotate in rotate_modes:
                results, unplaced = run_trial(part_order, stock_order, rotate)
                sc = score_solution(results, unplaced)

                if best_score is None or sc < best_score:
                    best_score    = sc
                    best_results  = results
                    best_unplaced = unplaced
                    streak        = 0
                    if not unplaced and len(results) == 1:
                        return best_results, best_unplaced   # perfect: done
                else:
                    streak += 1
                    if streak >= MAX_STREAK:
                        return best_results or [], best_unplaced

    return best_results or [], best_unplaced


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/solve', methods=['POST'])
def solve_route():
    data         = request.json
    stocks       = data.get('stocks', [])
    parts        = data.get('parts', [])
    kerf         = float(data.get('kerf', 0.125))
    allow_rotate = data.get('allow_rotate', True)
    strategy     = data.get('strategy', 'combination')
    min_waste    = float(data.get('min_waste', 1.0))

    if not stocks or not parts:
        return jsonify({'error': 'Need at least one stock board and one part.'}), 400

    results, unplaced = solve(stocks, parts, kerf, allow_rotate, strategy, min_waste)

    return jsonify({
        'results':       [r if isinstance(r, dict) else asdict(r) for r in results],
        'unplaced':      unplaced,
        'total_parts':   sum(p['qty'] for p in parts),
        'placed_count':  sum(len(r['placed'] if isinstance(r, dict) else r.placed)
                             for r in results),
        'unplaced_count': len(unplaced),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
