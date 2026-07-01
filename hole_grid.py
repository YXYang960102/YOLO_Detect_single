import numpy as np

from config import COLS, ROWS, TOP_ROW_SIZE_RATIO


column_centers = None


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


def estimate_row_offset(rows):
    if len(rows) == 0 or len(rows) >= ROWS:
        return 0

    row_heights = []

    for row in rows:
        avg_h = np.mean([h["box"][3] - h["box"][1] for h in row])
        row_heights.append(avg_h)

    max_h = max(row_heights)
    first_row_is_small = row_heights[0] < max_h * TOP_ROW_SIZE_RATIO

    if first_row_is_small:
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


def assign_ids(holes, frame_width):
    if len(holes) == 0:
        return []

    rows = group_rows_by_y(holes)
    row_offset = estimate_row_offset(rows)
    update_column_centers(holes)
    result = []

    for visible_row, row_holes in enumerate(rows):
        row_index = min(visible_row + row_offset, ROWS - 1)
        row_holes.sort(key=lambda h: h["cx"])
        col_indices = estimate_col_indices(row_holes, frame_width)

        for hole, col_index in zip(row_holes, col_indices):
            col_index = min(col_index, COLS - 1)
            hole["id"] = row_index * COLS + col_index + 1
            result.append(hole)

    result.sort(key=lambda h: h["id"])
    return result
