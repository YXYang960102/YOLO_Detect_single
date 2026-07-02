import numpy as np

from config import (
    COLS,
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
            result.append(hole)

    result.sort(key=lambda h: h["id"])
    return result


def assign_ids(holes, frame_width):
    if len(holes) <= GRID_MEMORY_PARTIAL_MAX_HOLES:
        memory_result = assign_ids_from_memory(holes)

        if memory_result is not None:
            return memory_result

    layout_result = assign_ids_by_layout(holes, frame_width)
    update_grid_anchors(layout_result)
    return layout_result
