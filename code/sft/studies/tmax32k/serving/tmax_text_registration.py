def register():
    from vllm import ModelRegistry
    ModelRegistry.register_model("Qwen3_5ForCausalLM", "tmax_text_model:TMaxTextForCausalLM")
