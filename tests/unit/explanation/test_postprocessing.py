# Copyright (C) 2023-2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from openvino_xai.common.utils import get_min_max, normalize
from openvino_xai.explanation import colormap, overlay, resize
from openvino_xai.explanation.explanation_parameters import (
    PostProcessParameters,
    TargetExplainGroup,
)
from openvino_xai.explanation.explanation_result import ExplanationResult
from openvino_xai.explanation.post_process import PostProcessor

SALIENCY_MAPS = [
    (np.random.rand(1, 5, 5) * 255).astype(np.uint8),
    (np.random.rand(1, 2, 5, 5) * 255).astype(np.uint8),
]

TARGET_EXPLAIN_GROUPS = [
    TargetExplainGroup.ALL,
    TargetExplainGroup.CUSTOM,
]


def test_normalize_3d():
    # Test normalization on a multi-channel input
    input_saliency_map = (np.random.rand(3, 5, 5) - 0.5) * 1000
    assert (input_saliency_map < 0).any() and (input_saliency_map > 255).any()
    normalized_map = normalize(input_saliency_map)
    assert (normalized_map >= 0).all() and (normalized_map <= 255).all()


def test_normalize_2d():
    # Test normalization on a simple 2D input
    input_saliency_map = (np.random.rand(5, 5) - 0.5) * 1000
    assert (input_saliency_map < 0).any() and (input_saliency_map > 255).any()
    normalized_map = normalize(input_saliency_map)
    assert (normalized_map >= 0).all() and (normalized_map <= 255).all()


def test_normalize_cast_to_int8():
    # Test if output is correctly cast to uint8
    input_saliency_map = (np.random.rand(3, 5, 5) - 0.5) * 1000
    normalized_map = normalize(input_saliency_map)
    assert normalized_map.dtype == np.uint8

    input_saliency_map = (np.random.rand(3, 5, 5) - 0.5) * 1000
    normalized_map = normalize(input_saliency_map, cast_to_uint8=False)
    assert normalized_map.dtype == np.float32


def test_get_min_max():
    # Test min and max calculation
    input_saliency_map = np.array([[[10, 20, 30], [40, 50, 60]]]).reshape(1, -1)
    min_val, max_val = get_min_max(input_saliency_map)
    assert min_val == [10]
    assert max_val == [60]


def test_resize():
    # Test resizing functionality
    input_saliency_map = np.random.randint(0, 255, (1, 3, 3), dtype=np.uint8)
    resized_map = resize(input_saliency_map, (5, 5))
    assert resized_map.shape == (1, 5, 5)


def test_colormap():
    input_saliency_map = np.random.randint(0, 255, (1, 3, 3), dtype=np.uint8)
    colored_map = colormap(input_saliency_map)
    assert colored_map.shape == (1, 3, 3, 3)  # Check added color channels


def test_overlay():
    # Test overlay functionality
    input_image = np.ones((3, 3, 3), dtype=np.uint8) * 100
    saliency_map = np.ones((3, 3, 3), dtype=np.uint8) * 150
    overlayed_image = overlay(saliency_map, input_image)
    expected_output = np.ones((3, 3, 3), dtype=np.uint8) * 125
    assert (overlayed_image == expected_output).all()


class TestPostProcessor:
    @pytest.mark.parametrize("saliency_maps", SALIENCY_MAPS)
    @pytest.mark.parametrize("target_explain_group", TARGET_EXPLAIN_GROUPS)
    @pytest.mark.parametrize("normalize", [True, False])
    @pytest.mark.parametrize("resize", [True, False])
    @pytest.mark.parametrize("colormap", [True, False])
    @pytest.mark.parametrize("overlay", [True, False])
    @pytest.mark.parametrize("overlay_weight", [0.5, 0.3])
    def test_postprocessor(
        self,
        saliency_maps,
        target_explain_group,
        normalize,
        resize,
        colormap,
        overlay,
        overlay_weight,
    ):
        post_processing_parameters = PostProcessParameters(
            normalize=normalize,
            resize=resize,
            colormap=colormap,
            overlay=overlay,
            overlay_weight=overlay_weight,
        )

        if target_explain_group == TargetExplainGroup.CUSTOM:
            explain_targets = [0]
        else:
            explain_targets = None

        if saliency_maps.ndim == 3:
            target_explain_group = TargetExplainGroup.IMAGE
            explain_targets = None
        explanation_result = ExplanationResult(
            saliency_maps, target_explain_group=target_explain_group, target_explain_labels=explain_targets
        )

        raw_sal_map_dims = len(explanation_result.sal_map_shape)
        data = np.ones((20, 20, 3))
        post_processor = PostProcessor(
            explanation=explanation_result,
            data=data,
            post_processing_parameters=post_processing_parameters,
        )
        explanation = post_processor.run()

        assert explanation is not None
        expected_dims = raw_sal_map_dims
        if colormap or overlay:
            expected_dims += 1
        assert len(explanation.sal_map_shape) == expected_dims

        if normalize and not colormap and not overlay:
            for map_ in explanation.saliency_map.values():
                assert map_.min() == 0, f"{map_.min()}"
                assert map_.max() in {254, 255}, f"{map_.max()}"
        if resize or overlay:
            for map_ in explanation.saliency_map.values():
                assert map_.shape[:2] == data.shape[:2]

        if target_explain_group == TargetExplainGroup.IMAGE and not overlay:
            explanation_result = ExplanationResult(
                saliency_maps, target_explain_group=target_explain_group, target_explain_labels=explain_targets
            )
            post_processor = PostProcessor(
                explanation=explanation_result,
                output_size=(20, 20),
                post_processing_parameters=post_processing_parameters,
            )
            saliency_map_processed_output_size = post_processor.run()
            maps_data = explanation.saliency_map
            maps_size = saliency_map_processed_output_size.saliency_map
            assert np.all(maps_data["per_image_map"] == maps_size["per_image_map"])
