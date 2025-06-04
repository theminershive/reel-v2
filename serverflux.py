#!/usr/bin/env python3
import os
import logging
import torch
import pynvml
from diffusers import FluxPipeline
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from io import BytesIO
from fastapi.responses import StreamingResponse
from PIL import Image

# ── PyTorch Memory Tweaks ─────────────────────────────────────────────────────
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = (
    "expandable_segments:True,"
    "max_split_size_mb:64,"
    "garbage_collection_threshold:0.6"
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flux-server")

# ── GPU Detection ─────────────────────────────────────────────────────────────
pynvml.nvmlInit()
gpus = []
for i in range(pynvml.nvmlDeviceGetCount()):
    h = pynvml.nvmlDeviceGetHandleByIndex(i)
    free = pynvml.nvmlDeviceGetMemoryInfo(h).free / 1024**3
    name = pynvml.nvmlDeviceGetName(h)
    gpus.append((i, free))
    logger.info(f"[GPU {i}] {name} — Free {free:.2f} GB")

gpus.sort(key=lambda x: x[1], reverse=True)
flux_gpu = gpus[0][0]
DEVICE_FLUX = torch.device(f"cuda:{flux_gpu}")
logger.info(f"Flux pipeline will use GPU {flux_gpu} (with CPU offload)")

# ── Model Load at Startup ────────────────────────────────────────────────────
logger.info("Loading Flux pipeline…")
pipe: FluxPipeline = FluxPipeline.from_pretrained(
    "models/FLUX.1-dev",
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
    use_safetensors=True,
)
pipe.enable_attention_slicing()
pipe.enable_model_cpu_offload()
logger.info("✔ Flux pipeline loaded and offloaded")

# ── FastAPI Setup ─────────────────────────────────────────────────────────────
app = FastAPI(title="Flux Fast-Load API")

class GenerationRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    guidance_scale: float = 4.5
    num_inference_steps: int = 50
    enhance: bool = False  # reserved flag for future ESRGAN

@app.post("/generate")
async def generate(req: GenerationRequest):
    try:
        logger.info(
            f"Generating: prompt={req.prompt!r}, size={req.width}×{req.height}, "
            f"steps={req.num_inference_steps}, scale={req.guidance_scale}, enhance={req.enhance}"
        )
        out = pipe(
            req.prompt,
            width=req.width,
            height=req.height,
            guidance_scale=req.guidance_scale,
            num_inference_steps=req.num_inference_steps,
        )
        img = out.images[0]

        if req.enhance:
            logger.warning("Enhance flag set, but enhancement is not yet implemented. Returning base image.")

        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")

    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting server on 0.0.0.0:8001")
    uvicorn.run("server:app", host="0.0.0.0", port=8001, log_level="info")
