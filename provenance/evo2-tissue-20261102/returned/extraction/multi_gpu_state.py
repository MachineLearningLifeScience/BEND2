"""Explicit, local TE 2.18 state-placement adapter; vendor sources stay frozen.

TE's recipe-state rebuild inherits the old tensors, including their old device.
Restoring under a CUDA context alone therefore cannot repair misplaced state.
Rebuild both the recipe state and its quantizers on the destination device, then
let TE copy the serialized checkpoint values into them. Never reset FP8 values.
"""
import functools


def install():
    import torch
    from transformer_engine.pytorch.module.base import TransformerEngineBaseModule

    cls = TransformerEngineBaseModule
    if getattr(cls, "_evo2_device_restore", False):
        return
    original_set = cls.set_extra_state
    original_get = cls.get_extra_state

    def state_device(module):
        device = next(module.parameters()).device
        if device.type == "cuda":
            return device
        # The unused tail blocks are offloaded after the short controls. Their
        # FP8 metadata stays on its original GPU and must still round-trip.
        for key in ("scaling_fwd", "scaling_bwd"):
            state = module.fp8_meta.get(key)
            if state is not None and hasattr(state, "scale"):
                return state.scale.device
        raise RuntimeError("Cannot determine device for offloaded TE state")

    @functools.wraps(original_get)
    def get_extra_state(self):
        with torch.cuda.device(state_device(self)):
            return original_get(self)

    @functools.wraps(original_set)
    def set_extra_state(self, value):
        if value is None or (isinstance(value, torch.Tensor) and value.numel() == 0):
            return original_set(self, value)
        device = state_device(self)
        misplaced = any(
            getattr(self.fp8_meta.get(key), attr, torch.empty(0, device=device)).device != device
            for key in ("scaling_fwd", "scaling_bwd")
            for attr in ("scale", "amax_history")
        )
        with torch.cuda.device(device):
            if misplaced:
                for key in ("scaling_fwd", "scaling_bwd"):
                    self.fp8_meta.pop(key, None)
                    self.quantizers[key] = []
                self.fp8_meta_tensors_initialized = False
            original_set(self, value)
            for key in ("scaling_fwd", "scaling_bwd"):
                state = self.fp8_meta.get(key)
                if state is not None and hasattr(state, "scale"):
                    for attr in ("scale", "amax_history"):
                        if getattr(state, attr).device != device:
                            raise RuntimeError(f"TE {key}.{attr} restored to wrong device")

    cls.get_extra_state = get_extra_state
    cls.set_extra_state = set_extra_state
    cls._evo2_device_restore = True
