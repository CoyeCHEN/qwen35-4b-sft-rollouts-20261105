# Modified initial environment: restores only dependencies promised in instruction.md.
# Supply the official immutable RepoDigest as BASE_IMAGE; never retag its image.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep fd-find && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      torch==2.5.1+cpu torchvision==0.20.1+cpu --index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
      numpy==1.26.4 pandas==2.2.3 scipy==1.13.1 timm==0.9.12 \
      opencv-python-headless==4.10.0.84 Pillow==10.4.0 tqdm==4.67.1
# Source archive fetched separately with a recorded SHA256; fixed Git revision,
# never an empty Releases HTML page. COPY contains source only, no task answers.
COPY MobileSAM-34bbbfdface3c18e5221aa7de6032d7220c6c6a1.tar.gz /tmp/mobile-sam.tar.gz
RUN python -m pip install --no-cache-dir --no-deps /tmp/mobile-sam.tar.gz && rm /tmp/mobile-sam.tar.gz \
 && python -c 'import torch, torchvision, mobile_sam, cv2, numpy, pandas; from torchvision.ops import nms; nms(torch.tensor([[0.,0.,1.,1.]]),torch.tensor([1.]),0.5); print(torch.__version__)' \
 && python -m pip freeze > /opt/harbor-promised-dependencies.txt
