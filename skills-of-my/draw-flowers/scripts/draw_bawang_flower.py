import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Polygon


def tapered_petal(
    angle: float,
    length: float,
    width: float,
    center: tuple[float, float],
    bend: float = 0.0,
    samples: int = 100,
) -> np.ndarray:
    parameter = np.linspace(0.0, 1.0, samples)
    centerline_x = length * parameter
    centerline_y = bend * np.sin(np.pi * parameter)
    half_width = width * np.sin(np.pi * parameter) ** 0.8
    upper = np.column_stack((centerline_x, centerline_y + half_width))
    lower = np.column_stack(
        (centerline_x[::-1], centerline_y[::-1] - half_width[::-1])
    )
    points = np.vstack((upper, lower))
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    return points @ rotation.T + np.asarray(center)


def cactus_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    width: float,
    waves: int = 7,
) -> np.ndarray:
    start_point = np.asarray(start)
    end_point = np.asarray(end)
    direction = end_point - start_point
    length = np.linalg.norm(direction)
    tangent = direction / length
    normal = np.array([-tangent[1], tangent[0]])
    parameter = np.linspace(0.0, 1.0, waves * 2 + 1)
    centerline = start_point + parameter[:, None] * direction
    scallop = width * (0.9 + 0.1 * np.cos(parameter * waves * 2 * np.pi))
    left = centerline + scallop[:, None] * normal
    right = centerline[::-1] - scallop[::-1, None] * normal
    return np.vstack((left, right))


def draw_bawang_flower(output: Path) -> None:
    rng = np.random.default_rng(108)
    figure, ax = plt.subplots(figsize=(8, 8), dpi=200)
    background = "#142321"
    figure.patch.set_facecolor(background)
    ax.set_facecolor(background)

    for start, end, width in [
        ((-3.2, -2.8), (-0.45, -0.55), 0.42),
        ((3.15, -2.55), (0.5, -0.45), 0.38),
    ]:
        segment = cactus_segment(start, end, width)
        ax.add_patch(
            Polygon(
                segment,
                closed=True,
                facecolor="#28754d",
                edgecolor="#65a66b",
                linewidth=2.0,
                zorder=1,
            )
        )

    center = (0.0, 0.15)
    layers = [
        (20, 2.9, 0.2, "#91b94e", 0.2),
        (18, 2.55, 0.3, "#d3e2a4", -0.12),
        (16, 2.15, 0.43, "#f1eed8", 0.09),
        (13, 1.62, 0.48, "#fffdf0", -0.06),
        (10, 1.15, 0.42, "#fffef8", 0.04),
    ]
    for layer_index, (count, length, width, color, bend) in enumerate(layers):
        offset = layer_index * 0.19
        for petal_index in range(count):
            angle = 2 * np.pi * petal_index / count + offset
            angle += rng.normal(0.0, 0.028)
            points = tapered_petal(
                angle,
                length * rng.uniform(0.94, 1.06),
                width * rng.uniform(0.9, 1.08),
                center,
                bend * rng.uniform(0.7, 1.3),
            )
            ax.add_patch(
                Polygon(
                    points,
                    closed=True,
                    facecolor=color,
                    edgecolor="#c8c9a5",
                    linewidth=0.65,
                    alpha=0.98,
                    zorder=3 + layer_index,
                )
            )

    stamen_angles = np.linspace(0.0, 2 * np.pi, 46, endpoint=False)
    for index, angle in enumerate(stamen_angles):
        radius = 0.35 + 0.32 * (index % 4) / 3
        start_x = center[0] + 0.18 * np.cos(angle)
        start_y = center[1] + 0.18 * np.sin(angle)
        end_x = center[0] + radius * np.cos(angle)
        end_y = center[1] + radius * np.sin(angle)
        ax.plot(
            [start_x, end_x],
            [start_y, end_y],
            color="#f3d66b",
            linewidth=1.0,
            zorder=10,
        )
        ax.add_patch(
            Circle(
                (end_x, end_y),
                radius=0.045,
                facecolor="#f5c64f",
                edgecolor="#b98a2f",
                linewidth=0.35,
                zorder=11,
            )
        )

    stigma_angles = np.linspace(0.0, 2 * np.pi, 12, endpoint=False)
    ax.scatter(
        center[0] + 0.2 * np.cos(stigma_angles),
        center[1] + 0.2 * np.sin(stigma_angles),
        s=28,
        color="#eaf0b0",
        edgecolor="#8da657",
        linewidth=0.4,
        zorder=12,
    )

    ax.set_xlim(-3.35, 3.35)
    ax.set_ylim(-3.15, 3.35)
    ax.set_aspect("equal")
    ax.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight", pad_inches=0.12, facecolor=background)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a night-blooming pitaya flower.")
    parser.add_argument("output", type=Path, help="Destination PNG path")
    args = parser.parse_args()
    draw_bawang_flower(args.output)


if __name__ == "__main__":
    main()