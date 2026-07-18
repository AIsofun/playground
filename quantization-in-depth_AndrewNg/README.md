#《深入量化》 学习笔记
#课程地址：https://www.deeplearning.ai/short-courses/quantization-in-depth/


About this course
关于本课程

In Quantization in Depth you will build model quantization methods to shrink model weights to ¼ their original size,
and apply methods to maintain the compressed model’s performance. Your ability to quantize your models can make them more accessible, 
and also faster at inference time. 
在《深度量化》中，您将构建模型量化方法，将模型权重压缩至原来的四分之一，并应用方法保持压缩模型的性能。
您对模型进行量化的技能能够使其更易于获取，同时在推理时速度更快。

Implement and customize linear quantization from scratch so that you can study the tradeoff between space and performance, 
and then build a general-purpose quantizer in PyTorch that can quantize any open source model. 
You’ll implement  techniques to compress model weights from 32 bits to 8 bits and even 2 bits.
从零开始实现并自定义线性量化，以便研究空间与性能之间的权衡，然后在 PyTorch 中构建一个通用量化器，能够对任何开源模型进行量化。
您将实现将模型权重从 32 位压缩到 8 位甚至 2 位的技术。

Join this course to:
参加本课程可：

1.Build and customize linear quantization functions, choosing between two “modes”: asymmetric and symmetric;
and three granularities: per-tensor, per-channel, and per-group quantization.
构建并自定义线性量化函数，可在两种“模式”（非对称和对称）以及三种粒度（张量级、通道级和组级量化）之间进行选择；

2.Measure the quantization error of each of these options as you balance the performance and space tradeoffs for each option.
衡量每种选项的量化误差，以平衡每种选项的性能和空间权衡。

3.Build your own quantizer in PyTorch, to quantize any open source model’s dense layers from 32 bits to 8 bits.
在 PyTorch 中构建自己的量化器，将任何开源模型的密集层从 32 位量化到 8 位。

4. Go beyond 8 bits, and pack four 2-bit weights into one 8-bit integer.
突破 8 位，将四个 2 位权重打包到一个 8 位整数中。

Quantization in Depth lets you build and customize your own linear quantizer from scratch, going beyond standard open source libraries such as PyTorch and Quanto, 
which are covered in the short course Quantization Fundamentals, also by Hugging Face.
《深度量化》课程让您从零开始构建和自定义自己的线性量化器，超越了 PyTorch 和 Quanto 等标准开源库，这些内容在 Hugging Face 推出的短期课程《量化基础》中均有介绍。

This course gives you the foundation to study more advanced quantization methods, some of which are recommended at the end of the course.
本课程为您学习更高级的量化方法打下基础，其中一些方法会在课程结束时为您推荐。
