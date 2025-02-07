# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import openvino as ov

from openvino_xai.api.api import insert_xai
from openvino_xai.common.parameters import Task
from openvino_xai.common.utils import has_xai, retrieve_otx_model
from tests.intg.test_classification import DEFAULT_CLS_MODEL


def test_has_xai(fxt_data_root: Path):
    model_without_xai = DEFAULT_CLS_MODEL
    retrieve_otx_model(fxt_data_root, model_without_xai)
    model_path = fxt_data_root / "otx_models" / (model_without_xai + ".xml")
    model = ov.Core().read_model(model_path)

    assert not has_xai(model)

    model_xai = insert_xai(
        model,
        task=Task.CLASSIFICATION,
    )

    assert has_xai(model_xai)
