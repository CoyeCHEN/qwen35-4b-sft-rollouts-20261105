# 已有数值参考的覆盖范围
+
+PUBLIC_LF_TRL_GA_ADAMW_CPU_GOLDEN是小型合成Qwen混合模型、FP32 CPU、DP1/GA2，只验Loss/GA/AdamW代数，不是4B长序列实测。
+
+ACTUAL_4B_PUBLIC_FP32_LOSS_GRADIENT_CPU来自NEW-M1 E5真实权重：文本Token 3928，collated Token 4000，监督Token 91，计算FP32 CPU, public Torch eager attention and native Gated DeltaNet fallback；原优化更新次数0。完整逐参数梯度摘要与独立手工CE原结果在01，脚本在本目录。不是GPU融合内核/ZeRO长序列等价性的证据。本轮没有重跑这些测试。
+