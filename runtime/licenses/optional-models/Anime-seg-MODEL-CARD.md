---
library_name: anime_segmentation
tags:
- image-segmentation
- model_hub_mixin
- pytorch_model_hub_mixin
license: apache-2.0
---

This model has been pushed to the Hub using the [PytorchModelHubMixin](https://huggingface.co/docs/huggingface_hub/package_reference/mixins#huggingface_hub.PyTorchModelHubMixin) integration:
- Library: https://github.com/SkyTNT/anime-segmentation

## How to load the model 
```
wget https://raw.githubusercontent.com/SkyTNT/anime-segmentation/refs/heads/main/train.py
```
```
pip install pytorch_lightning kornia timm "huggingface_hub>=0.22"
```

```python 
from train import AnimeSegmentation
model = AnimeSegmentation.from_pretrained("skytnt/anime-seg")
```