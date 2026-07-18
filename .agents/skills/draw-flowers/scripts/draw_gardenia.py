import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, Polygon


def petal_points(
    angle: float,
    length: float,
    width: float,
    center: tuple[float, float],
    samples: int = 120,
) -> np.ndarray:
    parameter = np.linspace(0.0, np.pi, samples)
    radius = length * np.sin(parameter / 2) ** 0.82
    taper = width * np.sin(parameter) ** 0.72
    local_x = radius
    local_y = taper * np.sin(np.linspace(0.0, np.pi, samples))
    outline_x = np.concatenate((local_x, local_x[::-1]))
    outline_y = np.concatenate((local_y, -local_y[::-1]))
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    points = np.column_stack((outline_x, outline_y)) @ rotation.T
    return points + np.asarray(center)


def add_leaf(ax: plt.Axes, center: tuple[float, float], angle: float, size: float) -> None:
    leaf = Ellipse(
        center,
        width=1.8 * size,
        height=0.68 * size,
        angle=np.degrees(angle),
        facecolor="#245b34",
        edgecolor="#163d24",
        linewidth=2.0,
        zorder=1,
    )
    ax.add_patch(leaf)
    direction = np.array([np.cos(angle), np.sin(angle)]) * size * 0.82
    ax.plot(
        [center[0] - direction[0], center[0] + direction[0]],
        [center[1] - direction[1], center[1] + direction[1]],
        color="#86a96e",
        linewidth=1.4,
        alpha=0.8,
        zorder=2,
    )


def draw_gardenia(output: Path) -> None:
    rng = np.random.default_rng(24)
    figure, ax = plt.subplots(figsize=(8, 8), dpi=200)
    figure.patch.set_facecolor("#dce8d5")
    ax.set_facecolor("#dce8d5")

    for center, angle, size in [
        ((-1.55, -0.55), 2.65, 2.5),
        ((1.45, -0.75), 0.48, 2.65),
        ((-0.95, 1.05), 2.0, 2.1),
        ((1.1, 1.15), 1.0, 2.0),
    ]:
        add_leaf(ax, center, angle, size)

    layers = [
        (13, 2.35, 0.72, "#f2f0df"),
        (11, 1.78, 0.62, "#faf8e9"),
        (9, 1.28, 0.49, "#fffdf2"),
        (7, 0.88, 0.36, "#fffef8"),
    ]
    for layer_index, (count, length, width, color) in enumerate(layers):
        offset = layer_index * 0.31
        for petal_index in range(count):
            angle = 2 * np.pi * petal_index / count + offset
            angle += rng.normal(0.0, 0.035)
            points = petal_points(
                angle,
                length * rng.uniform(0.94, 1.06),
                width * rng.uniform(0.92, 1.08),
                (0.0, 0.0),
            )
            petal = Polygon(
                points,
                closed=True,
                facecolor=color,
                edgecolor="#d8d4bd",
                linewidth=0.8,
                alpha=0.98,
                zorder=3 + layer_index,
            )
            ax.add_patch(petal)

    center_angles = np.linspace(0, 2 * np.pi, 18, endpoint=False)
    for index, angle in enumerate(center_angles):
        radius = 0.08 + 0.18 * (index / len(center_angles))
        ax.scatter(
            radius * np.cos(angle),
            radius * np.sin(angle),
            s=28,
            color="#e6c96b",
            edgecolor="#b8943f",
            linewidth=0.35,
            zorder=8,
        )

    ax.set_xlim(-3.25, 3.25)
    ax.set_ylim(-3.15, 3.15)
    ax.set_aspect("equal")
    ax.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, bbox_inches="tight", pad_inches=0.15, facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a layered white gardenia.")
    parser.add_argument("output", type=Path, help="Destination PNG path")
    args = parser.parse_args()
    draw_gardenia(args.output)


if __name__ == "__main__":
    main()