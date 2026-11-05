"""Native forward, native weight loading, lossless checkpoint prefix mapping."""
from vllm.model_executor.models.qwen3_5 import (
    Qwen3_5ForCausalLM,
    Qwen3_5ForConditionalGeneration,
)
import torch


class TMaxTextForCausalLM(Qwen3_5ForCausalLM):
    is_hybrid = True
    supports_mrope = True
    get_mamba_state_dtype_from_config = classmethod(
        Qwen3_5ForConditionalGeneration.get_mamba_state_dtype_from_config.__func__
    )
    get_mamba_state_shape_from_config = classmethod(
        Qwen3_5ForConditionalGeneration.get_mamba_state_shape_from_config.__func__
    )
    get_mamba_state_copy_func = classmethod(
        Qwen3_5ForConditionalGeneration.get_mamba_state_copy_func.__func__
    )

    def load_weights(self, weights):
        def canonical():
            prefix = "model.language_model."
            for name, tensor in weights:
                if not name.startswith(prefix):
                    raise ValueError("Unexpected M2 checkpoint tensor prefix: " + name)
                yield "model." + name[len(prefix):], tensor
        return super().load_weights(canonical())

    def get_mrope_input_positions(self, input_tokens, mm_features):
        if mm_features:
            raise ValueError("This TMax checkpoint is text-only")
        # Native Qwen text-only M-RoPE: identical positions on all three axes.
        return torch.arange(len(input_tokens), dtype=torch.long).expand(3, -1).contiguous(), 0
