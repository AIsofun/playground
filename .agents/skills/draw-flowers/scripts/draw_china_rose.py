import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon


def petal_points(
    angle: float,
    length: float,
    width: float,
    curl: float,
    samples: int = 100,
) -> np.ndarray:
    parameter = np.linspace(0.0, 1.0, samples)
    centerline = length * parameter
    half_width = width * np.sin(np.pi * parameter) ** 0.7
    ruffle = 1.0 + 0.08 * np.sin(5 * np.pi * parameter + curl)
    upper = np.column_stack((centerline, half_width * ruffle))
    lower = np.column_stack((centerline[::-1], -half_width[::-1] * ruffle[::-1]))
    points = np.vstack((upper, lower))
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    return points @ rotation.T


def serrated_leaf(
    center: tuple[float, float], angle: float, length: float, width: float
) -> np.ndarray:
    steps = 12
    x = np.linspace(-length / 2, length / 2, steps * 2 + 1)
    envelope = width * (1.0 - (2.0 * x / length) ** 2) ** 0.72
    teeth = np.where(np.arange(x.size) % 2 == 0, 1.0, 0.76)
    upper = np.column_stack((x, envelope * teeth))
    lower = np.column_stack((x[::-1], -envelope[::-1] * teeth[::-1]))
    points = np.vstack((upper, lower))
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    return points @ rotation.T + np.asarray(center)


def add_leaf(
    ax: plt.Axes, center: tuple[float, float], angle: float, length: float
) -> None:
    points = serrated_leaf(center, angle, length, length * 0.2)
    ax.add_patch(
        Polygon(
            points,
            closed=True,
            facecolor="#2f713f",
            edgecolor="#174a2a",
            linewidth=1.5,
            zorder=2,
        )
    )
    direction = np.array([np.cos(angle), np.sin(angle)]) * length * 0.47
    ax.plot(
        [center[0] - direction[0], center[0] + direction[0]],
        [center[1] - direction[1], center[1] + direction[1]],
        color="#a4bd78",
        linewidth=1.0,
        zorder=3,
    )


def draw_china_rose(output: Path) -> None:
    rng = np.random.default_rng(86)
    figure, ax = plt.subplots(figsize=(8, 8), dpi=200)
    background = "#f3e7df"
    figure.patch.set_facecolor(background)
    ax.set_facecolor(background)

    stem_x = np.array([0.05, -0.05, 0.08, -0.02])
    stem_y = np.array([-3.2, -2.25, -1.35, -0.55])
    ax.plot(stem_x, stem_y, color="#285f35", linewidth=8, solid_capstyle="round", zorder=1)
    for center, angle, length in [
        ((-0.85, -2.45), 2.85, 1.75),
        ((0.9, -2.15), 0.35, 1.8),
        ((-1.05, -1.45), 2.65, 1.55),
        ((1.05, -1.1), 0.55, 1.45),
    ]:
        add_leaf(ax, center, angle, length)

    layers = [
        (15, 2.45, 0.72, "#c92f5b"),
        (13, 1.95, 0.66, "#dc3f6b"),
        (11, 1.48, 0.56, "#e95579"),
        (9, 1.02, 0.43, "#f06a88"),
        (7, 0.65, 0.3, "#f58ba0"),
    ]
    flower_center = np.array([0.0, 0.55])
    for layer_index, (count, length, width, color) in enumerate(layers):
        offset = 0.24 * layer_index
        for petal_index in range(count):
            angle = 2 * np.pi * petal_index / count + offset
            angle += rng.normal(0.0, 0.045)
            points = petal_points(
                angle,
                length * rng.uniform(0.92, 1.06),
                width * rng.uniform(0.9, 1.1),
                rng.uniform(0.0, 2 * np.pi),
            )
            points += flower_center
            ax.add_patch(
                Polygon(
                    points,
                    closed=True,
                    facecolor=color,
                    edgecolor="#9f2449",
                    linewidth=0.75,
                    alpha=0.97,
                    zorder=4 + layer_index,
                )
            )

    center_angles = np.linspace(0.0, 4.5 * np.pi, 38)
    center_radius = np.linspace(0.03, 0.31, center_angles.size)
    ax.scatter(
        flower_center[0] + center_radius * np.cos(center_angles),
        flower_center[1] + center_radius * np.sin(center_angles),
        s=np.linspace(16, 34, center_angles.size),
        color="#f4c861",
        edgecolor="#b57b2f",
        linewidth=0.35,
        zorder=11,
    )

    ax.set_xlim(-3.15, 3.15)
    ax.set_ylim(-3.35, 3.5)
    ax.set_aspect("equal")
    ax.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight", pad_inches=0.12, facecolor=background)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a layered pink Chinese rose.")
    parser.add_argument("output", type=Path, help="Destination PNG path")
    args = parser.parse_args()
    draw_china_rose(args.output)


if __name__ == "__main__":
    main()