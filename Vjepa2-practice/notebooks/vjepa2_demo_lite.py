# 轻量版 V-JEPA 2 demo：只加载 PyTorch 版编码器（不加载 HuggingFace 版），
# 使用 bf16 半精度推理，适合 8GB 显存的显卡。
# 运行方式（仓库根目录）：python -m notebooks.vjepa2_demo_lite

import json
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
from decord import VideoReader

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

import src.datasets.utils.video.transforms as video_transforms
import src.datasets.utils.video.volume_transforms as volume_transforms
from src.models.attentive_pooler import AttentiveClassifier
from src.models.vision_transformer import vit_giant_xformers_rope

IMAGENET_DEFAULT_MEAN = (0.485, 0.456, 0.406)
IMAGENET_DEFAULT_STD = (0.229, 0.224, 0.225)

PT_MODEL_PATH = "ptdir/vitg-384.pt"
CLASSIFIER_PATH = "ptdir/ssv2-vitg-384-64x2x3.pt"
VIDEO_PATH = "ptdir/sample_video.mp4"
CLASSES_PATH = "ptdir/something-something-v2-id2label.json"
IMG_SIZE = 384
NUM_FRAMES = 64


def build_pt_video_transform(img_size):
    short_side_size = int(256.0 / 224 * img_size)
    return video_transforms.Compose(
        [
            video_transforms.Resize(short_side_size, interpolation="bilinear"),
            video_transforms.CenterCrop(size=(img_size, img_size)),
            volume_transforms.ClipToTensor(),
            video_transforms.Normalize(mean=IMAGENET_DEFAULT_MEAN, std=IMAGENET_DEFAULT_STD),
        ]
    )


def main():
    assert torch.cuda.is_available(), "需要 CUDA GPU"
    device = "cuda"

    print(f"[1/5] 读取视频 {VIDEO_PATH} ...")
    vr = VideoReader(VIDEO_PATH)
    frame_idx = np.linspace(0, len(vr) - 1, NUM_FRAMES).astype(int)
    video = vr.get_batch(frame_idx).asnumpy()  # T x H x W x C
    print(f"      视频共 {len(vr)} 帧，采样 {len(frame_idx)} 帧")

    print("[2/5] 构建模型并加载权重（bf16）...")
    model = vit_giant_xformers_rope(img_size=(IMG_SIZE, IMG_SIZE), num_frames=NUM_FRAMES)
    print("      模型已构建，转 bf16 并搬到 GPU ...")
    model = model.to(dtype=torch.bfloat16).to(device).eval()
    print("      mmap 流式加载权重 ...")
    state = torch.load(PT_MODEL_PATH, weights_only=True, map_location="cpu", mmap=True)["encoder"]
    state = {k.replace("module.", "").replace("backbone.", ""): v for k, v in state.items()}
    msg = model.load_state_dict(state, strict=False)
    print(f"      编码器权重加载: {msg}")
    del state

    print("[3/5] 预处理视频 ...")
    transform = build_pt_video_transform(IMG_SIZE)
    x = torch.from_numpy(video).permute(0, 3, 1, 2)  # T x C x H x W
    x = transform(x).unsqueeze(0).to(device, dtype=torch.bfloat16)
    print(f"      输入张量: {tuple(x.shape)}")

    print("[4/5] 编码器推理 ...")
    with torch.inference_mode():
        features = model(x)
    print(f"      特征输出: {tuple(features.shape)}")

    print("[5/5] 分类器推理 ...")
    classifier = AttentiveClassifier(embed_dim=model.embed_dim, num_heads=16, depth=4, num_classes=174)
    cls_state = torch.load(CLASSIFIER_PATH, weights_only=True, map_location="cpu")["classifiers"][0]
    cls_state = {k.replace("module.", ""): v for k, v in cls_state.items()}
    msg = classifier.load_state_dict(cls_state, strict=False)
    print(f"      分类器权重加载: {msg}")
    classifier = classifier.to(device, dtype=torch.bfloat16).eval()

    with torch.inference_mode():
        logits = classifier(features)

    classes = json.load(open(CLASSES_PATH, "r", encoding="utf-8"))
    top5 = logits.float().topk(5)
    probs = F.softmax(top5.values[0], dim=-1) * 100.0
    print("\nTop 5 预测类别:")
    for idx, prob in zip(top5.indices[0], probs):
        print(f"  {classes[str(idx.item())]} ({prob:.1f}%)")


if __name__ == "__main__":
    main()
