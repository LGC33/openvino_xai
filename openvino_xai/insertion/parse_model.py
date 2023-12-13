# Copyright (C) 2023 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Optional, List, Callable

import openvino

from openvino_xai.insertion.insertion_parameters import ModelType


class IRParser:
    """Parser parse OV IR model."""

    @staticmethod
    def get_logit_node(model: openvino.runtime.Model, output_id: int = 0) -> openvino.runtime.Node:
        logit_node = (
            model.get_output_op(output_id)
            .input(0)
            .get_source_output()
            .get_node()
        )
        return logit_node

    @staticmethod
    def get_node_by_condition(ops: List[openvino.runtime.Node], condition: Callable, k: int = 1):
        """Returns k-th node, which satisfies the condition."""
        for op in ops:
            if condition(op):
                k -= 1
                if k == 0:
                    return op

    @classmethod
    def _is_conv_node_w_spacial_size(cls, op: openvino.runtime.Node) -> bool:
        if op.get_type_name() != "Convolution":
            return False
        if not cls._has_spacial_size(op):
            return False
        return True

    @classmethod
    def _is_concat_node_w_non_constant_inputs(cls, op):
        if op.get_type_name() != "Concat":
            return False
        input_nodes = op.inputs()
        for input_node in input_nodes:
            if input_node.get_source_output().get_node().get_type_name() == "Constant":
                return False
        return True

    @classmethod
    def _is_pooling_node_wo_spacial_size(cls, op: openvino.runtime.Node) -> bool:
        if "Pool" not in op.get_friendly_name():
            return False
        if cls._has_spacial_size(op):
            return False
        return True

    @staticmethod
    def _is_op_w_single_spacial_output(op: openvino.runtime.Node) -> bool:
        if op.get_type_name() == "Constant":
            return False
        if len(op.outputs()) > 1:
            return False
        node_output_shape = op.output(0).partial_shape
        if node_output_shape.rank.get_length() != 4:
            return False
        c, h, w, = node_output_shape[1].get_length(), node_output_shape[2].get_length(), node_output_shape[3].get_length()
        return 1 < h < c and 1 < w < c

    @staticmethod
    def _has_spacial_size(node: openvino.runtime.Node, output_id: int = 0) -> Optional[bool]:
        node_output_shape = node.output(output_id).partial_shape

        # NCHW
        h, w, = node_output_shape[2].get_length(), node_output_shape[3].get_length()
        # NHWC
        h_, w_, = node_output_shape[1].get_length(), node_output_shape[2].get_length()
        return (h != 1 and w != 1) or (h_ != 1 and w_ != 1)

    @staticmethod
    def _is_add_node_w_two_non_constant_inputs(op: openvino.runtime.Node):
        if op.get_type_name() != "Add":
            return False
        input_nodes = op.inputs()
        for input_node in input_nodes:
            if len(input_node.get_partial_shape()) != 3:
                return False
            if input_node.get_source_output().get_node().get_type_name() == "Constant":
                return False
            if input_node.get_source_output().get_node().get_type_name() == "Convert":
                return False
        return True


class IRParserCls(IRParser):
    """ParserCls parse classification OV IR model."""
    # TODO: use OV pattern matching functionality
    # TODO: separate for CNNs and ViT

    @classmethod
    def get_logit_node(cls, model: openvino.runtime.Model, output_id=0, search_softmax=False) -> openvino.runtime.Node:
        if search_softmax:
            reversed_ops = model.get_ordered_ops()[::-1]
            softmax_node = cls.get_node_by_condition(reversed_ops, lambda x: x.get_type_name() == "Softmax")
            if softmax_node and len(softmax_node.get_output_partial_shape(0)) == 2:
                logit_node = softmax_node.input(0).get_source_output().get_node()
                return logit_node

        logit_node = (
            model.get_output_op(output_id)
            .input(0)
            .get_source_output()
            .get_node()
        )
        return logit_node

    @classmethod
    def get_target_node(
            cls,
            model: openvino.runtime.Model,
            model_type: Optional[ModelType] = None,
            target_node_name: Optional[str] = None,
            k: int = 1,
    ) -> openvino.runtime.Node:
        """
        Returns target node.
        Target node - node after which XAI branch will be inserted,
        i.e. output of the target node is used to generate input for the downstream XAI branch.
        """
        if target_node_name:
            reversed_ops = model.get_ordered_ops()[::-1]
            target_node = cls.get_node_by_condition(
                reversed_ops, lambda x: x.get_friendly_name() == target_node_name
            )
            if target_node is not None:
                return target_node
            raise ValueError(f"Cannot find {target_node_name} node.")

        if model_type == ModelType.CNN:
            # Make an attempt to search for last node with spacial dimensions
            reversed_ops = model.get_ordered_ops()[::-1]
            last_op_w_spacial_output = cls.get_node_by_condition(reversed_ops, cls._is_op_w_single_spacial_output, k)
            if last_op_w_spacial_output is not None:
                return last_op_w_spacial_output

            # Make an attempt to search for last backbone node via post_target_node
            post_target_node = cls.get_post_target_node(model)
            target_node = post_target_node.input(0).get_source_output().get_node()
            if cls._has_spacial_size(target_node):
                return target_node

        if model_type == ModelType.TRANSFORMER:
            reversed_ops = model.get_ordered_ops()[::-1]
            target_node = cls.get_node_by_condition(
                reversed_ops, cls._is_add_node_w_two_non_constant_inputs, k
            )
            if target_node is not None:
                return target_node

        raise RuntimeError(f"Cannot find output backbone_node in auto mode, please provide target_layer.")

    @classmethod
    def get_post_target_node(
            cls,
            model,
            model_type: Optional[ModelType] = None,
            target_node_name: Optional[str] = None,
            target_node_output_id: int = 0
    ) -> List[openvino.runtime.Node]:
        if target_node_name:
            target_node = cls.get_target_node(model, model_type, target_node_name)
            target_node_outputs = target_node.output(target_node_output_id).get_target_inputs()
            post_target_nodes = [target_node_output.get_node() for target_node_output in target_node_outputs]
            return post_target_nodes

        if model_type == ModelType.CNN:
            # Make an attempt to search for a last pooling node
            reversed_ops = model.get_ordered_ops()[::-1]
            last_pooling_node = cls.get_node_by_condition(reversed_ops, cls._is_pooling_node_wo_spacial_size)
            if last_pooling_node is not None:
                return [last_pooling_node]

        raise RuntimeError("Cannot find first head node in auto mode, please explicitly provide input parameters.")

    @classmethod
    def get_first_conv_node(cls, model):
        ops = model.get_ordered_ops()
        first_conv_node = cls.get_node_by_condition(ops, cls._is_conv_node_w_spacial_size)
        if first_conv_node is not None:
            return first_conv_node

        raise RuntimeError(f"Cannot find first convolution node in auto mode.")

    @classmethod
    def get_first_concat_node(cls, model):
        ops = model.get_ordered_ops()
        first_concat_node = cls.get_node_by_condition(ops, cls._is_concat_node_w_non_constant_inputs)
        if first_concat_node is not None:
            return first_concat_node

        raise RuntimeError(f"Cannot find first convolution node in auto mode.")
