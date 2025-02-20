# Copyright (C) 2023-2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess  # nosec B404 (not a part of product)
from pathlib import Path

import cv2
import numpy as np
import openvino as ov
import pytest

import openvino_xai.api.api as xai
from openvino_xai.common.parameters import Method, Task
from openvino_xai.common.utils import has_xai, retrieve_otx_model
from openvino_xai.explainer.explainer import Explainer, ExplainMode
from openvino_xai.explainer.utils import get_postprocess_fn, get_preprocess_fn
from openvino_xai.methods.black_box.base import Preset

MODELS = [
    "mlc_mobilenetv3_large_voc",  # verified
    "mlc_efficient_b0_voc",  # verified
    "mlc_efficient_v2s_voc",  # verified
    "cls_mobilenetv3_large_cars",
    "cls_efficient_b0_cars",
    "cls_efficient_v2s_cars",
    "mobilenet_v3_large_hc_cf",
    "classification_model_with_xai_head",  # verified
]


MODEL_NUM_CLASSES = {
    "mlc_mobilenetv3_large_voc": 20,
    "mlc_efficient_b0_voc": 20,
    "mlc_efficient_v2s_voc": 20,
    "cls_mobilenetv3_large_cars": 196,
    "cls_efficient_b0_cars": 196,
    "cls_efficient_v2s_cars": 196,
    "mobilenet_v3_large_hc_cf": 8,
    "classification_model_with_xai_head": 4,
    "deit-tiny": 10,
}


MODELS_VOC = [
    "mlc_mobilenetv3_large_voc",  # verified
    "mlc_efficient_b0_voc",  # verified
    "mlc_efficient_v2s_voc",  # verified
    "mobilenet_v3_large_hc_cf",
]


DEFAULT_CLS_MODEL = "mlc_mobilenetv3_large_voc"


class TestClsWB:
    image = cv2.imread("tests/assets/cheetah_person.jpg")
    _ref_sal_maps_reciprocam = {
        "mlc_mobilenetv3_large_voc": np.array([236, 237, 244, 252, 242, 225, 231], dtype=np.uint8),
        "mlc_efficient_b0_voc": np.array([53, 128, 70, 234, 227, 255, 59], dtype=np.uint8),
        "mlc_efficient_v2s_voc": np.array([144, 105, 116, 195, 209, 176, 176], dtype=np.uint8),
        "classification_model_with_xai_head": np.array([165, 161, 209, 211, 208, 206, 196], dtype=np.uint8),
    }
    _ref_sal_maps_vitreciprocam = {
        "deit-tiny": np.array([200, 171, 183, 196, 198, 196, 205, 225, 207, 173, 174, 134, 97, 117], dtype=np.uint8)
    }
    _ref_sal_maps_activationmap = {
        "mlc_mobilenetv3_large_voc": np.array([6, 3, 10, 15, 5, 0, 13], dtype=np.uint8),
    }
    preprocess_fn = get_preprocess_fn(
        change_channel_order=True,
        input_size=(224, 224),
        hwc_to_chw=True,
    )

    @pytest.fixture(autouse=True)
    def setup(self, fxt_data_root):
        self.data_dir = fxt_data_root

    @pytest.mark.parametrize("embed_scaling", [True, False])
    @pytest.mark.parametrize(
        "explain_all_classes",
        [
            False,
            True,
        ],
    )
    def test_vitreciprocam(self, embed_scaling: bool, explain_all_classes: bool):
        model_name = "deit-tiny"
        retrieve_otx_model(self.data_dir, model_name)
        model_path = self.data_dir / "otx_models" / (model_name + ".xml")

        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            explain_mode=ExplainMode.WHITEBOX,
            explain_method=Method.VITRECIPROCAM,
            embed_scaling=embed_scaling,
        )

        if explain_all_classes:
            explanation = explainer(
                self.image,
                targets=-1,
                resize=False,
                colormap=False,
            )
            assert explanation is not None
            assert len(explanation.saliency_map) == MODEL_NUM_CLASSES[model_name]
            if model_name in self._ref_sal_maps_vitreciprocam:
                actual_sal_vals = explanation.saliency_map[0][0, :].astype(np.int16)
                ref_sal_vals = self._ref_sal_maps_vitreciprocam[model_name].astype(np.uint8)
                if embed_scaling:
                    # Reference values generated with embed_scaling=True
                    assert np.all(np.abs(actual_sal_vals - ref_sal_vals) <= 1)
                else:
                    assert np.sum(np.abs(actual_sal_vals - ref_sal_vals)) > 100

        if not explain_all_classes:
            target_class = 1
            explanation = explainer(
                self.image,
                targets=[target_class],
                resize=False,
                colormap=False,
            )
            assert explanation is not None
            assert target_class in explanation.saliency_map
            assert len(explanation.saliency_map) == len([target_class])
            assert explanation.saliency_map[target_class].ndim == 2

    @pytest.mark.parametrize("model_name", MODELS)
    @pytest.mark.parametrize("embed_scaling", [True, False])
    @pytest.mark.parametrize(
        "explain_all_classes",
        [
            False,
            True,
        ],
    )
    def test_reciprocam(self, model_name: str, embed_scaling: bool, explain_all_classes: bool):
        retrieve_otx_model(self.data_dir, model_name)
        model_path = self.data_dir / "otx_models" / (model_name + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            explain_mode=ExplainMode.WHITEBOX,
            explain_method=Method.RECIPROCAM,
            embed_scaling=embed_scaling,
        )

        if explain_all_classes:
            explanation = explainer(
                self.image,
                targets=-1,
                resize=False,
                colormap=False,
            )
            assert explanation is not None
            assert len(explanation.saliency_map) == MODEL_NUM_CLASSES[model_name]
            if model_name in self._ref_sal_maps_reciprocam:
                actual_sal_vals = explanation.saliency_map[0][0, :].astype(np.int16)
                ref_sal_vals = self._ref_sal_maps_reciprocam[model_name].astype(np.uint8)
                if embed_scaling:
                    # Reference values generated with embed_scaling=True
                    assert np.all(np.abs(actual_sal_vals - ref_sal_vals) <= 1)
                else:
                    if model_name == "classification_model_with_xai_head":
                        pytest.skip("model already has fixed xai head - this test cannot change it.")
                    assert np.sum(np.abs(actual_sal_vals - ref_sal_vals)) > 100

        if not explain_all_classes:
            target_class = 1
            explanation = explainer(
                self.image,
                targets=[target_class],
                resize=False,
                colormap=False,
            )
            assert explanation is not None
            assert target_class in explanation.saliency_map
            assert len(explanation.saliency_map) == len([target_class])
            assert explanation.saliency_map[target_class].ndim == 2

    @pytest.mark.parametrize("model_name", MODELS)
    @pytest.mark.parametrize("embed_scaling", [True, False])
    def test_activationmap(self, model_name: str, embed_scaling: bool):
        if model_name == "classification_model_with_xai_head":
            pytest.skip("model already has reciprocam xai head - this test cannot change it.")
        retrieve_otx_model(self.data_dir, model_name)
        model_path = self.data_dir / "otx_models" / (model_name + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            explain_mode=ExplainMode.WHITEBOX,
            explain_method=Method.ACTIVATIONMAP,
            embed_scaling=embed_scaling,
        )

        explanation = explainer(
            self.image,
            targets=-1,
            resize=False,
            colormap=False,
        )
        if model_name in self._ref_sal_maps_activationmap and embed_scaling:
            actual_sal_vals = explanation.saliency_map["per_image_map"][0, :].astype(np.int16)
            ref_sal_vals = self._ref_sal_maps_activationmap[model_name].astype(np.uint8)
            # Reference values generated with embed_scaling=True
            assert np.all(np.abs(actual_sal_vals - ref_sal_vals) <= 1)
        assert explanation is not None
        assert "per_image_map" in explanation.saliency_map
        assert explanation.saliency_map["per_image_map"].ndim == 2

    @pytest.mark.parametrize(
        "explain_all_classes",
        [
            True,
            False,
        ],
    )
    @pytest.mark.parametrize("overlay", [True, False])
    def test_classification_visualizing(self, explain_all_classes: bool, overlay: bool):
        retrieve_otx_model(self.data_dir, DEFAULT_CLS_MODEL)
        model_path = self.data_dir / "otx_models" / (DEFAULT_CLS_MODEL + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            explain_mode=ExplainMode.WHITEBOX,
        )

        explain_targets = -1
        if not explain_all_classes:
            explain_targets = [1]  # type: ignore

        explanation = explainer(
            self.image,
            targets=explain_targets,  # type: ignore
            overlay=overlay,
            resize=False,
            colormap=False,
        )
        assert explanation is not None
        if explain_all_classes:
            assert len(explanation.saliency_map) == MODEL_NUM_CLASSES[DEFAULT_CLS_MODEL]
        if not explain_all_classes:
            assert len(explanation.saliency_map) == len(explain_targets)  # type: ignore
            assert 1 in explanation.saliency_map
        if overlay:
            assert explanation.shape == (354, 500, 3)
        else:
            assert explanation.shape == (7, 7)
            for map_ in explanation.saliency_map.values():
                assert map_.min() == 0, f"{map_.min()}"
                assert map_.max() in {254, 255}, f"{map_.max()}"

    def test_two_sequential_norms(self):
        retrieve_otx_model(self.data_dir, DEFAULT_CLS_MODEL)
        model_path = self.data_dir / "otx_models" / (DEFAULT_CLS_MODEL + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,
            explain_mode=ExplainMode.WHITEBOX,
        )

        explanation = explainer(
            self.image,
            targets=-1,
            scaling=True,
            resize=False,
            colormap=False,
        )

        actual_sal_vals = explanation.saliency_map[0][0, :].astype(np.int16)
        ref_sal_vals = self._ref_sal_maps_reciprocam[DEFAULT_CLS_MODEL].astype(np.uint8)
        # Reference values generated with embed_scaling=True
        assert np.all(np.abs(actual_sal_vals - ref_sal_vals) <= 1)

        for map_ in explanation.saliency_map.values():
            assert map_.min() == 0, f"{map_.min()}"
            assert map_.max() in {254, 255}, f"{map_.max()}"


class TestClsBB:
    image = cv2.imread("tests/assets/cheetah_person.jpg")
    _ref_sal_maps = {
        "mlc_mobilenetv3_large_voc": np.array([246, 241, 236, 231, 226, 221, 216, 211, 205, 197], dtype=np.uint8),
    }
    preprocess_fn = get_preprocess_fn(
        change_channel_order=True,
        input_size=(224, 224),
        hwc_to_chw=True,
    )

    @pytest.fixture(autouse=True)
    def setup(self, fxt_data_root):
        self.data_dir = fxt_data_root

    @pytest.mark.parametrize("model_name", MODELS)
    @pytest.mark.parametrize("overlay", [True, False])
    @pytest.mark.parametrize("scaling", [True, False])
    def test_aise(
        self,
        model_name: str,
        overlay: bool,
        scaling: bool,
    ):
        retrieve_otx_model(self.data_dir, model_name)
        model_path = self.data_dir / "otx_models" / (model_name + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            postprocess_fn=get_postprocess_fn(),  # type: ignore
            explain_mode=ExplainMode.BLACKBOX,
        )
        target_class = 1
        explanation = explainer(
            self.image,
            targets=[target_class],
            scaling=scaling,
            overlay=overlay,
            resize=False,
            colormap=False,
            num_iterations_per_kernel=2,
            kernel_widths=[0.1],
        )
        assert target_class in explanation.saliency_map
        assert len(explanation.saliency_map) == len([target_class])
        if overlay:
            assert explanation.saliency_map[target_class].ndim == 3
        else:
            assert explanation.saliency_map[target_class].ndim == 2

    @pytest.mark.parametrize("model_name", MODELS)
    @pytest.mark.parametrize("overlay", [True, False])
    @pytest.mark.parametrize(
        "explain_all_classes",
        [
            True,
            False,
        ],
    )
    @pytest.mark.parametrize("scaling", [True, False])
    def test_rise(
        self,
        model_name: str,
        overlay: bool,
        explain_all_classes: bool,
        scaling: bool,
    ):
        retrieve_otx_model(self.data_dir, model_name)
        model_path = self.data_dir / "otx_models" / (model_name + ".xml")
        model = ov.Core().read_model(model_path)

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,  # type: ignore
            postprocess_fn=get_postprocess_fn(),  # type: ignore
            explain_mode=ExplainMode.BLACKBOX,
            explain_method=Method.RISE,
        )

        if not explain_all_classes:
            target_class = 1
            explanation = explainer(
                self.image,
                targets=[target_class],
                scaling=scaling,
                overlay=overlay,
                resize=False,
                colormap=False,
                num_masks=5,
            )

            assert explanation is not None
            assert target_class in explanation.saliency_map
            assert len(explanation.saliency_map) == len([target_class])
            if overlay:
                assert explanation.saliency_map[target_class].ndim == 3
            else:
                assert explanation.saliency_map[target_class].ndim == 2

        if explain_all_classes:
            explanation = explainer(
                self.image,
                targets=-1,
                scaling=scaling,
                overlay=overlay,
                resize=False,
                colormap=False,
                num_masks=5,
            )

            assert explanation is not None
            if overlay:
                assert len(explanation.saliency_map) == MODEL_NUM_CLASSES[model_name]
                assert explanation.shape == (354, 500, 3)
            else:
                assert len(explanation.saliency_map) == MODEL_NUM_CLASSES[model_name]
                assert explanation.shape == (224, 224)
                if scaling:
                    for map_ in explanation.saliency_map.values():
                        assert map_.min() == 0, f"{map_.min()}"
                        assert map_.max() in {254, 255}, f"{map_.max()}"

    def test_rise_xai_model_as_input(self):
        retrieve_otx_model(self.data_dir, DEFAULT_CLS_MODEL)
        model_path = self.data_dir / "otx_models" / (DEFAULT_CLS_MODEL + ".xml")
        model = ov.Core().read_model(model_path)
        model_xai = xai.insert_xai(
            model,
            task=Task.CLASSIFICATION,
        )
        assert has_xai(model_xai), "Updated IR model should has XAI head."

        explainer = Explainer(
            model=model_xai,
            task=Task.CLASSIFICATION,
            preprocess_fn=self.preprocess_fn,
            postprocess_fn=get_postprocess_fn(),
            explain_mode=ExplainMode.BLACKBOX,
            explain_method=Method.RISE,
        )
        explanation = explainer(
            self.image,
            targets=[0],
            resize=False,
            colormap=False,
            num_masks=5,
        )

        actual_sal_vals = explanation.saliency_map[0][0, :10].astype(np.int16)
        ref_sal_vals = self._ref_sal_maps[DEFAULT_CLS_MODEL].astype(np.uint8)
        assert np.all(np.abs(actual_sal_vals - ref_sal_vals) <= 1)


class TestExample:
    """Test sanity of examples/run_classification.py."""

    @pytest.fixture(autouse=True)
    def setup(self, fxt_data_root):
        self.data_dir = fxt_data_root

    def test_default_model(self):
        retrieve_otx_model(self.data_dir, DEFAULT_CLS_MODEL)
        model_path = self.data_dir / "otx_models" / (DEFAULT_CLS_MODEL + ".xml")
        cmd = [
            "python",
            "examples/run_classification.py",
            model_path,
            "tests/assets/cheetah_person.jpg",
        ]
        subprocess.run(cmd, check=True)  # noqa: S603, PLW1510
