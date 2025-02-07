# Copyright (C) 2023-2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Common functionality.
"""
import logging
import os
from pathlib import Path
from typing import Any, Tuple
from urllib.request import urlretrieve

import numpy as np
import openvino.runtime as ov

logger = logging.getLogger("openvino_xai")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


SALIENCY_MAP_OUTPUT_NAME = "saliency_map"


def has_xai(model: ov.Model) -> bool:
    """
    Function checks if the model contains XAI branch.

    :param model: OV IR model.
    :type model: ov.Model
    :return: True is the model has XAI branch and saliency_map output, False otherwise.
    """
    if not isinstance(model, ov.Model):
        raise ValueError(f"Input model has to be ov.Model instance, but got{type(model)}.")
    for output in model.outputs:
        if SALIENCY_MAP_OUTPUT_NAME in output.get_names():
            return True
    return False


# Not a part of product
def retrieve_otx_model(data_dir: str | Path, model_name: str, dir_url=None) -> None:
    destination_folder = Path(data_dir) / "otx_models"
    os.makedirs(destination_folder, exist_ok=True)
    if dir_url is None:
        dir_url = f"https://storage.openvinotoolkit.org/repositories/model_api/test/otx_models/{model_name}"
        snapshot_file = "openvino"
    else:
        snapshot_file = model_name

    for post_fix in ["xml", "bin"]:
        if not os.path.isfile(os.path.join(destination_folder, model_name + f".{post_fix}")):
            urlretrieve(  # nosec B310
                f"{dir_url}/{snapshot_file}.{post_fix}",
                f"{destination_folder}/{model_name}.{post_fix}",
            )


def scaling(saliency_map: np.ndarray, cast_to_uint8: bool = True, max_value: int = 255) -> np.ndarray:
    """Scaling saliency maps to [0, max_value] range."""
    original_num_dims = saliency_map.ndim
    if original_num_dims == 2:
        # If input map is 2D array, add dim so that below code would work
        saliency_map = saliency_map[np.newaxis, ...]

    saliency_map = saliency_map.astype(np.float32)
    num_maps, h, w = saliency_map.shape
    saliency_map = saliency_map.reshape((num_maps, h * w))

    min_values, max_values = get_min_max(saliency_map)
    saliency_map = max_value * (saliency_map - min_values[:, None]) / (max_values - min_values + 1e-12)[:, None]
    saliency_map = saliency_map.reshape(num_maps, h, w)

    if original_num_dims == 2:
        saliency_map = np.squeeze(saliency_map)

    if cast_to_uint8:
        return saliency_map.astype(np.uint8)
    return saliency_map


def get_min_max(saliency_map: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Returns min and max values of saliency map of shape (N, -1)."""
    min_values = np.min(saliency_map, axis=-1)
    max_values = np.max(saliency_map, axis=-1)
    return min_values, max_values


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Compute sigmoid values of x."""
    return 1 / (1 + np.exp(-x))


def softmax(x: np.ndarray) -> np.ndarray:
    """Compute softmax values of x."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()


class IdentityPreprocessFN:
    def __call__(self, x: Any) -> Any:
        return x


def is_bhwc_layout(image: np.array) -> bool:
    """Check whether layout of image is BHWC."""
    _, dim0, dim1, dim2 = image.shape
    if dim0 > dim2 and dim1 > dim2:  # bhwc layout
        return True
    return False


def format_to_bhwc(image: np.ndarray) -> np.ndarray:
    """Format image to BHWC from ndim=3 or ndim=4."""
    if image.ndim == 3:
        image = np.expand_dims(image, axis=0)
    if not is_bhwc_layout(image):
        # bchw layout -> bhwc
        image = image.transpose((0, 2, 3, 1))
    return image


def infer_size_from_image(image: np.ndarray) -> Tuple[int, int]:
    """Estimate image size."""
    if image.ndim not in [2, 3, 4]:
        raise ValueError(f"Supports only two, three, and four dimensional image, but got {image.ndim}.")

    if image.ndim == 2:
        return image.shape

    if image.ndim == 3:
        image = np.expand_dims(image, axis=0)
    _, dim0, dim1, dim2 = image.shape
    if dim0 > dim2 and dim1 > dim2:  # bhwc layout:
        return dim0, dim1
    else:
        return dim1, dim2
