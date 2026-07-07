import numpy as np
from itertools import product

from config import (
    COLS,
    GRID_GEOMETRY_ANCHOR_WEIGHT,
    GRID_GEOMETRY_MAX_ERROR_RATIO,
    GRID_MEMORY_MAX_DISTANCE_RATIO,
    GRID_MEMORY_MIN_HOLES,
    GRID_MEMORY_PARTIAL_MAX_HOLES,
    GRID_MEMORY_SMOOTHING,
    ROWS,
    TOP_ROW_SIZE_RATIO,
)


row_centers = None
column_centers = None
grid_anchors = {}


def reset_grid_memory():
    global row_centers, column_centers

    row_centers = None
    column_centers = None
    grid_anchors.clear()


def grid_memory_count():
    return len(grid_anchors)


def group_rows_by_y(holes):
    sorted_holes = sorted(holes, key=lambda h: h["cy"])

    if len(sorted_holes) == 0:
        return []

    rows = []
    median_h = np.median([h["box"][3] - h["box"][1] for h in sorted_holes])
    row_threshold = max(20, median_h * 0.55)

    for hole in sorted_holes:
        placed = False

        for row in rows:
            row_center = sum(h["cy"] for h in row) / len(row)

            if abs(hole["cy"] - row_center) < row_threshold:
                row.append(hole)
                placed = True
                break

        if not placed:
            rows.append([hole])

    rows.sort(key=lambda row: sum(h["cy"] for h in row) / len(row))
    return rows[:ROWS]


def row_avg_height(row):
    return np.mean([h["box"][3] - h["box"][1] for h in row])


def first_visible_row_is_top(rows):
    if len(rows) < 2:
        return False

    row_heights = [row_avg_height(row) for row in rows]
    max_h = max(row_heights)
    return row_heights[0] < max_h * TOP_ROW_SIZE_RATIO


def estimate_row_offset(rows):
    if len(rows) == 0 or len(rows) >= ROWS:
        return 0

    if first_visible_row_is_top(rows):
        return 0

    return ROWS - len(rows)


def cluster_axis(values, threshold):
    clusters = []

    for value in sorted(values):
        placed = False

        for cluster in clusters:
            center = sum(cluster) / len(cluster)

            if abs(value - center) < threshold:
                cluster.append(value)
                placed = True
                break

        if not placed:
            clusters.append([value])

    return [sum(cluster) / len(cluster) for cluster in clusters]


def update_column_centers(holes):
    global column_centers

    if len(holes) == 0:
        return column_centers

    median_w = np.median([h["box"][2] - h["box"][0] for h in holes])
    centers = cluster_axis([h["cx"] for h in holes], max(25, median_w * 0.8))

    if len(centers) >= COLS:
        column_centers = sorted(centers)[:COLS]

    return column_centers


def update_row_centers(rows):
    global row_centers

    if len(rows) < 3:
        return row_centers

    visible_centers = [sum(h["cy"] for h in row) / len(row) for row in rows]

    if len(visible_centers) >= ROWS:
        row_centers = visible_centers[:ROWS]
        return row_centers

    gap_1 = visible_centers[1] - visible_centers[0]
    gap_2 = visible_centers[2] - visible_centers[1]

    if first_visible_row_is_top(rows):
        row_centers = [
            visible_centers[0],
            visible_centers[1],
            visible_centers[2],
            visible_centers[2] + gap_2,
        ]
    else:
        row_centers = [
            visible_centers[0] - gap_1,
            visible_centers[0],
            visible_centers[1],
            visible_centers[2],
        ]

    return row_centers


def estimate_row_indices(rows):
    centers = update_row_centers(rows)

    if first_visible_row_is_top(rows):
        return list(range(len(rows)))

    if centers is not None and len(centers) == ROWS:
        used = set()
        indices = []

        for row in rows:
            row_center = sum(h["cy"] for h in row) / len(row)
            best_index = None
            best_dist = None

            for i, center in enumerate(centers):
                if i in used:
                    continue

                dist = abs(row_center - center)

                if best_dist is None or dist < best_dist:
                    best_index = i
                    best_dist = dist

            if best_index is None:
                best_index = min(range(ROWS), key=lambda i: abs(row_center - centers[i]))

            used.add(best_index)
            indices.append(best_index)

        return indices

    row_offset = estimate_row_offset(rows)
    return [min(visible_row + row_offset, ROWS - 1) for visible_row in range(len(rows))]


def estimate_col_indices(row_holes, frame_width):
    centers = update_column_centers(row_holes)

    if centers is not None and len(centers) == COLS:
        used = set()
        indices = []

        for hole in row_holes:
            best_index = None
            best_dist = None

            for i, center in enumerate(centers):
                if i in used:
                    continue

                dist = abs(hole["cx"] - center)

                if best_dist is None or dist < best_dist:
                    best_index = i
                    best_dist = dist

            if best_index is None:
                best_index = min(range(COLS), key=lambda i: abs(hole["cx"] - centers[i]))

            used.add(best_index)
            indices.append(best_index)

        return indices

    if len(row_holes) == 3:
        return [0, 1, 2]

    if len(row_holes) == 2:
        avg_x = sum(h["cx"] for h in row_holes) / 2
        col_offset = 0 if avg_x < frame_width / 2 else 1
        return [col_offset, col_offset + 1]

    if len(row_holes) == 1:
        x = row_holes[0]["cx"]

        if x < frame_width / 3:
            return [0]
        if x < frame_width * 2 / 3:
            return [1]
        return [2]

    return []


def anchor_max_distance(holes):
    if len(holes) == 0:
        return 0

    diagonals = []

    for hole in holes:
        x1, y1, x2, y2 = hole["box"]
        diagonals.append(np.hypot(x2 - x1, y2 - y1))

    return max(20, np.median(diagonals) * GRID_MEMORY_MAX_DISTANCE_RATIO)


def update_grid_anchors(holes):
    unique_ids = {hole.get("id") for hole in holes if hole.get("id") is not None}

    if len(unique_ids) < GRID_MEMORY_MIN_HOLES:
        return

    for hole in holes:
        hole_id = hole.get("id")

        if hole_id is None:
            continue

        point = np.array([hole["cx"], hole["cy"]], dtype=np.float32)

        if hole_id in grid_anchors:
            grid_anchors[hole_id] = (
                grid_anchors[hole_id] * (1.0 - GRID_MEMORY_SMOOTHING)
                + point * GRID_MEMORY_SMOOTHING
            )
        else:
            grid_anchors[hole_id] = point


def assign_ids_from_memory(holes):
    if len(holes) == 0 or len(grid_anchors) == 0:
        return None

    max_distance = anchor_max_distance(holes)
    used_ids = set()
    result = []

    for hole in holes:
        best_id = None
        best_distance = None

        for hole_id, anchor in grid_anchors.items():
            if hole_id in used_ids:
                continue

            distance = float(np.linalg.norm(np.array([hole["cx"], hole["cy"]]) - anchor))

            if best_distance is None or distance < best_distance:
                best_id = hole_id
                best_distance = distance

        if best_id is None or best_distance > max_distance:
            return None

        hole["id"] = best_id
        hole["memory_match_distance"] = best_distance
        used_ids.add(best_id)
        result.append(hole)

    result.sort(key=lambda h: h["id"])
    return result


def hole_size_scale(holes):
    if len(holes) == 0:
        return 1

    diagonals = []

    for hole in holes:
        x1, y1, x2, y2 = hole["box"]
        diagonals.append(np.hypot(x2 - x1, y2 - y1))

    return max(1, float(np.median(diagonals)))


def fit_affine(canonical_points, image_points):
    if len(canonical_points) < 3:
        return None, None

    a = []
    b = []

    for (col, row), (x, y) in zip(canonical_points, image_points):
        a.append([col, row, 1, 0, 0, 0])
        a.append([0, 0, 0, col, row, 1])
        b.append(x)
        b.append(y)

    coeffs, _, _, _ = np.linalg.lstsq(
        np.array(a, dtype=np.float32),
        np.array(b, dtype=np.float32),
        rcond=None,
    )

    predicted = []

    for col, row in canonical_points:
        x = coeffs[0] * col + coeffs[1] * row + coeffs[2]
        y = coeffs[3] * col + coeffs[4] * row + coeffs[5]
        predicted.append((x, y))

    return coeffs, predicted


def geometry_assignment_score(assignment, holes):
    canonical_points = []
    image_points = []

    for hole, hole_id in zip(holes, assignment):
        zero_based = hole_id - 1
        row = zero_based // COLS
        col = zero_based % COLS
        canonical_points.append((col, row))
        image_points.append((hole["cx"], hole["cy"]))

    _, predicted = fit_affine(canonical_points, image_points)

    if predicted is None:
        return None

    scale = hole_size_scale(holes)
    geometry_error = np.mean([
        np.linalg.norm(np.array(actual) - np.array(expected)) / scale
        for actual, expected in zip(image_points, predicted)
    ])

    anchor_error = 0.0
    anchor_count = 0

    for hole, hole_id in zip(holes, assignment):
        if hole_id not in grid_anchors:
            continue

        anchor_error += (
            np.linalg.norm(np.array([hole["cx"], hole["cy"]]) - grid_anchors[hole_id])
            / scale
        )
        anchor_count += 1

    if anchor_count > 0:
        anchor_error /= anchor_count

    return geometry_error + anchor_error * GRID_GEOMETRY_ANCHOR_WEIGHT


def row_start_candidates(row_holes):
    count = len(row_holes)

    if count <= 0 or count > COLS:
        return []

    return list(range(COLS - count + 1))


def geometry_assignments_for_rows(rows):
    if len(rows) == 0:
        return []

    row_start_options = list(range(ROWS - len(rows) + 1))
    if first_visible_row_is_top(rows):
        row_start_options = [0]

    col_start_options = [row_start_candidates(row) for row in rows]

    if any(len(options) == 0 for options in col_start_options):
        return []

    assignments = []

    for row_start in row_start_options:
        for col_starts in product(*col_start_options):
            ids = []

            for visible_row, (row_holes, col_start) in enumerate(zip(rows, col_starts)):
                row_index = row_start + visible_row

                for col_offset in range(len(row_holes)):
                    col_index = col_start + col_offset
                    ids.append(row_index * COLS + col_index + 1)

            assignments.append(ids)

    return assignments


def assign_ids_by_geometry(holes):
    if len(holes) < 4:
        return None

    rows = group_rows_by_y(holes)
    ordered_holes = []

    for row in rows:
        row.sort(key=lambda h: h["cx"])
        ordered_holes.extend(row)

    assignments = geometry_assignments_for_rows(rows)

    if len(assignments) == 0:
        return None

    best_assignment = None
    best_score = None

    for assignment in assignments:
        score = geometry_assignment_score(assignment, ordered_holes)

        if score is None:
            continue

        if best_score is None or score < best_score:
            best_score = score
            best_assignment = assignment

    if best_assignment is None:
        return None

    if best_score > GRID_GEOMETRY_MAX_ERROR_RATIO:
        return None

    result = []

    for hole, hole_id in zip(ordered_holes, best_assignment):
        hole["id"] = hole_id
        hole["id_mode"] = "geometry"
        hole["geometry_score"] = best_score
        result.append(hole)

    result.sort(key=lambda h: h["id"])
    return result


def assign_ids_by_layout(holes, frame_width):
    if len(holes) == 0:
        return []

    rows = group_rows_by_y(holes)
    row_indices = estimate_row_indices(rows)
    update_column_centers(holes)
    result = []

    for row_index, row_holes in zip(row_indices, rows):
        row_index = min(row_index, ROWS - 1)
        row_holes.sort(key=lambda h: h["cx"])
        col_indices = estimate_col_indices(row_holes, frame_width)

        for hole, col_index in zip(row_holes, col_indices):
            col_index = min(col_index, COLS - 1)
            hole["id"] = row_index * COLS + col_index + 1
            hole["id_mode"] = "layout"
            result.append(hole)

    result.sort(key=lambda h: h["id"])
    return result


def assign_ids(holes, frame_width):
    if len(holes) <= GRID_MEMORY_PARTIAL_MAX_HOLES:
        geometry_result = assign_ids_by_geometry(holes)

        if geometry_result is not None:
            return geometry_result

        memory_result = assign_ids_from_memory(holes)

        if memory_result is not None:
            for hole in memory_result:
                hole["id_mode"] = "memory"

            return memory_result

    layout_result = assign_ids_by_layout(holes, frame_width)
    update_grid_anchors(layout_result)
    return layout_result
